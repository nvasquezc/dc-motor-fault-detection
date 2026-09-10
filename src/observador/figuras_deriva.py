"""
Figura de deriva de la linea base del observable de diagnostico.

Ajuste biexponencial de la relajacion de d_hat bajo excitacion
constante, con diagnostico de condicionamiento del ajuste y
cuantificacion de la ventana de contaminacion para deteccion.

Jitter Ingenieria SAS
"""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from scipy.optimize import curve_fit

from observador.identificacion import (
    AZUL, GRIS, GRIS_CLARO, GRIS_FONDO, ROJO, TINTA, VERDE,
    COL_DOBLE, MM, _panel,
)

DELTA_FALLA = 0.5      # severidad minima de falla a detectar, % de duty


# ---------------------------------------------------------------
# UTILIDADES DE ESTILO
# ---------------------------------------------------------------
def _marco(ax, minor=True, logy=False):
    ax.grid(True, which="major", axis="both", zorder=0)
    if minor:
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        if not logy:
            ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax.tick_params(which="both", direction="in", top=True, right=True)
    for s in ax.spines.values():
        s.set_linewidth(0.7)
        s.set_visible(True)
        s.set_zorder(10)


def _leyenda(ax, **kw):
    leg = ax.legend(**kw)
    leg.get_frame().set_linewidth(0.7)
    leg.set_zorder(11)
    return leg


# ---------------------------------------------------------------
# MODELO
# ---------------------------------------------------------------
def biexp(t, d_inf, A1, tau1, A2, tau2):
    """Dos procesos de relajacion superpuestos sobre una asintota."""
    return d_inf + A1 * np.exp(-t / tau1) + A2 * np.exp(-t / tau2)


def ajustar_deriva(t, d):
    """
    Ajuste biexponencial con diagnostico de condicionamiento.

    La asintota se acota inferiormente en -0.5 %: valores muy
    negativos carecen de sentido fisico (implicarian que la planta
    rinde mas que el modelo nominal).
    """
    p0 = [max(d.min() * 0.5, 0.05), 1.5, 2.0, 1.5, 30.0]
    lo = [-0.5, 0.0, 0.2, 0.0, 5.0]
    hi = [d.min(), 6.0, 20.0, 6.0, 600.0]

    popt, pcov = curve_fit(biexp, t, d, p0=p0, bounds=(lo, hi),
                           maxfev=80000)
    perr = np.sqrt(np.diag(pcov))
    res = d - biexp(t, *popt)
    ss_res = float((res ** 2).sum())
    ss_tot = float(((d - d.mean()) ** 2).sum())

    en_cota = [abs(popt[i] - lo[i]) < 1e-4 or abs(popt[i] - hi[i]) < 1e-4
               for i in range(5)]
    extrapola = popt[4] > 0.6 * t.max()

    return {
        "d_inf": popt[0], "A1": popt[1], "tau1": popt[2],
        "A2": popt[3], "tau2": popt[4], "err": perr,
        "r2": 1.0 - ss_res / ss_tot,
        "rmse": float(np.sqrt((res ** 2).mean())),
        "resid": res, "en_cota": en_cota, "extrapola": extrapola,
    }


def tiempo_para_umbral(fit, umbral):
    """Instante en que |d(t) - d_inf| cae por debajo del umbral."""
    t = np.linspace(0, 1200, 120000)
    par = {k: fit[k] for k in ("d_inf", "A1", "tau1", "A2", "tau2")}
    y = np.abs(biexp(t, **par) - fit["d_inf"])
    idx = np.where(y < umbral)[0]
    return float(t[idx[0]]) if len(idx) else np.nan


# ---------------------------------------------------------------
# FIGURA
# ---------------------------------------------------------------
def fig_deriva(df_res, salida="docs/fig04_deriva.pdf"):
    r = df_res[df_res["minuto"] > 0].copy()
    t = r["minuto"].values.astype(float)
    d = r["d_hat_media"].values
    ds = r["d_hat_std"].values
    w = r["w_media"].values

    sigma = float(ds[-len(ds) // 3:].mean())
    fit = ajustar_deriva(t, d)
    t_falla = tiempo_para_umbral(fit, DELTA_FALLA)
    t_3s = tiempo_para_umbral(fit, 3 * sigma)

    fig = plt.figure(figsize=(COL_DOBLE, 112 * MM))
    gs = fig.add_gridspec(
        3, 2, width_ratios=[1.55, 1], height_ratios=[2.1, 0.8, 1.4],
        hspace=0.34, wspace=0.32,
        left=0.085, right=0.965, top=0.945, bottom=0.075,
    )
    ax = fig.add_subplot(gs[0, 0])
    axr = fig.add_subplot(gs[1, 0], sharex=ax)
    axw = fig.add_subplot(gs[2, 0], sharex=ax)
    axd = fig.add_subplot(gs[0, 1])
    axc = fig.add_subplot(gs[1:, 1])

    # ---------- (a) Residuo y ajuste ----------
    tf = np.linspace(0, t.max() * 1.02, 800)
    par = {k: fit[k] for k in ("d_inf", "A1", "tau1", "A2", "tau2")}

    ax.set_xlim(0, t.max() + t.max() * 0.02)
    ax.set_ylim(min(-0.2, fit["d_inf"] - 0.3), d.max() * 1.45)

    ax.fill_between(t, d - ds, d + ds, color=AZUL, alpha=0.16,
                    lw=0, zorder=2)
    ax.plot(tf, biexp(tf, **par), "-", color=ROJO, lw=1.2, zorder=4,
            label="Ajuste biexponencial")
    ax.plot(tf, fit["d_inf"] + fit["A1"] * np.exp(-tf / fit["tau1"]),
            "--", color=GRIS, lw=0.85, zorder=3,
            label=fr"Componente rápida  $\tau_1={fit['tau1']:.1f}$ min")
    ax.axhline(fit["d_inf"], color=VERDE, ls="-.", lw=0.85, zorder=3,
               label=fr"Asíntota  $\hat{{d}}_\infty={fit['d_inf']:.2f}$ %")
    ax.plot(t, d, "o", color=AZUL, mec=TINTA, mew=0.45, ms=3.2,
            ls="none", zorder=5, label="Media por minuto")

    ax.set_ylabel(r"Residuo estimado  $\hat{d}$  (%)")
    plt.setp(ax.get_xticklabels(), visible=False)
    _marco(ax)
    _leyenda(ax, loc="upper right", bbox_to_anchor=(0.985, 0.97))

    ax.text(0.025, 0.965,
            f"Excitación constante  $u=50$ %\n"
            f"$R^2 = {fit['r2']:.4f}$,  RMSE $= {fit['rmse']:.3f}$ %",
            transform=ax.transAxes, fontsize=6.6, va="top",
            linespacing=1.5, zorder=6,
            bbox=dict(boxstyle="square,pad=0.38", fc="white",
                      ec=TINTA, lw=0.6))

    # ---------- (b) Residuos del ajuste ----------
    lim = 1.7 * np.abs(fit["resid"]).max()
    axr.set_ylim(-lim, lim)
    axr.axhspan(-fit["rmse"], fit["rmse"], color=ROJO, alpha=0.12,
                lw=0, zorder=1)
    axr.axhline(0, color=ROJO, lw=0.85, zorder=2)
    axr.plot(t, fit["resid"], "o", color=AZUL, mec=TINTA, mew=0.4,
             ms=2.8, ls="none", zorder=4)
    axr.set_ylabel("Residuo\ndel ajuste (%)", fontsize=7,
                   linespacing=1.3)
    axr.yaxis.set_major_locator(MultipleLocator(round(lim / 2, 2)))
    plt.setp(axr.get_xticklabels(), visible=False)
    _marco(axr, minor=False)

    # ---------- (c) Velocidad ----------
    axw.plot(t, w, "-s", color=VERDE, mec=TINTA, mew=0.45, ms=3.0,
             lw=1.0, zorder=4)
    axw.set_xlabel("Tiempo de operación continua  (min)")
    axw.set_ylabel(r"$\omega$  (rpm)")
    axw.set_ylim(w.min() - 0.7, w.max() + 1.0)
    _marco(axw)
    axw.text(0.978, 0.09,
             f"$\\Delta\\omega = +{w[-1]-w[0]:.2f}$ rpm a esfuerzo constante",
             transform=axw.transAxes, ha="right", fontsize=6.5,
             color=VERDE, zorder=6)

    # ---------- (d) Deriva normalizada ----------
    dev = np.maximum((d - fit["d_inf"]) / sigma, 0.6)
    umbral_falla = DELTA_FALLA / sigma

    axd.set_yscale("log")
    axd.set_xlim(0, t.max() + t.max() * 0.02)
    axd.set_ylim(0.6, max(300, dev.max() * 2.5))
    axd.axhspan(0.6, 3, color=GRIS_FONDO, zorder=1)
    axd.axhline(3, color=VERDE, ls="--", lw=0.9, zorder=3)
    axd.axhline(umbral_falla, color=ROJO, ls="-.", lw=0.9, zorder=3)
    axd.plot(t, dev, "-o", color=AZUL, mec=TINTA, mew=0.4,
             ms=2.8, lw=1.0, zorder=4)

    axd.set_xlabel("Tiempo de operación continua  (min)")
    axd.set_ylabel(r"$(\hat{d}-\hat{d}_\infty)\,/\,\sigma_{\hat d}$")
    _marco(axd, logy=True)

    axd.text(t.max() * 0.97, umbral_falla * 0.60,
             f"Falla de {DELTA_FALLA} %", ha="right",
             fontsize=6.4, color=ROJO, va="top")
    axd.text(t.max() * 0.97, 3 * 0.60, r"$3\sigma$", ha="right",
             fontsize=6.4, color=VERDE, va="top")

    # ---------- (e) Tabla de parametros ----------
    axc.axis("off")
    axc.set_xlim(0, 1)
    axc.set_ylim(0, 1)

    filas = [
        (r"$\hat{d}_\infty$", f"{fit['d_inf']:.3f}",
         f"{fit['err'][0]:.3f}", "%"),
        (r"$A_1$", f"{fit['A1']:.3f}", f"{fit['err'][1]:.3f}", "%"),
        (r"$\tau_1$", f"{fit['tau1']:.2f}", f"{fit['err'][2]:.2f}", "min"),
        (r"$A_2$", f"{fit['A2']:.3f}", f"{fit['err'][3]:.3f}", "%"),
        (r"$\tau_2$", f"{fit['tau2']:.1f}", f"{fit['err'][4]:.1f}", "min"),
        (r"$\sigma_{\hat d}$", f"{sigma:.4f}", "—", "%"),
    ]

    axc.text(0.02, 0.93, "Parámetros del ajuste", fontsize=7.2,
             fontweight="bold", va="center")
    axc.plot([0.02, 0.98], [0.875, 0.875], color=TINTA, lw=0.7,
             clip_on=False)

    y = 0.795
    for sym, val, err, uni in filas:
        axc.text(0.05, y, sym, fontsize=7.2, va="center")
        axc.text(0.52, y, val, fontsize=7.2, ha="right", va="center")
        axc.text(0.76, y, f"± {err}" if err != "—" else "",
                 fontsize=6.6, ha="right", color=GRIS, va="center")
        axc.text(0.80, y, uni, fontsize=6.8, color=GRIS, va="center")
        y -= 0.105

    axc.plot([0.02, 0.98], [y + 0.052, y + 0.052], color=TINTA,
             lw=0.7, clip_on=False)

    y -= 0.045
    txt_t = f"{t_falla:.0f} min" if np.isfinite(t_falla) else "> 1200 min"
    axc.text(0.05, y, f"Contaminación $< {DELTA_FALLA}$ %:  {txt_t}",
             fontsize=6.9, color=ROJO, va="center")

    if fit["extrapola"] or any(fit["en_cota"]):
        y -= 0.095
        axc.text(0.05, y,
                 r"$\tau_2$ excede el registro: cota inferior,"
                 "\nno estimación puntual",
                 fontsize=6.4, color=GRIS, style="italic",
                 va="top", linespacing=1.4)

    _panel(ax, "(a)", dx=-0.115)
    _panel(axr, "(b)", dx=-0.115, dy=1.28)
    _panel(axw, "(c)", dx=-0.115)
    _panel(axd, "(d)", dx=-0.245)

    Path(salida).parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(salida)
    fig.savefig(salida.replace(".pdf", ".png"))
    plt.close(fig)

    return fit, sigma, t_falla, t_3s


# ---------------------------------------------------------------
def main(base: str):
    df_res = pd.read_parquet(f"{base}_resumen.parquet")
    fit, sigma, t_falla, t_3s = fig_deriva(df_res)

    r = df_res[df_res["minuto"] > 0]
    d0, d1 = r["d_hat_media"].iloc[0], r["d_hat_media"].iloc[-1]
    t_max = r["minuto"].max()

    print("=" * 62)
    print("DERIVA DE LA LINEA BASE DEL OBSERVABLE")
    print("=" * 62)
    print(f"  Duracion del registro : {t_max:.0f} min")
    print()
    print("  Ajuste biexponencial")
    print(f"    d_inf   : {fit['d_inf']:8.3f} +/- {fit['err'][0]:.3f} %")
    print(f"    A_1     : {fit['A1']:8.3f} +/- {fit['err'][1]:.3f} %")
    print(f"    tau_1   : {fit['tau1']:8.2f} +/- {fit['err'][2]:.2f} min")
    print(f"    A_2     : {fit['A2']:8.3f} +/- {fit['err'][3]:.3f} %")
    print(f"    tau_2   : {fit['tau2']:8.1f} +/- {fit['err'][4]:.1f} min")
    print(f"    R^2     : {fit['r2']:8.5f}")
    print(f"    RMSE    : {fit['rmse']:8.4f} %")
    print()

    if any(fit["en_cota"]):
        nombres = ["d_inf", "A_1", "tau_1", "A_2", "tau_2"]
        cotas = [n for n, c in zip(nombres, fit["en_cota"]) if c]
        print(f"  ADVERTENCIA: parametros en cota: {', '.join(cotas)}")
        print("  El ajuste esta mal condicionado en esos parametros.")
        print()

    if fit["extrapola"]:
        print(f"  ADVERTENCIA: tau_2 = {fit['tau2']:.0f} min supera el")
        print(f"  60 % del registro ({t_max:.0f} min). El proceso lento no")
        print("  se observo completo. Reportar como cota inferior.")
        print()

    print("  Magnitud observada")
    print(f"    Deriva  : {d0 - d1:.4f} %")
    print(f"    sigma   : {sigma:.4f} %")
    print(f"    Relacion: {(d0 - d1)/sigma:.1f} sigma")
    print()
    print("  Ventana de contaminacion")
    tf_s = f"{t_falla:.0f} min" if np.isfinite(t_falla) else "> 1200 min"
    t3_s = f"{t_3s:.0f} min" if np.isfinite(t_3s) else "> 1200 min"
    print(f"    Deriva < {DELTA_FALLA} % : {tf_s}")
    print(f"    Deriva < 3 sigma : {t3_s}")
    print()
    print("  Separacion de escalas")
    print(f"    tau_2 / tau_1 = {fit['tau2']/fit['tau1']:.0f}")
    print("=" * 62)
    print("\nFigura: docs/fig04_deriva.{pdf,png}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: uv run python -m observador.figuras_deriva <ruta_base>")
        sys.exit(1)
    main(sys.argv[1])