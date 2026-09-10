"""
Identificacion de la planta y figuras de publicacion.

Convencion de control automatico: marco cerrado en los cuatro lados,
ticks hacia adentro, grid punteado en ambos ejes, series distinguidas
por color Y estilo de linea.

Jitter Ingenieria SAS
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from scipy import stats

# ---------------------------------------------------------------
# SISTEMA DE DISEÑO
# ---------------------------------------------------------------
MM = 1 / 25.4
COL_SIMPLE = 89 * MM
COL_DOBLE = 183 * MM

TINTA      = "#000000"
GRIS       = "#555555"
GRIS_CLARO = "#9a9a9a"
GRIS_FONDO = "#f0f0f0"

AZUL      = "#0000CC"   # azul puro
ROJO      = "#CC0000"   # rojo puro
VERDE     = "#008000"   # verde
MAGENTA   = "#CC00CC"   # magenta
MARRON    = "#8B4513"   # marron
CIAN      = "#00868B"

ESTILO = {
    "figure.dpi": 300,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
    "savefig.facecolor": "white",
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8.5,
    "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7,
    "mathtext.fontset": "stix",

    # --- Marco cerrado, convencion de control ---
    "axes.linewidth": 0.7,
    "axes.edgecolor": TINTA,
    "axes.labelcolor": TINTA,
    "axes.axisbelow": True,
    "axes.spines.top": True,
    "axes.spines.right": True,
    "axes.spines.bottom": True,
    "axes.spines.left": True,

    "grid.color": GRIS_CLARO,
    "grid.linestyle": ":",
    "grid.linewidth": 0.45,
    "grid.alpha": 0.75,

    # --- Ticks hacia adentro en los cuatro lados ---
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "xtick.minor.width": 0.45,
    "ytick.minor.width": 0.45,
    "xtick.major.size": 3.2,
    "ytick.major.size": 3.2,
    "xtick.minor.size": 1.8,
    "ytick.minor.size": 1.8,
    "xtick.color": TINTA,
    "ytick.color": TINTA,
    "text.color": TINTA,

    "lines.linewidth": 1.1,
    "lines.markersize": 3.5,

    # --- Leyenda con recuadro, convencion de control ---
    "legend.frameon": True,
    "legend.framealpha": 1.0,
    "legend.edgecolor": TINTA,
    "legend.fancybox": False,
    "legend.handlelength": 2.2,
    "legend.handletextpad": 0.6,
    "legend.borderpad": 0.45,
    "legend.labelspacing": 0.4,
}
mpl.rcParams.update(ESTILO)


def _ejes(ax, minor=True):
    """Grid punteado en ambos ejes, marco cerrado, datos por encima."""
    ax.grid(True, which="major", axis="both", zorder=0)
    if minor:
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    for s in ax.spines.values():
        s.set_linewidth(0.7)
        s.set_zorder(10)


def _leyenda(ax, **kw):
    leg = ax.legend(**kw)
    leg.get_frame().set_linewidth(0.7)
    leg.set_zorder(11)
    return leg


def _panel(ax, letra, dx=-0.17, dy=1.06):
    ax.text(dx, dy, letra, transform=ax.transAxes,
            fontsize=9, fontweight="bold", va="top", ha="left")


# ---------------------------------------------------------------
# PARAMETROS
# ---------------------------------------------------------------
UMBRAL_RPM = 1.0
DUTY_MAX_LINEAL = 70
PPR = 1266
TS = 0.01


def identificar(df_res: pd.DataFrame) -> dict:
    girando = df_res[df_res["rpm_media"] > UMBRAL_RPM]
    if girando.empty:
        raise ValueError("Ningun punto con el motor girando")

    quieto = df_res[df_res["rpm_media"] <= UMBRAL_RPM]
    lineal = girando[girando["duty_cmd"] <= DUTY_MAX_LINEAL]
    if len(lineal) < 3:
        raise ValueError("Muy pocos puntos en la zona lineal")

    reg = stats.linregress(lineal["duty_cmd"], lineal["rpm_media"])
    pred = reg.slope * lineal["duty_cmd"] + reg.intercept
    resid = lineal["rpm_media"] - pred

    return {
        "K": reg.slope,
        "u_0": -reg.intercept / reg.slope,
        "intercepto": reg.intercept,
        "u_arranque": float(girando["duty_cmd"].iloc[0]),
        "w_salto": float(girando["rpm_media"].iloc[0]),
        "ultimo_quieto": float(quieto["duty_cmd"].max())
                          if not quieto.empty else np.nan,
        "r2": reg.rvalue ** 2,
        "err_K": reg.stderr,
        "rmse": float(np.sqrt((resid ** 2).mean())),
        "n_puntos_ajuste": len(lineal),
        "duty_ajuste": lineal["duty_cmd"].values,
        "resid": resid.values,
    }


def estimar_kf_R(df_crudo, duty_min=40, duty_max=60) -> float:
    reg = df_crudo[(df_crudo["duty_cmd"] >= duty_min) &
                   (df_crudo["duty_cmd"] <= duty_max)]
    if reg.empty:
        return float("nan")
    return float(reg.groupby("duty_cmd")["w_raw"].var().mean())


def parametros_discretos(K, tau, Ts=TS) -> dict:
    a = 1.0 - np.exp(-Ts / tau)
    return {"mod_a": float(a), "mod_b": float(a * K)}


# ---------------------------------------------------------------
# FIGURA 1
# ---------------------------------------------------------------
def fig_caracteristica(df_res, ident, salida="docs/fig01_caracteristica.pdf"):
    fig = plt.figure(figsize=(COL_SIMPLE, 92 * MM))
    gs = fig.add_gridspec(2, 1, height_ratios=[2.4, 1],
                          hspace=0.13, left=0.21, right=0.965,
                          top=0.94, bottom=0.10)
    ax = fig.add_subplot(gs[0])
    axr = fig.add_subplot(gs[1], sharex=ax)

    quieto = df_res[df_res["rpm_media"] <= UMBRAL_RPM]
    gira = df_res[df_res["rpm_media"] > UMBRAL_RPM]
    lin = gira[gira["duty_cmd"] <= DUTY_MAX_LINEAL]
    nolin = gira[gira["duty_cmd"] > DUTY_MAX_LINEAL]

    ax.set_xlim(0, 95)
    ax.set_ylim(-8, 125)
    ax.yaxis.set_major_locator(MultipleLocator(25))
    ax.xaxis.set_major_locator(MultipleLocator(20))
    _ejes(ax)

    # Región sin movimiento
    ax.axvspan(0, ident["u_arranque"], color=GRIS_FONDO, zorder=1)
    ax.text(ident["u_arranque"] / 2, 72, "Rotor\ndetenido",
            ha="center", va="center", fontsize=6.8, color=GRIS,
            style="italic", linespacing=1.4, zorder=2)

    # Recta de régimen
    x_ext = np.linspace(ident["u_0"], ident["u_arranque"], 50)
    ax.plot(x_ext, ident["K"] * (x_ext - ident["u_0"]), "--",
            color=AZUL, lw=0.9, alpha=0.55, zorder=3)
    x = np.linspace(ident["u_arranque"], DUTY_MAX_LINEAL, 100)
    ax.plot(x, ident["K"] * (x - ident["u_0"]), "-",
            color=AZUL, lw=1.2, zorder=3, label="Ajuste de régimen")

    # Salto de arranque
    ax.annotate("", xy=(ident["u_arranque"], ident["w_salto"]),
                xytext=(ident["u_arranque"], 0),
                arrowprops=dict(arrowstyle="-|>", color=ROJO, lw=1.0,
                                mutation_scale=7, shrinkA=0, shrinkB=1),
                zorder=4)
    ax.text(ident["u_arranque"] + 2.5, ident["w_salto"] * 0.5,
            f"Salto\n{ident['w_salto']:.1f} rpm", fontsize=6.6,
            color=ROJO, va="center", linespacing=1.35, zorder=4)

    # Datos
    ax.plot(quieto["duty_cmd"], quieto["rpm_media"], "o", mfc="white",
            mec=TINTA, mew=0.8, ms=3.6, zorder=5, ls="none",
            label="Sin movimiento")
    ax.plot(lin["duty_cmd"], lin["rpm_media"], "o", color=ROJO,
            mec=TINTA, mew=0.5, ms=3.8, zorder=5, ls="none",
            label="Régimen lineal")
    ax.plot(nolin["duty_cmd"], nolin["rpm_media"], "^", color=VERDE,
            mec=TINTA, mew=0.5, ms=4.0, zorder=5, ls="none",
            label="Fuera de ajuste")

    ax.set_ylabel(r"Velocidad angular  $\omega$  (rpm)")
    plt.setp(ax.get_xticklabels(), visible=False)

    txt = (f"$u_{{\\mathrm{{arr}}}} = {ident['u_arranque']:.0f}$ %\n"
           f"$u_0 = {ident['u_0']:.2f}$ %\n"
           f"$K = {ident['K']:.3f}$ rpm/%\n"
           f"$R^2 = {ident['r2']:.4f}$")
    ax.text(0.955, 0.045, txt, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=6.8, linespacing=1.55,
            zorder=6,
            bbox=dict(boxstyle="square,pad=0.45", fc="white",
                      ec=TINTA, lw=0.7))

    _leyenda(ax, loc="upper left", bbox_to_anchor=(0.025, 0.98))

    # Residuos
    lim = max(1.4 * np.abs(ident["resid"]).max(), 0.6)
    axr.set_ylim(-lim, lim)
    axr.yaxis.set_major_locator(MultipleLocator(round(lim / 2, 1)))
    _ejes(axr)

    axr.axhspan(-ident["rmse"], ident["rmse"], color=AZUL,
                alpha=0.10, lw=0, zorder=1)
    axr.axhline(0, color=AZUL, lw=1.0, ls="-", zorder=2)
    axr.plot(ident["duty_ajuste"], ident["resid"], "o", color=ROJO,
             mec=TINTA, mew=0.5, ms=3.6, ls="none", zorder=4)

    axr.set_xlabel(r"Ciclo útil comandado  $u$  (%)")
    axr.set_ylabel("Residuo\n(rpm)", fontsize=7.5, linespacing=1.35)
    axr.text(0.955, 0.88, f"RMSE = {ident['rmse']:.3f} rpm",
             transform=axr.transAxes, ha="right", va="top",
             fontsize=6.6, color=TINTA)

    _panel(ax, "(a)")
    _panel(axr, "(b)")

    Path(salida).parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(salida)
    fig.savefig(salida.replace(".pdf", ".png"))
    plt.close(fig)


# ---------------------------------------------------------------
# FIGURA 2
# ---------------------------------------------------------------
def fig_metrologia(df_res, salida="docs/fig02_metrologia.pdf"):
    g = df_res[df_res["rpm_media"] > UMBRAL_RPM]

    fig, axes = plt.subplots(1, 3, figsize=(COL_DOBLE, 60 * MM))
    ax1, ax2, ax3 = axes
    fig.subplots_adjust(wspace=0.30, left=0.065, right=0.985,
                        top=0.90, bottom=0.21)

    # (a) Dispersión absoluta
    ax1.plot(g["rpm_media"], g["rpm_std"], "-o", color=AZUL,
             mec=TINTA, mew=0.5, ms=3.8, lw=1.1, zorder=4)
    ax1.set_xlabel(r"Velocidad angular  $\omega$  (rpm)")
    ax1.set_ylabel(r"Desviación estándar  $\sigma_\omega$  (rpm)")
    ax1.set_ylim(0, None)
    _ejes(ax1)

    # (b) Incertidumbre relativa vs cota teórica
    sigma_conteo = 60.0 / (PPR * TS * np.sqrt(12))
    w = np.linspace(g["rpm_media"].min(), g["rpm_media"].max(), 200)

    ax2.set_yscale("log")
    ax2.set_ylim(0.1, 30)
    ax2.fill_between(w, 100 * sigma_conteo / w, 30,
                     color=ROJO, alpha=0.07, lw=0, zorder=1)
    ax2.plot(w, 100 * sigma_conteo / w, "--", color=ROJO, lw=1.2,
             zorder=3, label="Conteo por ventana fija\n(cota teórica)")
    ax2.plot(g["rpm_media"], 100 * g["rpm_std"] / g["rpm_media"], "-o",
             color=AZUL, mec=TINTA, mew=0.5, ms=3.8, lw=1.1, zorder=4,
             label="Método M/T (medido)")

    ax2.set_xlabel(r"Velocidad angular  $\omega$  (rpm)")
    ax2.set_ylabel(r"Incertidumbre relativa  $\sigma_\omega/\omega$  (%)")
    _leyenda(ax2, loc="upper right")
    ax2.grid(True, which="major", axis="both", zorder=0)
    ax2.xaxis.set_minor_locator(AutoMinorLocator(2))
    for s in ax2.spines.values():
        s.set_linewidth(0.7)

    # (c) Densidad de flancos
    ax3.plot(g["rpm_media"], g["n_flancos_media"], "-s", color=VERDE,
             mec=TINTA, mew=0.5, ms=3.8, lw=1.1, zorder=4)
    ax3.axhline(1, color=ROJO, ls="-.", lw=1.0, zorder=2)
    ax3.text(0.96, 0.08, "Un flanco por $T_s$", transform=ax3.transAxes,
             ha="right", fontsize=6.8, color=ROJO)
    ax3.set_xlabel(r"Velocidad angular  $\omega$  (rpm)")
    ax3.set_ylabel(r"Flancos por ventana  $T_s$")
    ax3.set_ylim(0, None)
    _ejes(ax3)

    for ax, l in zip(axes, ["(a)", "(b)", "(c)"]):
        _panel(ax, l, dx=-0.21)

    Path(salida).parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(salida)
    fig.savefig(salida.replace(".pdf", ".png"))
    plt.close(fig)


# ---------------------------------------------------------------
def main(base: str):
    df_res = pd.read_parquet(f"{base}_resumen.parquet")
    df_crudo = pd.read_parquet(f"{base}_crudo.parquet")

    ident = identificar(df_res)
    kf_R = estimar_kf_R(df_crudo)
    sigma_conteo = 60.0 / (PPR * TS * np.sqrt(12))

    print("=" * 58)
    print("IDENTIFICACION DE LA PLANTA")
    print("=" * 58)
    print("  Umbral de movimiento")
    print(f"    Ultimo duty sin giro : {ident['ultimo_quieto']:.0f} %")
    print(f"    Primer duty con giro : {ident['u_arranque']:.0f} %")
    print(f"    Salto de velocidad   : {ident['w_salto']:.2f} rpm")
    print()
    print("  Regimen lineal")
    print(f"    Ganancia K           : {ident['K']:.4f} +/- "
          f"{ident['err_K']:.4f} rpm/%")
    print(f"    Intercepto u_0       : {ident['u_0']:.2f} %")
    print(f"    R^2                  : {ident['r2']:.5f}")
    print(f"    RMSE                 : {ident['rmse']:.4f} rpm")
    print()
    print("  Metrologia de la medicion")
    print(f"    kf_R                 : {kf_R:.4f} rpm^2")
    print(f"    sigma M/T            : {np.sqrt(kf_R):.4f} rpm")
    print(f"    sigma conteo (teor.) : {sigma_conteo:.4f} rpm")
    print(f"    Factor de mejora     : {sigma_conteo/np.sqrt(kf_R):.2f}x")
    print()
    print("  PENDIENTE: tau (ensayo de escalon) -> mod_a, mod_b")
    print("=" * 58)

    fig_caracteristica(df_res, ident)
    fig_metrologia(df_res)
    print("\nFiguras: docs/fig01_caracteristica.{pdf,png}")
    print("         docs/fig02_metrologia.{pdf,png}")

    return ident, kf_R


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: uv run python -m observador.identificacion <ruta_base>")
        sys.exit(1)
    main(sys.argv[1])