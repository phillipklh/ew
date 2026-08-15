"""Aufzaehlung regelkonformer Wellenlabelings ueber das Pivot-Lattice.

Der zentrale Punkt: zu jedem Zeitpunkt gibt es viele regelkonforme Zaehlungen,
nicht eine. Wer eine einzelne "richtige" sucht, trifft am Ende eine
willkuerliche Wahl und nennt sie Analyse. Dieses Modul zaehlt stattdessen alle
zulaessigen auf; die Gewichtung uebernimmt das Scoring.

Zwei Bausteine:

*Vollstaendige Muster* dienen dem Lernen der Richtlinien-Verteilungen
(Retracements, Extensions, Zeitverhaeltnisse) - dafuer braucht es
abgeschlossene Strukturen.

*Unvollstaendige Muster* sind die eigentlich handelbaren. Ein Setup entsteht
nicht, wenn ein Impuls fertig ist, sondern wenn Welle 1 und 2 stehen und
Welle 3 bevorsteht. Genau diese Hypothesen tragen Invalidierung und Ziel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..pivots.lattice import Lattice
from ..pivots.zigzag import Pivot
from ..rules import geometry as g
from ..rules.patterns import (
    SUBDIVISION,
    WAVE_COUNT,
    Check,
    Config,
    PatternType,
    check as check_pattern,
)


@dataclass
class Labeling:
    """Ein regelkonformes Labeling einer Pivot-Folge."""

    pattern: PatternType
    pivots: list[Pivot]
    scale: int
    check: Check
    #: Anteil der Wellen, deren Substruktur der erwarteten Unterteilung
    #: entspricht. Die Top-down-Analyse mit Bottom-up-Bestaetigung.
    substructure: float = 0.0
    sub_detail: list[tuple[int, int]] = field(default_factory=list)

    @property
    def confirmed_idx(self) -> int:
        """Bar, ab der dieses Labeling ueberhaupt bekannt sein kann."""
        return g.confirmed_at(self.pivots)

    @property
    def start_idx(self) -> int:
        return self.pivots[0].idx

    @property
    def end_idx(self) -> int:
        return self.pivots[-1].idx

    @property
    def notes(self) -> list[str]:
        return self.check.notes

    def __repr__(self) -> str:
        return (
            f"<{self.pattern.value} s{self.scale} "
            f"[{self.start_idx}..{self.end_idx}] sub={self.substructure:.0%}>"
        )


# --------------------------------------------------------------------------
# Substruktur
# --------------------------------------------------------------------------

def subwave_count(lat: Lattice, scale: int, a: Pivot, b: Pivot) -> int:
    """Anzahl Unterwellen zwischen zwei Pivots auf der naechstfeineren Ebene."""
    if scale <= 0:
        return 0
    inner = [p for p in lat.pivots(scale - 1) if a.idx < p.idx < b.idx]
    return len(inner) + 1


def best_subwave_count(
    lat: Lattice, scale: int, a: Pivot, b: Pivot, expected: int, depth: int = 3
) -> tuple[int, int]:
    """Sucht die feinere Ebene, auf der die Welle am besten aufgeloest ist.

    Eine Welle loest sich nicht zwingend genau eine Ebene tiefer in ihre
    Unterwellen auf: eine kurze Welle 4 kann zwei Ebenen tiefer liegen als
    eine ausgedehnte Welle 3. Ein starres Ebene-minus-eins waere deshalb
    genau die Starrheit, die die Praxis widerlegt. Gesucht wird die Ebene,
    deren Wellenzahl der Erwartung am naechsten kommt.
    """
    best = (scale - 1, 0)
    best_err = None
    for s in range(scale - 1, max(scale - 1 - depth, -1), -1):
        inner = [p for p in lat.pivots(s) if a.idx < p.idx < b.idx]
        n = len(inner) + 1
        err = abs(n - expected)
        if best_err is None or err < best_err:
            best, best_err = (s, n), err
        if err == 0:
            break
    return best


def substructure_score(
    lat: Lattice, scale: int, pattern: PatternType, pivots: list[Pivot]
) -> tuple[float, list[tuple[int, int]]]:
    """Wie gut zerfaellt jede Welle in die erwartete Unterteilung?

    Rueckgabe: Anteil passender Wellen und je Welle (Ebene, gefundene Anzahl).
    """
    expected = SUBDIVISION[pattern]
    detail: list[tuple[int, int]] = []
    hits = 0
    for (a, b), exp in zip(zip(pivots, pivots[1:]), expected):
        s, n = best_subwave_count(lat, scale, a, b, exp)
        detail.append((s, n))
        # Eine motive Welle darf sich als 5 oder als erweiterte 9/13 zeigen,
        # eine korrektive als 3 oder als Kombination 7/11 - das sind die
        # zulaessigen Verlaengerungen derselben Struktur.
        allowed = (5, 9, 13) if exp == 5 else (3, 7, 11)
        if n in allowed:
            hits += 1
    return hits / len(expected), detail


# --------------------------------------------------------------------------
# Aufzaehlung
# --------------------------------------------------------------------------

def enumerate_complete(
    lat: Lattice,
    scale: int,
    cfg: Config = Config(),
    *,
    up_to_bar: int | None = None,
    patterns: tuple[PatternType, ...] | None = None,
) -> list[Labeling]:
    """Alle regelkonformen, abgeschlossenen Muster auf einer Ebene.

    `up_to_bar` erzwingt Kausalitaet: es werden nur Pivots verwendet, die zu
    diesem Zeitpunkt bereits bestaetigt sind.
    """
    piv = (
        lat.visible_at(scale, up_to_bar) if up_to_bar is not None else lat.pivots(scale)
    )
    piv = [p for p in piv if not p.is_anchor]
    types = patterns or tuple(PatternType)

    out: list[Labeling] = []
    for ptype in types:
        need = WAVE_COUNT[ptype] + 1
        for i in range(len(piv) - need + 1):
            window = piv[i : i + need]
            res = check_pattern(ptype, window, cfg)
            if not res.ok:
                continue
            sub, detail = substructure_score(lat, scale, ptype, window)
            out.append(Labeling(ptype, window, scale, res, sub, detail))
    return out


@dataclass
class Hypothesis:
    """Ein laufendes, noch unvollstaendiges Muster.

    Traegt alles, was ein Signal braucht: was bisher da ist, welche Welle
    als naechstes erwartet wird, und ab welchem Preis die Zaehlung
    regelwidrig - also widerlegt - waere.
    """

    pattern: PatternType
    pivots: list[Pivot]  # bereits bestaetigte Pivots
    scale: int
    next_wave: int  # 1-basiert: welche Welle laeuft gerade
    invalidation: float  # Preis, ab dem die Hypothese verletzt ist
    direction: int  # Richtung der laufenden Welle

    @property
    def confirmed_idx(self) -> int:
        return g.confirmed_at(self.pivots)

    def is_alive(self, high: float, low: float) -> bool:
        """Lebt die Hypothese noch, gegeben ein Preisextrem?"""
        if self.direction > 0:
            return low > self.invalidation
        return high < self.invalidation

    def __repr__(self) -> str:
        return (
            f"<{self.pattern.value} s{self.scale} W{self.next_wave} "
            f"dir={'+' if self.direction > 0 else '-'} inv={self.invalidation:.6g}>"
        )


def enumerate_in_progress(
    lat: Lattice,
    scale: int,
    up_to_bar: int,
    cfg: Config = Config(),
) -> list[Hypothesis]:
    """Laufende Impuls-Hypothesen zum Zeitpunkt `up_to_bar`.

    Beschraenkt auf die beiden handelbaren Konstellationen des Impulses:

      nach Welle 2 -> Welle 3 steht bevor. Invalidierung: der Start von
      Welle 1, denn Welle 2 darf ihn nie unterschreiten.

      nach Welle 4 -> Welle 5 steht bevor. Invalidierung: das Ende von
      Welle 1, denn Welle 4 darf nicht ueberlappen.

    Das sind genau die Punkte, an denen die Regel selbst den Stop liefert -
    der Grund, warum Elliott-Setups strukturell enge Verlustbegrenzungen
    haben und der durchschnittliche Verlust deutlich unter 1R bleiben kann.
    """
    piv = [p for p in lat.visible_at(scale, up_to_bar) if not p.is_anchor]
    out: list[Hypothesis] = []

    # Nach Welle 2: die letzten drei Pivots bilden 0-1-2.
    if len(piv) >= 3:
        p0, p1, p2 = piv[-3:]
        d = 1 if p1.price > p0.price else -1
        if g.beyond(p2.price, p0.price, d) and abs(p1.price - p0.price) > 0:
            out.append(Hypothesis(PatternType.IMPULSE, [p0, p1, p2], scale, 3,
                                  p0.price, d))

    # Nach Welle 4: die letzten fuenf Pivots bilden 0-1-2-3-4.
    if len(piv) >= 5:
        p0, p1, p2, p3, p4 = piv[-5:]
        d = 1 if p1.price > p0.price else -1
        partial_ok = (
            g.beyond(p2.price, p0.price, d)
            and g.beyond(p3.price, p1.price, d)
            and g.beyond(p4.price, p2.price, d)
        )
        overlap = (p1.price - p4.price) if d > 0 else (p4.price - p1.price)
        w1 = abs(p1.price - p0.price)
        if partial_ok and w1 > 0 and overlap / w1 <= cfg.overlap_tol:
            out.append(Hypothesis(PatternType.IMPULSE, [p0, p1, p2, p3, p4], scale, 5,
                                  p1.price, d))

    return out
