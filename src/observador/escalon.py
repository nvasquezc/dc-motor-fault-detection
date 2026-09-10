"""
Ensayo de escalon: identificacion de la constante de tiempo tau.

Aplica saltos de duty desde reposo y ajusta la respuesta exponencial
de primer orden. Se repite a varias amplitudes para verificar que tau
no dependa del punto de operacion.

Jitter Ingenieria SAS
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import serial
from scipy.optimize import curve_fit

from observador.ensayos import META, obtener_commit
from observador.protocolo import parsear_trama

PUERTO = "COM11"
BAUD = 921600

AMPLITUDES = [40, 55, 70]   # % de duty
N_REPETICIONES = 3
T_REPOSO = 3.0              # segundos en cero antes del salto
T_CAPTURA = 6.0             # segundos de registro tras el salto


def modelo_escalon(t, w_ss, tau, t0):
    """Respuesta de primer orden con retardo de arranque."""
    y = np.zeros_like(t)
    m = t >= t0
    y[m] = w_ss * (1.0 - np.exp(-(t[m] - t0) / tau))
    return y


def un_escalon(ser, duty: int) -> pd.DataFrame:
    """Ejecuta un escalon desde reposo y devuelve la respuesta."""
    ser.write(b"D0\r\n")
    time.sleep(T_REPOSO)
    ser.write(b"Z\r\n")
    time.sleep(0.3)
    ser.reset_input_buffer()

    filas = []
    t0 = time.time()
    disparado = False

    while time.time() - t0 < T_CAPTURA:
        # Medio segundo de linea base antes del salto
        if not disparado and time.time() - t0 > 0.5:
            ser.write(f"D{duty}\r\n".encode())
            disparado = True
        m = parsear_trama(ser.readline())
        if m:
            filas.append(m)

    ser.write(b"D0\r\n")
    df = pd.DataFrame(filas)
    df["duty_cmd"] = duty
    df["t_rel"] = (df["t_us"] - df["t_us"].iloc[0]) * 1e-6
    return df


def ajustar(df: pd.DataFrame) -> dict:
    """Ajusta la exponencial y devuelve tau, w_ss y diagnosticos."""
    t = df["t_rel"].values
    w = df["w_raw"].abs().values

    w_ss0 = float(np.median(w[-int(len(w) * 0.2):]))
    if w_ss0 < 1.0:
        raise ValueError("El motor no alcanzo velocidad de regimen")

    p0 = [w_ss0, 0.15, 0.5]
    lo = [0.5 * w_ss0, 0.005, 0.0]
    hi = [1.5 * w_ss0, 3.0, t.max()]

    popt, pcov = curve_fit(modelo_escalon, t, w, p0=p0,
                           bounds=(lo, hi), maxfev=20000)
    perr = np.sqrt(np.diag(pcov))

    resid = w - modelo_escalon(t, *popt)
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((w - w.mean()) ** 2).sum())

    return {
        "w_ss": float(popt[0]),
        "tau": float(popt[1]),
        "t0": float(popt[2]),
        "err_w_ss": float(perr[0]),
        "err_tau": float(perr[1]),
        "r2": 1.0 - ss_res / ss_tot,
        "rmse": float(np.sqrt((resid ** 2).mean())),
        "n": len(df),
    }


def campana(puerto: str = PUERTO):
    ser = serial.Serial(puerto, BAUD, timeout=0.1)
    time.sleep(0.5)
    ser.reset_input_buffer()

    crudo, resultados = [], []

    print(f"{'Duty':>6} {'rep':>4} {'w_ss':>9} {'tau [ms]':>10} "
          f"{'err':>7} {'R2':>8}")
    print("-" * 50)

    try:
        for duty in AMPLITUDES:
            for rep in range(1, N_REPETICIONES + 1):
                df = un_escalon(ser, duty)
                df["rep"] = rep
                crudo.append(df)

                try:
                    r = ajustar(df)
                except (ValueError, RuntimeError) as e:
                    print(f"{duty:6d} {rep:4d}   fallo: {e}")
                    continue

                r.update({"duty_cmd": duty, "rep": rep})
                resultados.append(r)
                print(f"{duty:6d} {rep:4d} {r['w_ss']:9.2f} "
                      f"{r['tau']*1000:10.2f} {r['err_tau']*1000:7.2f} "
                      f"{r['r2']:8.5f}")

    except KeyboardInterrupt:
        print("\n>> Interrumpido")
    finally:
        ser.write(b"D0\r\n")
        time.sleep(0.3)
        ser.close()
        print(">> Motor detenido")

    if not resultados:
        return pd.DataFrame(), pd.DataFrame()

    return pd.DataFrame(resultados), pd.concat(crudo, ignore_index=True)


def guardar(df_res, df_crudo, carpeta="data"):
    Path(carpeta).mkdir(exist_ok=True, parents=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = f"{carpeta}/escalon_{stamp}"

    df_crudo.to_parquet(f"{base}_crudo.parquet", index=False)
    df_res.to_parquet(f"{base}_resumen.parquet", index=False)
    with pd.ExcelWriter(f"{base}.xlsx", engine="openpyxl") as xl:
        df_res.to_excel(xl, sheet_name="ajustes", index=False)
        df_crudo.to_excel(xl, sheet_name="crudo", index=False)

    meta = dict(META)
    meta.update({
        "ensayo": "escalon",
        "timestamp": stamp,
        "firmware_commit": obtener_commit(),
        "amplitudes": AMPLITUDES,
        "n_repeticiones": N_REPETICIONES,
        "t_reposo_s": T_REPOSO,
        "t_captura_s": T_CAPTURA,
    })
    with open(f"{base}_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return base


def main():
    print(f">> Firmware commit: {obtener_commit()}")
    n = len(AMPLITUDES) * N_REPETICIONES
    print(f">> {n} escalones  |  ~{n * (T_REPOSO + T_CAPTURA) / 60:.1f} min\n")

    df_res, df_crudo = campana()
    if df_res.empty:
        print("Sin datos. Verifique que el puerto este libre.")
        return

    base = guardar(df_res, df_crudo)

    print(f"\n{'=' * 50}")
    print("RESUMEN POR AMPLITUD")
    print(f"{'=' * 50}")
    g = df_res.groupby("duty_cmd")["tau"]
    for duty, sub in df_res.groupby("duty_cmd"):
        print(f"  {duty:3d} %:  tau = {sub['tau'].mean()*1000:6.2f} "
              f"+/- {sub['tau'].std()*1000:5.2f} ms   "
              f"(w_ss = {sub['w_ss'].mean():.1f} rpm)")

    tau_global = df_res["tau"].mean()
    tau_std = df_res["tau"].std()
    disp = 100 * tau_std / tau_global

    print()
    print(f"  tau global : {tau_global*1000:.2f} +/- {tau_std*1000:.2f} ms")
    print(f"  dispersion : {disp:.1f} %")
    if disp > 15:
        print("  ATENCION: tau varia con el punto de operacion.")
        print("            La aproximacion de primer orden es debil.")

    K = 1.0654   # de la identificacion estatica
    a = 1.0 - np.exp(-0.01 / tau_global)
    print()
    print(f"{'=' * 50}")
    print("PARAMETROS PARA EL FIRMWARE")
    print(f"{'=' * 50}")
    print(f"  float mod_a = {a:.6f}f;")
    print(f"  float mod_b = {a * K:.6f}f;")
    print(f"{'=' * 50}")
    print(f"\nGuardado: {base}.*")


if __name__ == "__main__":
    main()