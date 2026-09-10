"""
Ensayo de deriva termica.

Registra la evolucion de d_hat, w_raw y corriente durante una
operacion prolongada a duty constante, partiendo de motor frio.
Determina el tiempo de calentamiento necesario antes de tomar
datos de diagnostico.

Jitter Ingenieria SAS
"""

import json
import time
from pathlib import Path

import pandas as pd
import serial

from observador.ensayos import META, obtener_commit
from observador.protocolo import parsear_trama

PUERTO = "COM11"
BAUD = 921600

DUTY = 50               # % de duty durante todo el ensayo
DURACION_MIN = 30       # minutos
INTERVALO_REPORTE = 60  # segundos entre lineas de consola


def registrar(puerto: str = PUERTO,
              duty: int = DUTY,
              minutos: float = DURACION_MIN) -> pd.DataFrame:
    ser = serial.Serial(puerto, BAUD, timeout=0.1)
    time.sleep(0.5)
    ser.reset_input_buffer()

    filas = []
    t_fin = time.time() + minutos * 60
    t_prox = time.time()

    print(f"{'min':>6} {'w_raw':>9} {'d_hat':>9} {'i_r':>9} {'nf':>6}")
    print("-" * 46)

    try:
        ser.write(b"Z\r\n")
        time.sleep(0.5)
        ser.write(f"D{duty}\r\n".encode())
        t0 = time.time()

        while time.time() < t_fin:
            m = parsear_trama(ser.readline())
            if not m:
                continue
            m["t_ensayo"] = time.time() - t0
            filas.append(m)

            if time.time() >= t_prox:
                t_prox = time.time() + INTERVALO_REPORTE
                # Promedio de las ultimas 100 muestras
                v = pd.DataFrame(filas[-100:])
                print(f"{m['t_ensayo']/60:6.1f} {v['w_raw'].mean():9.3f} "
                      f"{v['d_hat'].mean():9.4f} {v['i_r'].mean():9.4f} "
                      f"{v['n_flancos'].mean():6.2f}")

    except KeyboardInterrupt:
        print("\n>> Interrumpido")
    finally:
        ser.write(b"D0\r\n")
        time.sleep(0.3)
        ser.close()
        print(">> Motor detenido")

    df = pd.DataFrame(filas)
    df["duty_cmd"] = duty
    return df


def guardar(df: pd.DataFrame, carpeta: str = "data") -> str:
    Path(carpeta).mkdir(exist_ok=True, parents=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = f"{carpeta}/deriva_{stamp}"

    df.to_parquet(f"{base}_crudo.parquet", index=False)

    # Resumen por minuto
    df["minuto"] = (df["t_ensayo"] // 60).astype(int)
    res = df.groupby("minuto").agg(
        w_media=("w_raw", "mean"),
        w_std=("w_raw", "std"),
        d_hat_media=("d_hat", "mean"),
        d_hat_std=("d_hat", "std"),
        i_r_media=("i_r", "mean"),
        nf_media=("n_flancos", "mean"),
        n=("k", "count"),
    ).reset_index()
    res.to_parquet(f"{base}_resumen.parquet", index=False)

    with pd.ExcelWriter(f"{base}.xlsx", engine="openpyxl") as xl:
        res.to_excel(xl, sheet_name="por_minuto", index=False)

    meta = dict(META)
    meta.update({
        "ensayo": "deriva_termica",
        "timestamp": stamp,
        "firmware_commit": obtener_commit(),
        "duty": DUTY,
        "duracion_min": DURACION_MIN,
        "condicion_inicial": "motor frio, en reposo >30 min",
        "n_muestras": len(df),
    })
    with open(f"{base}_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return base


def main():
    print(f">> Firmware commit: {obtener_commit()}")
    print(f">> Duty constante: {DUTY} %")
    print(f">> Duracion: {DURACION_MIN} min")
    print(">> IMPORTANTE: el motor debe estar frio (>30 min en reposo)\n")

    if input("Motor frio y eje libre? [s/N] ").lower() != "s":
        return

    df = registrar()
    if df.empty:
        print("Sin datos")
        return

    base = guardar(df)

    # Comparacion inicio vs final
    n = len(df)
    ini = df.iloc[:n // 20]
    fin = df.iloc[-n // 20:]

    print(f"\n{'=' * 50}")
    print("DERIVA OBSERVADA")
    print(f"{'=' * 50}")
    print(f"  w_raw : {ini['w_raw'].mean():7.3f} -> "
          f"{fin['w_raw'].mean():7.3f} rpm  "
          f"({fin['w_raw'].mean() - ini['w_raw'].mean():+.3f})")
    print(f"  d_hat : {ini['d_hat'].mean():7.4f} -> "
          f"{fin['d_hat'].mean():7.4f} %    "
          f"({fin['d_hat'].mean() - ini['d_hat'].mean():+.4f})")
    print()
    dd = abs(fin["d_hat"].mean() - ini["d_hat"].mean())
    sd = fin["d_hat"].std()
    print(f"  Deriva de d_hat : {dd:.4f} %")
    print(f"  Ruido de d_hat  : {sd:.4f} % (1 sigma en regimen)")
    print(f"  Relacion        : {dd/sd:.1f} sigma")
    if dd > 3 * sd:
        print()
        print("  La deriva termica supera 3 sigma del ruido.")
        print("  REQUIERE protocolo de calentamiento antes de")
        print("  cada corrida del dataset de fallas.")
    print(f"{'=' * 50}")
    print(f"\nGuardado: {base}.*")


if __name__ == "__main__":
    main()