"""Chart-Rendering fuer visuelles Audit.

Ohne visuelle Pruefbarkeit vertraut niemand einem Wellenzaehler - zu Recht.
Diese Charts sind deshalb kein Nice-to-have, sondern der Weg, wie ein
Analyst stichprobenartig gegenprueft, ob das System plausibel zaehlt.

Die Darstellung unterscheidet bewusst zwischen dem Extrempunkt (Marker) und
dem Bestaetigungszeitpunkt (Schatten), damit die Verzoegerung sichtbar bleibt
statt kaschiert zu werden.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from ..pivots.lattice import Lattice  # noqa: E402

# Haendlerkonvention: Hochpunkte rot (Verkaufsseite), Tiefpunkte gruen (Kaufseite).
_HIGH = "#d73027"
_LOW = "#1a9850"
_LINE = "#37474f"
_MUTED = "#90a4ae"


def plot_pivots(
    df: pd.DataFrame,
    lat: Lattice,
    scales: list[int],
    *,
    title: str = "",
    out: Path | str | None = None,
    show_confirmation: bool = True,
    last_n: int | None = None,
    figsize: tuple[float, float] = (16, 9),
):
    """Zeichnet Kurs plus Pivot-Polygonzug fuer eine oder mehrere Ebenen."""
    if last_n:
        df = df.iloc[-last_n:]
    lo_ts, hi_ts = df.index[0], df.index[-1]

    fig, axes = plt.subplots(
        len(scales), 1, figsize=figsize, sharex=True, squeeze=False,
        gridspec_kw={"hspace": 0.12},
    )
    axes = axes.ravel()

    for ax, scale in zip(axes, scales):
        ax.plot(df.index, df["close"], color=_MUTED, lw=0.7, zorder=1)

        piv = [p for p in lat.pivots(scale)
               if lo_ts <= lat.index[p.idx] <= hi_ts]
        if piv:
            xs = [lat.index[p.idx] for p in piv]
            ys = [p.price for p in piv]
            ax.plot(xs, ys, color=_LINE, lw=1.4, zorder=2)

            for p in piv:
                x, y = lat.index[p.idx], p.price
                is_high = p.kind > 0
                col = _HIGH if is_high else _LOW
                ax.scatter([x], [y], s=34, zorder=4, color=col,
                           marker="v" if is_high else "^")
                if show_confirmation and p.confirmed_idx < len(lat.index):
                    cx = lat.index[p.confirmed_idx]
                    if cx <= hi_ts:
                        ax.plot([x, cx], [y, y], color=col,
                                lw=0.8, ls=":", alpha=0.55, zorder=3)

        lag = [p.lag for p in piv]
        med = f"{pd.Series(lag).median():.0f}" if lag else "-"
        ax.set_ylabel(f"Ebene {scale}\nθ={lat.thetas[scale]} ATR", fontsize=9)
        ax.text(
            0.005, 0.96, f"{len(piv)} Pivots · Median-Lag {med} Bars",
            transform=ax.transAxes, va="top", fontsize=8, color="#546e7a",
        )
        ax.grid(alpha=0.15, lw=0.5)
        ax.set_yscale("log")
        ax.tick_params(labelsize=8)

    axes[0].set_title(title or "Pivot-Lattice", fontsize=11, loc="left")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return Path(out)
    return fig
