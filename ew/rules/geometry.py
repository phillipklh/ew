"""Geometrische Grundgroessen einer Wellenfolge.

Eine Wellenfolge ist eine Liste alternierender Pivots. n Wellen brauchen
n+1 Pivots. Alle Groessen hier sind reine Preis-/Zeitarithmetik ohne jede
Interpretation - die Regeln setzen darauf auf.
"""

from __future__ import annotations

import numpy as np

from ..pivots.zigzag import Pivot


def lengths(pivots: list[Pivot]) -> list[float]:
    """Absolute Preisstrecke jeder Welle."""
    return [abs(b.price - a.price) for a, b in zip(pivots, pivots[1:])]


def durations(pivots: list[Pivot]) -> list[int]:
    """Dauer jeder Welle in Bars."""
    return [b.idx - a.idx for a, b in zip(pivots, pivots[1:])]


def log_lengths(pivots: list[Pivot]) -> list[float]:
    """Preisstrecke im Log-Raum.

    Ueber lange Historien mit Vervielfachung des Kursniveaus (BTC von 3k auf
    120k) ist der arithmetische Vergleich zweier Wellen irrefuehrend: eine
    spaete Welle wirkt allein durch das Niveau riesig. Das Buch formuliert
    die Regel "Welle 3 ist nie die kuerzeste" ausdruecklich prozentual.
    """
    return [abs(np.log(b.price) - np.log(a.price)) for a, b in zip(pivots, pivots[1:])]


def direction(pivots: list[Pivot]) -> int:
    """Richtung der ersten Welle: +1 aufwaerts, -1 abwaerts."""
    return 1 if pivots[1].price > pivots[0].price else -1


def alternates(pivots: list[Pivot]) -> bool:
    """Prueft, dass sich Hoch- und Tiefpunkte strikt abwechseln."""
    return all(a.kind != b.kind for a, b in zip(pivots, pivots[1:]))


def monotonic_time(pivots: list[Pivot]) -> bool:
    return all(a.idx < b.idx for a, b in zip(pivots, pivots[1:]))


def retracement(pivots: list[Pivot], i: int) -> float:
    """Anteil, den Welle i von Welle i-1 zurueckgelegt hat."""
    ls = lengths(pivots)
    prev = ls[i - 1]
    return ls[i] / prev if prev > 0 else np.inf


def beyond(a: float, b: float, d: int) -> bool:
    """Liegt a in Richtung d jenseits von b?"""
    return a > b if d > 0 else a < b


def net_progress(pivots: list[Pivot]) -> float:
    """Netto-Preisfortschritt vom ersten zum letzten Pivot."""
    return pivots[-1].price - pivots[0].price


def confirmed_at(pivots: list[Pivot]) -> int:
    """Bar, ab der das gesamte Muster bekannt ist.

    Das Maximum ueber alle Bestaetigungszeitpunkte - ein Muster existiert
    nicht frueher als sein zuletzt bestaetigter Pivot. Diese Groesse ist der
    einzige zulaessige Zeitstempel fuer Signale aus dem Muster.
    """
    return max(p.confirmed_idx for p in pivots)
