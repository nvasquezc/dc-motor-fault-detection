"""
Figuras del ensayo de escalon.

Fig 3: respuestas temporales, residuos del ajuste y dependencia
       de tau con el punto de operacion.

Jitter Ingenieria SAS
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import AutoMinorLocator, MultipleLocator
from scipy import stats

from observador.escalon import modelo_escalon
from observador.identificacion import (
    AZUL, GRIS, GRIS_CLARO, MAGENTA, ROJO, TINTA, VERDE,
    COL_DOBLE, COL_SIMPLE, MM, _ejes, _leyenda, _panel,
)

# Estilo por amplitud: color + linea + marcador
ESTILOS = {
    40: (AZUL, "-", "o"),
    55: (ROJO, "--", "s"),
    70: (VERDE, "-.", "^"),
}


def fig_escalon(df_crudo, df_res, salida="docs/fig03_escalon.pdf"):
    fig = plt.figure(figsize=(COL_DOBLE, 66 * MM))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1],
                          height_ratios=[2.3, 1],
                          hspace=0.14, wspace=0.26,
                          left=0.065, right=0.985,
                          top=0.92, bottom=0.13)
    ax = fig.add_subplot(gs[0, 0])
    axr = fig.add_subplot(gs[1, 0], sharex=ax)
    axt = fig.add_subplot(gs[:, 1])

    # ---------- (a) Respuestas temporales ----------
    for duty, (col, ls, mk) in ESTILOS.items():
        sub = df_crudo[(df_crudo["duty_cmd"] == duty) &
                       (df_crudo["rep"] == 1)]
        if sub.empty:
            continue
        r = df_res[(df_res["duty_cmd"] == duty) &
                   (df_res["rep"] == 1)].iloc[0]

        t = sub["t_rel"].values
        w = sub["w_raw"].abs().values
        t_sh = t - r["t0"]

        # Datos: submuestreo para no saturar el trazo
        ax.plot(t_sh[::3], w[::3], mk, color=col, mec=TINTA, mew=0.35,
                ms=2.6, ls="none", alpha=0.55, zorder=3)
        # Ajuste
        tf = np.linspace(0, t_sh.max(), 400)
        ax.plot(tf, r["w_ss"] * (1 - np.exp(-tf / r["tau"])), ls,
                color=col, lw=1.3, zorder=4,
                label=fr"$u={duty}$ %,  $\tau={r['tau']*1000:.1f}$ ms")

        # Marca del 63.2 %
        ax.plot([r["tau"]], [0.632 * r["w_ss"]], "o", mfc="white",
                mec=col, mew=1.0, ms=4.5, zorder=6)

    ax.axhline(0, color=GRIS_CLARO, lw=0.5, zorder=1)
    ax.set_xlim(-0.05, 1.0)
    ax.set_ylim(-3, 82)
    ax.xaxis.set_major_locator(MultipleLocator(0.2))
    ax.yaxis.set_major_locator(MultipleLocator(20))
    ax.set_ylabel(r"Velocidad angular  $\omega$  (rpm)")
    plt.setp(ax.get_xticklabels(), visible=False)
    _ejes(ax)
    _leyenda(ax, loc="lower right", bbox_to_anchor=(0.985, 0.04))

    ax.text(0.03, 0.94, r"$\circ$  marca en $63.2\,\%$ de $\omega_{ss}$",
            transform=ax.transAxes, fontsize=6.5, color=GRIS, va="top")

    # ---------- (b) Residuos ----------
    for duty, (col, ls, mk) in ESTILOS.items():
        sub = df_crudo[(df_crudo["duty_cmd"] == duty) &
                       (df_crudo["rep"] == 1)]
        if sub.empty:
            continue
        r = df_res[(df_res["duty_cmd"] == duty) &
                   (df_res["rep"] == 1)].iloc[0]
        t = sub["t_rel"].values
        w = sub["w_raw"].abs().values
        res = w - modelo_escalon(t, r["w_ss"], r["tau"], r["t0"])
        axr.plot(t[::3] - r["t0"], res[::3], mk, color=col, mec=TINTA,
                 mew=0.3, ms=2.2, ls="none", alpha=0.6, zorder=3)

    axr.axhline(0, color=TINTA, lw=0.8, zorder=2)
    axr.set_ylim(-3.2, 3.2)
    axr.yaxis.set_major_locator(MultipleLocator(2))
    axr.set_xlabel(r"Tiempo desde el escalón  $t-t_0$  (s)")
    axr.set_ylabel("Residuo\n(rpm)", fontsize=7.5, linespacing=1.3)
    _ejes(axr)

    # ---------- (c) tau vs punto de operacion ----------
    g = df_res.groupby("duty_cmd")
    w_m = g["w_ss"].mean()
    t_m = g["tau"].mean() * 1000
    t_s = g["tau"].std() * 1000

    reg = stats.linregress(w_m, t_m)
    xf = np.linspace(w_m.min() * 0.92, w_m.max() * 1.06, 50)
    axt.plot(xf, reg.slope * xf + reg.intercept, "-", color=GRIS,
             lw=1.0, zorder=3)

    for duty, (col, ls, mk) in ESTILOS.items():
        if duty not in w_m.index:
            continue
        axt.errorbar(w_m[duty], t_m[duty], yerr=t_s[duty],
                     fmt=mk, color=col, mec=TINTA, mew=0.5, ms=5,
                     capsize=2.5, elinewidth=0.8, zorder=5)
        # Puntos individuales
        sub = df_res[df_res["duty_cmd"] == duty]
        axt.plot(sub["w_ss"], sub["tau"] * 1000, mk, color=col,
                 ms=2.4, alpha=0.35, ls="none", zorder=4)

    axt.set_xlabel(r"Velocidad de régimen  $\omega_{ss}$  (rpm)")
    axt.set_ylabel(r"Constante de tiempo  $\tau$  (ms)")
    axt.set_xlim(30, 80)
    axt.set_ylim(20, 70)
    axt.xaxis.set_major_locator(MultipleLocator(10))
    axt.yaxis.set_major_locator(MultipleLocator(10))
    _ejes(axt)

    axt.text(0.05, 0.95,
             f"$d\\tau/d\\omega = {reg.slope:.3f}$ ms/rpm\n"
             f"$R^2 = {reg.rvalue**2:.3f}$",
             transform=axt.transAxes, fontsize=6.8, va="top",
             linespacing=1.5,
             bbox=dict(boxstyle="square,pad=0.4", fc="white",
                       ec=TINTA, lw=0.7))

    axt.text(0.96, 0.06,
             "Modelo LTI\nrequiere $\\tau$ constante",
             transform=axt.transAxes, fontsize=6.3, color=ROJO,
             ha="right", va="bottom", style="italic", linespacing=1.4)

    _panel(ax, "(a)", dx=-0.115)
    _panel(axr, "(b)", dx=-0.115)
    _panel(axt, "(c)", dx=-0.21)

    Path(salida).parent.mkdir(exist_ok=True, parents=True)
    fig.savefig(salida)
    fig.savefig(salida.replace(".pdf", ".png"))
    plt.close(fig)


def main(base: str):
    df_crudo = pd.read_parquet(f"{base}_crudo.parquet")
    df_res = pd.read_parquet(f"{base}_resumen.parquet")

    reg = stats.linregress(df_res["w_ss"], df_res["tau"] * 1000)

    print("=" * 58)
    print("DEPENDENCIA DE tau CON EL PUNTO DE OPERACION")
    print("=" * 58)
    for duty, sub in df_res.groupby("duty_cmd"):
        print(f"  {duty:3d} %  ->  w_ss = {sub['w_ss'].mean():5.1f} rpm,"
              f"  tau = {sub['tau'].mean()*1000:5.2f}"
              f" +/- {sub['tau'].std()*1000:4.2f} ms")
    print()
    print(f"  Pendiente  : {reg.slope:.4f} ms/rpm")
    print(f"  R^2        : {reg.rvalue**2:.4f}")
    print(f"  p-valor    : {reg.pvalue:.2e}")
    print()
    print("  El amortiguamiento efectivo B_ef = J/tau decrece con la")
    print("  velocidad, consistente con friccion de Stribeck.")
    print("=" * 58)

    fig_escalon(df_crudo, df_res)
    print("\nFigura: docs/fig03_escalon.{pdf,png}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: uv run python -m observador.figuras_escalon <ruta_base>")
        sys.exit(1)
    main(sys.argv[1])