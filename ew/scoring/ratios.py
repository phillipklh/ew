"""Extraktion der Verhaeltniszahlen aus gelabelten Wellen.

Die Elliott-Richtlinien sind im Kern Aussagen ueber Verhaeltnisse: Welle 2
retraciert typischerweise 0.618 von Welle 1, Welle 3 erreicht 1.618 von
Welle 1, und so weiter. Bevor daraus eine Bewertungsfunktion wird, muss
gemessen werden, ob diese Verhaeltnisse in den Daten ueberhaupt haeufiger
auftreten als zufaellig - sonst wird Rauschen optimiert.

Alle Preisverhaeltnisse werden im Log-Raum gebildet. Ueber Historien mit
vervielfachtem Kursniveau ist das arithmetische Verhaeltnis zweier Wellen
sonst vom Niveau dominiert statt von der Struktur.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..labeling.enumerate import Labeling
from ..rules.patterns import PatternType

# Die im Buch genannten Verhaeltnisse.
FIB_RETRACE = (0.236, 0.382, 0.500, 0.618, 0.786)
FIB_EXTEND = (1.000, 1.236, 1.382, 1.618, 2.000, 2.618)


def _log_len(a, b) -> float:
    return abs(np.log(b.price) - np.log(a.price))


def impulse_ratios(lab: Labeling) -> dict[str, float]:
    """Verhaeltniszahlen eines Fuenfwellen-Musters."""
    p = lab.pivots
    w = [_log_len(p[i], p[i + 1]) for i in range(5)]
    t = [p[i + 1].idx - p[i].idx for i in range(5)]

    def safe(a, b):
        return a / b if b > 0 else np.nan

    return {
        "w2_retrace_w1": safe(w[1], w[0]),
        "w4_retrace_w3": safe(w[3], w[2]),
        "w3_ext_w1": safe(w[2], w[0]),
        "w5_ext_w1": safe(w[4], w[0]),
        "w5_ext_w3": safe(w[4], w[2]),
        "t2_t1": safe(t[1], t[0]),
        "t4_t3": safe(t[3], t[2]),
        "t3_t1": safe(t[2], t[0]),
        # Alternation: unterscheiden sich Welle 2 und Welle 4 in der Tiefe?
        # Das Buch fuehrt sie als eigenstaendige Richtlinie.
        "alternation": safe(max(w[1] / w[0], w[3] / w[2]),
                            min(w[1] / w[0], w[3] / w[2])) if w[0] > 0 and w[2] > 0 else np.nan,
    }


def corrective_ratios(lab: Labeling) -> dict[str, float]:
    """Verhaeltniszahlen einer Dreiwellen-Korrektur."""
    p = lab.pivots
    w = [_log_len(p[i], p[i + 1]) for i in range(3)]
    t = [p[i + 1].idx - p[i].idx for i in range(3)]

    def safe(a, b):
        return a / b if b > 0 else np.nan

    return {
        "b_retrace_a": safe(w[1], w[0]),
        "c_ext_a": safe(w[2], w[0]),
        "tb_ta": safe(t[1], t[0]),
        "tc_ta": safe(t[2], t[0]),
    }


FIVE_WAVE = {
    PatternType.IMPULSE,
    PatternType.LEADING_DIAGONAL,
    PatternType.ENDING_DIAGONAL,
}
THREE_WAVE = {PatternType.ZIGZAG, PatternType.FLAT}


def extract(labelings: list[Labeling], *, symbol: str = "", timeframe: str = "") -> pd.DataFrame:
    """Baut eine Tabelle aller Verhaeltniszahlen ueber viele Labelings."""
    rows: list[dict] = []
    for lab in labelings:
        if lab.pattern in FIVE_WAVE:
            r = impulse_ratios(lab)
        elif lab.pattern in THREE_WAVE:
            r = corrective_ratios(lab)
        else:
            continue
        r.update(
            pattern=lab.pattern.value,
            scale=lab.scale,
            substructure=lab.substructure,
            symbol=symbol,
            timeframe=timeframe,
            start_idx=lab.start_idx,
            end_idx=lab.end_idx,
        )
        rows.append(r)
    return pd.DataFrame(rows)


def near_fib(values: np.ndarray, levels: tuple[float, ...], tol: float = 0.05) -> np.ndarray:
    """Boolesche Maske: liegt der Wert innerhalb `tol` (relativ) an einem Level?"""
    v = np.asarray(values, dtype=float)
    hit = np.zeros(len(v), dtype=bool)
    for lvl in levels:
        hit |= np.abs(v - lvl) <= tol * lvl
    return hit


def fib_hit_rate(
    values: np.ndarray, levels: tuple[float, ...], tol: float = 0.05
) -> tuple[float, int]:
    """Anteil der Werte, die nahe an einem Fibonacci-Level liegen."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return float("nan"), 0
    return float(near_fib(v, levels, tol).mean()), len(v)


def coverage(levels: tuple[float, ...], tol: float, lo: float, hi: float) -> float:
    """Anteil des Wertebereichs [lo, hi], den die Toleranzbaender ueberdecken.

    Das ist die Trefferquote, die reiner Zufall erzeugen wuerde - ohne diesen
    Bezugswert ist eine gemessene Trefferquote nicht interpretierbar. Sich
    ueberlappende Baender werden nur einmal gezaehlt.
    """
    intervals = []
    for lvl in levels:
        a, b = lvl * (1 - tol), lvl * (1 + tol)
        a, b = max(a, lo), min(b, hi)
        if b > a:
            intervals.append((a, b))
    if not intervals:
        return 0.0
    intervals.sort()
    merged = [list(intervals[0])]
    for a, b in intervals[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return sum(b - a for a, b in merged) / (hi - lo)
