"""Multi-Scale-Pivot-Lattice.

Die Frage "welcher ZigZag-Schwellwert ist der richtige?" hat keine Antwort,
weil Elliott-Wellen fraktal sind - jede Skala ist gleichermassen real. Statt
zu waehlen, haelt das Lattice alle Skalen gleichzeitig und ueberlaesst die
Auswahl der Regel-Engine, die dort ansetzt, wo die Regeln am besten passen.

Zwei Konsequenzen:

*Zyklusgrad* ist eine Ebene in diesem Baum, relativ vergeben ueber
Verschachtelung - nicht an einen Timeframe gekoppelt. Genau die Flexibilitaet,
die die Praxis verlangt.

*Das Multi-Timeframe-Problem verschwindet.* Wenn der Wochen-Pivot einen
anderen Preis hat als der Daily-Pivot, ist das ein Artefakt des Resamplings.
Hier werden Pivots genau einmal auf der feinsten Serie berechnet; eine
groebere Ebene ist eine Teilmenge davon und hat damit zwangslaeufig exakt
denselben Preis und Zeitpunkt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import atr as compute_atr
from .zigzag import Pivot, to_frame, zigzag_from_bars, zigzag_from_pivots

# Geometrische Leiter in ATR-Einheiten (Verhaeltnis ~1.5). Die Spanne deckt
# vom Intraday-Rauschen bis zum mehrjaehrigen Zyklus alles ab, was in einer
# typischen Historie ueberhaupt aufloesbar ist.
DEFAULT_THETAS: tuple[float, ...] = (0.5, 0.75, 1.1, 1.6, 2.4, 3.6, 5.4, 8.1)


@dataclass
class Lattice:
    """Hierarchie verschachtelter Pivot-Mengen."""

    levels: dict[int, list[Pivot]] = field(default_factory=dict)
    thetas: tuple[float, ...] = DEFAULT_THETAS
    index: pd.DatetimeIndex | None = None

    @property
    def n_levels(self) -> int:
        return len(self.levels)

    def pivots(self, scale: int) -> list[Pivot]:
        return self.levels.get(scale, [])

    def frame(self, scale: int) -> pd.DataFrame:
        return to_frame(self.pivots(scale), self.index)

    def visible_at(self, scale: int, bar_idx: int) -> list[Pivot]:
        """Alle Pivots, die zum Zeitpunkt `bar_idx` bereits bestaetigt sind.

        Der einzige zulaessige Zugriff fuer Backtest und Live-Betrieb. Wer
        stattdessen `pivots()` verwendet, sieht in die Zukunft.
        """
        return [p for p in self.pivots(scale) if p.confirmed_idx <= bar_idx]

    def reversals(self, scale: int) -> list[Pivot]:
        """Nur echte Wendepunkte, ohne den Bootstrap-Anker der Serie."""
        return [p for p in self.pivots(scale) if not p.is_anchor]

    def children(self, scale: int, start: Pivot, end: Pivot) -> list[Pivot]:
        """Feinere Pivots strikt zwischen zwei Pivots der Ebene darueber.

        Das ist die Substruktur einer Welle - die Grundlage dafuer, zu pruefen,
        ob sich eine als Impuls gelabelte Welle tatsaechlich in fuenf
        Unterwellen zerlegt.
        """
        if scale <= 0:
            return []
        return [
            p for p in self.pivots(scale - 1)
            if start.idx < p.idx < end.idx
        ]

    def summary(self) -> pd.DataFrame:
        rows = []
        for s in sorted(self.levels):
            ps = self.levels[s]
            lags = [p.lag for p in ps]
            rows.append(
                {
                    "scale": s,
                    "theta_atr": self.thetas[s],
                    "n_pivots": len(ps),
                    "median_lag_bars": float(np.median(lags)) if lags else np.nan,
                    "mean_bars_between": (
                        float(np.mean(np.diff([p.idx for p in ps]))) if len(ps) > 1 else np.nan
                    ),
                }
            )
        return pd.DataFrame(rows)


def build(
    df: pd.DataFrame,
    thetas: tuple[float, ...] = DEFAULT_THETAS,
    atr_period: int = 14,
) -> Lattice:
    """Baut das Lattice aus einem normalisierten OHLCV-Frame.

    Ebene 0 laeuft auf den Bars, jede weitere Ebene vergroebert die vorige.
    Dadurch gilt strikt: pivots(k+1) ist Teilmenge von pivots(k).
    """
    atr_arr = compute_atr(df, atr_period).to_numpy("float64")
    high = df["high"].to_numpy("float64")
    low = df["low"].to_numpy("float64")

    levels: dict[int, list[Pivot]] = {}
    levels[0] = zigzag_from_bars(high, low, atr_arr, thetas[0], scale=0)

    for k in range(1, len(thetas)):
        prev = levels[k - 1]
        if len(prev) < 2:
            levels[k] = []
            continue
        levels[k] = zigzag_from_pivots(prev, atr_arr, thetas[k], scale=k)

    return Lattice(levels=levels, thetas=thetas, index=df.index)


def verify_nesting(lat: Lattice) -> list[str]:
    """Prueft die Verschachtelungseigenschaft.

    Verletzungen waeren ein Implementierungsfehler, kein Marktphaenomen -
    deshalb ist das ein Test, kein Warnhinweis.
    """
    problems: list[str] = []
    for k in range(1, lat.n_levels):
        coarse = lat.pivots(k)
        fine = {(p.idx, p.kind) for p in lat.pivots(k - 1)}
        for p in coarse:
            if (p.idx, p.kind) not in fine:
                problems.append(
                    f"Ebene {k}: Pivot idx={p.idx} kind={p.kind} fehlt in Ebene {k-1}"
                )
    return problems


def verify_causality(lat: Lattice) -> list[str]:
    """Prueft, dass kein Pivot vor seinem Extremwert bestaetigt wird."""
    problems: list[str] = []
    for k in range(lat.n_levels):
        for p in lat.pivots(k):
            if p.confirmed_idx < p.idx:
                problems.append(
                    f"Ebene {k}: Pivot idx={p.idx} bestaetigt bei {p.confirmed_idx}"
                )
    return problems


def verify_alternation(lat: Lattice) -> list[str]:
    """Prueft, dass sich Hoch- und Tiefpunkte strikt abwechseln."""
    problems: list[str] = []
    for k in range(lat.n_levels):
        ps = lat.pivots(k)
        for a, b in zip(ps, ps[1:]):
            if a.kind == b.kind:
                problems.append(f"Ebene {k}: zwei gleiche Pivot-Typen bei {a.idx}/{b.idx}")
            if b.idx <= a.idx:
                problems.append(f"Ebene {k}: Reihenfolge verletzt bei {a.idx}/{b.idx}")
    return problems
