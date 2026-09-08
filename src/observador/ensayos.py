"""
Ensayos de caracterizacion del accionamiento DC.

Barrido estatico: duty -> RPM para identificar zona muerta y ganancia.
Los datos se guardan en Parquet (analisis) y Excel (inspeccion), con
un sidecar JSON de metadatos que registra el commit del firmware.

Jitter Ingenieria SAS
"""

import json
import subprocess
import time
from pathlib import Path

import pandas as pd
import serial

from observador.protocolo import F_GLITCH, F_STALL, parsear_trama

# ---------------------------------------------------------------
# CONFIGURACION DEL ENSAYO
# ---------------------------------------------------------------
PUERTO = "COM11"
BAUD = 921600

# Resolucion fina cerca del umbral (arranque observado ~20 %)
DUTIES = [0, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28,
          30, 35, 40, 45, 50, 55, 60, 70, 80, 90]

T_ESTAB = 4.0   # segundos de espera tras cambiar el duty
T_MEDIR = 3.0   # segundos de captura por punto

# Metadatos de la corrida (EDITAR en cada campana)
META = {
    "operador": "NVC",
    "montaje": "protoboard, motor libre sin carga",
    "encoder_ppr": 1266,
    "pwm_hz": 16000,
    "ts_ms": 10,
    "clase_falla": "sana",
    "severidad": 0,
    "notas": "barrido inicial de caracterizacion estatica",
}


# ---------------------------------------------------------------
# TRAZABILIDAD
# ---------------------------------------------------------------
def obtener_commit() -> str:
    """
    Hash corto del commit actual del repositorio.
    Se marca con sufijo '-dirty' si hay cambios sin commitear,
    porque en ese caso la corrida no es reproducible.
    """
    try:
        h = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        sucio = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        return f"{h}-dirty" if sucio else h
    except Exception:
        return "desconocido"


# ---------------------------------------------------------------
# ADQUISICION
# ---------------------------------------------------------------
def capturar(ser: serial.Serial, segundos: float) -> list[dict]:
    """Captura tramas validas durante el tiempo indicado."""
    filas = []
    t0 = time.time()
    while time.time() - t0 < segundos:
        m = parsear_trama(ser.readline())
        if m:
            filas.append(m)
    return filas


def barrido(puerto: str = PUERTO,
            duties: list[int] | None = None
            ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ejecuta el barrido estatico completo.
    Devuelve (resumen por punto, muestras crudas).
    """
    duties = duties if duties is not None else DUTIES

    ser = serial.Serial(puerto, BAUD, timeout=0.1)
    time.sleep(0.5)
    ser.reset_input_buffer()

    crudo: list[pd.DataFrame] = []
    resumen: list[dict] = []

    print(f"{'Duty':>6} {'RPM':>9} {'sigma':>8} {'n':>6} {'nf':>6} {'glitch%':>8}")
    print("-" * 50)

    try:
        # Reset de estados antes de empezar
        ser.write(b"Z\r\n")
        time.sleep(0.5)
        ser.write(b"D0\r\n")
        time.sleep(1.0)

        for d in duties:
            ser.write(f"D{d}\r\n".encode())
            time.sleep(T_ESTAB)
            ser.reset_input_buffer()

            filas = capturar(ser, T_MEDIR)
            if not filas:
                print(f"{d:6d}   sin datos")
                continue

            df = pd.DataFrame(filas)
            df["duty_cmd"] = d
            crudo.append(df)

            # El signo de w_raw esta invertido (QA/QB sin permutar):
            # se trabaja con la magnitud.
            w = df["w_raw"].abs()
            pct_glitch = 100.0 * (df["flags"] & F_GLITCH).astype(bool).mean()
            pct_stall = 100.0 * (df["flags"] & F_STALL).astype(bool).mean()

            resumen.append({
                "duty_cmd": d,
                "duty_medido": df["duty"].mean(),
                "rpm_media": w.mean(),
                "rpm_std": w.std(),
                "rpm_min": w.min(),
                "rpm_max": w.max(),
                "w_hat_media": df["w_hat"].abs().mean(),
                "d_hat_media": df["d_hat"].mean(),
                "i_r_media": df["i_r"].mean(),
                "i_l_media": df["i_l"].mean(),
                "n_flancos_media": df["n_flancos"].mean(),
                "n_muestras": len(df),
                "pct_glitch": pct_glitch,
                "pct_stall": pct_stall,
            })

            r = resumen[-1]
            print(f"{d:6d} {r['rpm_media']:9.2f} {r['rpm_std']:8.3f} "
                  f"{r['n_muestras']:6d} {r['n_flancos_media']:6.2f} "
                  f"{pct_glitch:8.1f}")

    except KeyboardInterrupt:
        print("\n>> Interrumpido por el usuario")

    finally:
        ser.write(b"D0\r\n")
        time.sleep(0.3)
        ser.close()
        print(">> Motor detenido, puerto cerrado")

    if not resumen:
        return pd.DataFrame(), pd.DataFrame()

    return pd.DataFrame(resumen), pd.concat(crudo, ignore_index=True)


# ---------------------------------------------------------------
# PERSISTENCIA
# ---------------------------------------------------------------
def guardar(df_res: pd.DataFrame,
            df_crudo: pd.DataFrame,
            carpeta: str = "data",
            prefijo: str = "barrido") -> str:
    """
    Guarda resumen y crudo en Parquet + Excel, con sidecar JSON
    de metadatos. Devuelve la ruta base sin extension.
    """
    Path(carpeta).mkdir(exist_ok=True, parents=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = f"{carpeta}/{prefijo}_{stamp}"

    df_crudo.to_parquet(f"{base}_crudo.parquet", index=False)
    df_res.to_parquet(f"{base}_resumen.parquet", index=False)

    with pd.ExcelWriter(f"{base}.xlsx", engine="openpyxl") as xl:
        df_res.to_excel(xl, sheet_name="resumen", index=False)
        df_crudo.to_excel(xl, sheet_name="crudo", index=False)

    meta = dict(META)
    meta.update({
        "timestamp": stamp,
        "firmware_commit": obtener_commit(),
        "puerto": PUERTO,
        "baudrate": BAUD,
        "duties": list(df_res["duty_cmd"]),
        "t_estab_s": T_ESTAB,
        "t_medir_s": T_MEDIR,
        "n_puntos": len(df_res),
        "n_muestras_total": len(df_crudo),
        "muestras_perdidas": int(
            df_crudo["k"].diff().dropna().sub(1).clip(lower=0).sum()
        ),
    })

    with open(f"{base}_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return base


# ---------------------------------------------------------------
# PUNTO DE ENTRADA
# ---------------------------------------------------------------
def main_barrido():
    commit = obtener_commit()
    if commit.endswith("-dirty"):
        print("AVISO: hay cambios sin commitear.")
        print("       Esta corrida quedara marcada como no reproducible.")
        if input("       Continuar de todos modos? [s/N] ").lower() != "s":
            return

    print(f">> Firmware commit: {commit}")
    print(f">> Puerto: {PUERTO} @ {BAUD} baudios")
    print(f">> Puntos: {len(DUTIES)}  |  Duracion estimada: "
          f"{len(DUTIES) * (T_ESTAB + T_MEDIR) / 60:.1f} min\n")

    df_res, df_crudo = barrido()

    if df_res.empty:
        print("No se capturaron datos. Verifique que el puerto este libre")
        print("(cierre PuTTY) y que la placa este alimentada.")
        return

    base = guardar(df_res, df_crudo)

    print(f"\n{'=' * 50}")
    print(f"Guardado en: {base}.*")
    print(f"Muestras crudas: {len(df_crudo)}")
    print(f"Puntos validos:  {len(df_res)}")
    print(f"{'=' * 50}")
    print("\nSiguiente paso:")
    print(f"  uv run python -m observador.identificacion {base}")


if __name__ == "__main__":
    main_barrido()