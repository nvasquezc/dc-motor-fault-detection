"""
Figura de deriva de la linea base del observable de diagnostico.

Ajuste monoexponencial de la relajacion de d_hat bajo excitacion
constante, con verificacion de normalidad del ruido en regimen.

Jitter Ingenieria SAS
"""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from scipy import stats
from scipy.optimize import curve_fit

from observador.identificacion import (
    AZUL, GRIS, GRIS_CLARO, GRIS_FONDO, ROJO, TINTA, VERDE,
    COL_DOBLE, MM, _panel,
)

# Rellenos claros: borde oscuro + interior claro da profundidad
# al marcador sin introducir tintas nuevas en la paleta.
AZUL_RELLENO = "#4d8fd1"
VERDE_RELLENO = "#4da64d"

DELTA_FALLA = 0.5           # severidad minima de falla, % de duty
MOSTRAR_HISTOGRAMA = True   # False -> deja el espacio en blanco
T_REGIMEN_FRAC = 0.5        # fraccion final considerada en regimen


# ---------------------------------------------------------------
# ESTILO
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
def monoexp(t, d_inf, A, tau):
    """Relajacion exponencial simple hacia una asintota."""
    return d_inf + A * np.exp(-t / tau)


def ajustar_deriva(t, d):
    """
    Ajuste monoexponencial.

    Se descarto el modelo biexponencial: con el motor iniciando
    tibio la componente rapida no queda dentro del registro y sus
    parametros resultan indeterminados.
    """
    p0 = [float(d[-len(d) // 4:].mean()), float(d[0] - d[-1]), 20.0]
    lo = [float(d.min()) - 0.3, 0.0, 1.0]
    hi = [float(d.max()), 6.0, 300.0]

    popt, pcov = curve_fit(monoexp, t, d, p0=p0, bounds=(lo, hi),
                           maxfev=60000)
    perr = np.sqrt(np.diag(pcov))
    res = d - monoexp(t, *popt)
    ss_res = float((res ** 2).sum())
    ss_tot = float(((d - d.mean()) ** 2).sum())

    return {
        "d_inf": popt[0], "A": popt[1], "tau": popt[2],
        "err": perr,
        "r2": 1.0 - ss_res / ss_tot,
        "rmse": float(np.sqrt((res ** 2).mean())),
        "resid": res,
        "extrapola": popt[2] > 0.6 * t.max(),
    }


def tiempo_para_umbral(fit, umbral):
    """Instante en que |d(t) - d_inf| cae por debajo del umbral."""
    if fit["A"] <= umbral:
        return 0.0
    return float(fit["tau"] * np.log(fit["A"] / umbral))


# ---------------------------------------------------------------
# FIGURA
# ---------------------------------------------------------------
def fig_deriva(df_res, salida="docs/fig04_deriva.pdf"):
    r = df_res[(df_res["minuto"] > 0) & (df_res["nf_media"] > 0.5)].copy()
    t = r["minuto"].values.astype(float)
    d = r["d_hat_media"].values
    ds = r["d_hat_std"].values
    w = r["w_media"].values

    n_reg = int(len(t) * T_REGIMEN_FRAC)
    sigma = float(ds[-n_reg:].mean())
    fit = ajustar_deriva(t, d)
    t_falla = tiempo_para_umbral(fit, DELTA_FALLA)
    t_3s = tiempo_para_umbral(fit, 3 * sigma)

    res_reg = fit["resid"][-n_reg:]
    sw_stat, sw_p = stats.shapiro(res_reg[:min(len(res_reg), 500)])

    fig = plt.figure(figsize=(COL_DOBLE, 120 * MM))
    gs = fig.add_gridspec(
        3, 2, width_ratios=[1, 1], height_ratios=[2.1, 1.05, 1.4],
        hspace=0.38, wspace=0.30,
        left=0.075, right=0.975, top=0.945, bottom=0.015,
    )
    ax = fig.add_subplot(gs[0, 0])
    axr = fig.add_subplot(gs[1, 0], sharex=ax)
    axw = fig.add_subplot(gs[2, 0], sharex=ax)
    axd = fig.add_subplot(gs[0, 1])
    axh = fig.add_subplot(gs[2, 1])
    axc = fig.add_subplot(gs[1, 1])

    # ---------- (a) Residuo y ajuste ----------
    tf = np.linspace(0, t.max() * 1.02, 800)
    ax.set_xlim(0, t.max() + t.max() * 0.02)
    margen = 0.25 * (d.max() - d.min())
    ax.set_ylim(d.min() - margen, d.max() + margen * 2.2)

    ax.fill_between(t, d - ds, d + ds, color=AZUL, alpha=0.16,
                    lw=0, zorder=2)
    ax.axhline(fit["d_inf"], color=VERDE, ls="-.", lw=0.85, zorder=3,
               label=fr"Asíntota  $\hat{{d}}_\infty={fit['d_inf']:.3f}$ %")
    ax.plot(tf, monoexp(tf, fit["d_inf"], fit["A"], fit["tau"]), "-",
            color=ROJO, lw=1.2, zorder=4,
            label=fr"Ajuste exponencial  $\tau={fit['tau']:.1f}$ min")
    ax.plot(t, d, "o", mfc=AZUL_RELLENO, mec=AZUL, mew=0.7, ms=3.0,
            ls="none", zorder=5, label="Media por minuto")

    ax.set_ylabel(r"Residuo estimado  $\hat{d}$  (%)")
    plt.setp(ax.get_xticklabels(), visible=False)
    _marco(ax)
    _leyenda(ax, loc="upper right", bbox_to_anchor=(0.985, 0.97))

    ax.text(0.395, 0.57,
            f"Excitación constante  $u=50$ %\n"
            f"$R^2 = {fit['r2']:.4f}$,  RMSE $= {fit['rmse']:.3f}$ %",
            transform=ax.transAxes, fontsize=6.6, va="top",
            linespacing=1.5, zorder=6,
            bbox=dict(boxstyle="square,pad=0.38", fc="white",
                      ec=TINTA, lw=0.6))

    # ---------- (b) Residuos del ajuste ----------
    lim = 1.7 * float(np.abs(fit["resid"]).max())
    axr.set_ylim(-lim, lim)
    axr.axhspan(-fit["rmse"], fit["rmse"], color=ROJO, alpha=0.12,
                lw=0, zorder=1)
    axr.axhline(0, color=ROJO, lw=0.85, zorder=2)
    axr.plot(t, fit["resid"], "o", mfc=AZUL_RELLENO, mec=AZUL, mew=0.6,
             ms=2.6, ls="none", zorder=4)
    axr.set_ylabel("Residuo\ndel ajuste (%)", fontsize=7,
                   linespacing=1.3)
    axr.yaxis.set_major_locator(MultipleLocator(round(lim / 2, 2)))
    plt.setp(axr.get_xticklabels(), visible=False)
    _marco(axr, minor=False)

    # ---------- (c) Velocidad ----------
    axw.plot(t, w, "-s", color=VERDE, mfc=VERDE_RELLENO, mec=VERDE,
             mew=0.6, ms=2.8, lw=0.9, zorder=4)
    axw.set_xlabel("Tiempo de operación continua  (min)")
    axw.set_ylabel(r"$\omega$  (rpm)")
    mw = 0.25 * (w.max() - w.min())
    axw.set_ylim(w.min() - mw, w.max() + mw * 1.8)
    _marco(axw)
    axw.text(0.978, 0.09,
             f"$\\Delta\\omega = +{w[-1]-w[0]:.2f}$ rpm a esfuerzo constante",
             transform=axw.transAxes, ha="right", fontsize=6.5,
             color=VERDE, zorder=6)

    # ---------- (d) Deriva normalizada ----------
    dev = np.maximum(np.abs(d - fit["d_inf"]) / sigma, 0.6)
    umbral_falla = DELTA_FALLA / sigma

    axd.set_yscale("log")
    axd.set_xlim(0, t.max() + t.max() * 0.02)
    axd.set_ylim(0.6, max(200, dev.max() * 3))
    axd.axhspan(0.6, 3, color=GRIS_FONDO, zorder=1)
    axd.axhline(3, color=VERDE, ls="--", lw=0.9, zorder=3)
    axd.axhline(umbral_falla, color=ROJO, ls="-.", lw=0.9, zorder=3)
    axd.plot(t, dev, "-o", color=AZUL, mfc=AZUL_RELLENO, mec=AZUL,
             mew=0.6, ms=2.6, lw=0.8, zorder=4)
    if np.isfinite(t_3s) and t_3s < t.max():
        axd.axvline(t_3s, color=TINTA, ls=":", lw=0.8, zorder=3)
        axd.text(t_3s + t.max() * 0.025, dev.max() * 1.3,
                 f"{t_3s:.0f} min", fontsize=6.3, color=TINTA)

    axd.set_xlabel("Tiempo de operación continua  (min)")
    axd.set_ylabel(r"$|\hat{d}-\hat{d}_\infty|\,/\,\sigma_{\hat d}$")
    _marco(axd, logy=True)

    axd.text(t.max() * 0.97, umbral_falla * 0.62,
             f"Falla de {DELTA_FALLA} %", ha="right",
             fontsize=6.4, color=ROJO, va="top")
    axd.text(t.max() * 0.97, 3 * 0.62, r"$3\sigma$", ha="right",
             fontsize=6.4, color=VERDE, va="top")

    # ---------- (e) Tabla ----------
    axc.axis("off")
    axc.set_xlim(0, 1)
    axc.set_ylim(0, 1)

    filas = [
        (r"$\hat{d}_\infty$", f"{fit['d_inf']:.3f}",
         f"{fit['err'][0]:.3f}", "%"),
        (r"$A$", f"{fit['A']:.3f}", f"{fit['err'][1]:.3f}", "%"),
        (r"$\tau$", f"{fit['tau']:.1f}", f"{fit['err'][2]:.1f}", "min"),
        (r"$\sigma_{\hat d}$", f"{sigma:.4f}", "—", "%"),
    ]

    axc.text(0.02, 0.97, "Parámetros del ajuste", fontsize=7.2,
             fontweight="bold", va="center")
    axc.plot([0.02, 0.98], [0.86, 0.86], color=TINTA, lw=0.7,
             clip_on=False)

    y = 0.71
    for sym, val, err, uni in filas:
        axc.text(0.06, y, sym, fontsize=7.2, va="center")
        axc.text(0.55, y, val, fontsize=7.2, ha="right", va="center")
        axc.text(0.80, y, f"± {err}" if err != "—" else "",
                 fontsize=6.6, ha="right", color=GRIS, va="center")
        axc.text(0.84, y, uni, fontsize=6.8, color=GRIS, va="center")
        y -= 0.155

    axc.plot([0.02, 0.98], [y + 0.072, y + 0.072], color=TINTA,
             lw=0.7, clip_on=False)
    axc.text(0.06, y - 0.035,
             f"Estabilización ($3\\sigma$):  {t_3s:.0f} min",
             fontsize=6.9, color=ROJO, va="center")

    # ---------- (f) Normalidad del ruido ----------
    if MOSTRAR_HISTOGRAMA:
        axh.hist(res_reg, bins=18, density=True, color=AZUL_RELLENO,
                 alpha=0.75, edgecolor=AZUL, lw=0.6, zorder=3)
        xg = np.linspace(res_reg.min(), res_reg.max(), 200)
        axh.plot(xg, stats.norm.pdf(xg, res_reg.mean(), res_reg.std()),
                 "-", color=ROJO, lw=1.1, zorder=4)
        axh.set_xlabel("Residuo en régimen  (%)")
        axh.set_ylabel("Densidad")
        _marco(axh)
        axh.text(0.03, 0.96,
                 f"Shapiro–Wilk\n$W={sw_stat:.3f}$,  $p={sw_p:.3f}$",
                 transform=axh.transAxes, fontsize=6.4, va="top",
                 linespacing=1.45,
                 bbox=dict(boxstyle="square,pad=0.3", fc="white",
                           ec=GRIS_CLARO, lw=0.5))
    else:
        axh.axis("off")

    _panel(ax, "(a)", dx=-0.145)
    _panel(axr, "(b)", dx=-0.145, dy=1.20)
    _panel(axw, "(c)", dx=-0.145)
    _panel(axd, "(d)", dx=-0.145)
    if MOSTRAR_HISTOGRAMA:
        _panel(axh, "(e)", dx=-0.145)

    Path(salida).parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(salida)
    fig.savefig(salida.replace(".pdf", ".png"))
    plt.close(fig)

    return fit, sigma, t_falla, t_3s, (sw_stat, sw_p)


# ---------------------------------------------------------------
def main(base: str):
    df_res = pd.read_parquet(f"{base}_resumen.parquet")
    fit, sigma, t_falla, t_3s, sw = fig_deriva(df_res)

    r = df_res[df_res["minuto"] > 0]
    d0, d1 = r["d_hat_media"].iloc[0], r["d_hat_media"].iloc[-1]
    t_max = r["minuto"].max()

    print("=" * 62)
    print("DERIVA DE LA LINEA BASE DEL OBSERVABLE")
    print("=" * 62)
    print(f"  Duracion del registro : {t_max:.0f} min")
    print()
    print("  Ajuste monoexponencial")
    print(f"    d_inf : {fit['d_inf']:8.4f} +/- {fit['err'][0]:.4f} %")
    print(f"    A     : {fit['A']:8.4f} +/- {fit['err'][1]:.4f} %")
    print(f"    tau   : {fit['tau']:8.2f} +/- {fit['err'][2]:.2f} min")
    print(f"    R^2   : {fit['r2']:8.5f}")
    print(f"    RMSE  : {fit['rmse']:8.4f} %")
    print()
    if fit["extrapola"]:
        print("  ADVERTENCIA: tau supera el 60 % del registro.")
        print()
    print("  Magnitud observada")
    print(f"    Deriva  : {d0 - d1:.4f} %")
    print(f"    sigma   : {sigma:.4f} %")
    print(f"    Relacion: {abs(d0 - d1)/sigma:.1f} sigma")
    print()
    print("  Protocolo de calentamiento")
    print(f"    Deriva < 3 sigma        : {t_3s:.0f} min")
    print(f"    Deriva < {DELTA_FALLA} % (falla) : {t_falla:.0f} min")
    print()
    print("  Normalidad del ruido en regimen")
    print(f"    Shapiro-Wilk W = {sw[0]:.4f},  p = {sw[1]:.4f}")
    if sw[1] < 0.05:
        print("    El ruido NO es gaussiano (p < 0.05). El filtro de")
        print("    Kalman asume normalidad: declarar como limitacion.")
    elif sw[1] < 0.10:
        print("    Compatible con gaussiano al 5 %, pero marginalmente.")
        print("    La asimetria es consistente con la cuantizacion")
        print("    temporal del metodo M/T.")
    else:
        print("    Compatible con ruido gaussiano.")
    print("=" * 62)
    print("\nFigura: docs/fig04_deriva.{pdf,png}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: uv run python -m observador.figuras_deriva <ruta_base>")
        sys.exit(1)
    main(sys.argv[1])