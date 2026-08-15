"""Harte Elliott-Regeln als pruefbare Praedikate.

Formalisiert nach Frost/Prechter, "The Elliott Wave Principle" (Lessons 4-9).

Die Trennung, auf die es ankommt:

  **Regel**     - gilt ausnahmslos. Eine Verletzung schliesst das Label aus
                  und schneidet den Ast in der Suche ab.
  **Richtlinie**- gilt typischerweise. Sie wird bewertet, nicht erzwungen,
                  und lebt deshalb nicht hier, sondern in `ew.scoring`.

Zwei Stellen, an denen Implementierungen regelmaessig zu streng sind:

1. *Truncation.* Welle 5 darf das Ende von Welle 3 verfehlen. Das Buch
   behandelt das ausdruecklich als zulaessige Variante. "Welle 5 uebertrifft
   Welle 3" ist also Richtlinie, nicht Regel.
2. *Ueberlappung in gehebelten Maerkten.* Die Nicht-Ueberlappung von Welle 4
   und Welle 1 gilt laut Buch fuer Cash-Maerkte; gehebelte Maerkte koennen
   kurzfristige Ausreisser erzeugen. Deshalb `overlap_tol`, nicht null per
   Dekret.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..pivots.zigzag import Pivot
from . import geometry as g


class PatternType(str, Enum):
    IMPULSE = "impulse"
    LEADING_DIAGONAL = "leading_diagonal"
    ENDING_DIAGONAL = "ending_diagonal"
    ZIGZAG = "zigzag"
    FLAT = "flat"
    TRIANGLE = "triangle"


# Anzahl Wellen je Muster (Pivots = Wellen + 1).
WAVE_COUNT = {
    PatternType.IMPULSE: 5,
    PatternType.LEADING_DIAGONAL: 5,
    PatternType.ENDING_DIAGONAL: 5,
    PatternType.ZIGZAG: 3,
    PatternType.FLAT: 3,
    PatternType.TRIANGLE: 5,
}

# Erwartete Unterteilung jeder Welle. 5 = motiv, 3 = korrektiv.
# Grundlage der Eltern-Kind-Konsistenzpruefung ueber Lattice-Ebenen.
SUBDIVISION = {
    PatternType.IMPULSE: (5, 3, 5, 3, 5),
    PatternType.LEADING_DIAGONAL: (5, 3, 5, 3, 5),
    PatternType.ENDING_DIAGONAL: (3, 3, 3, 3, 3),
    PatternType.ZIGZAG: (5, 3, 5),
    PatternType.FLAT: (3, 3, 5),
    PatternType.TRIANGLE: (3, 3, 3, 3, 3),
}


@dataclass(frozen=True)
class Config:
    """Toleranzen.

    Bewusst klein und benannt: jede Toleranz ist eine Stellschraube, die
    ueberangepasst werden kann, deshalb sollen es wenige und begruendete sein.
    """

    # Zulaessige Ueberlappung von Welle 4 in Welle 1, als Anteil der Laenge
    # von Welle 1. 0.0 entspricht dem Cash-Markt-Wortlaut des Buchs.
    overlap_tol: float = 0.0
    # Mindest-Retracement von B gegenueber A, ab dem eine Korrektur als Flat
    # statt als Zigzag gilt.
    flat_min_b_retrace: float = 0.90
    # Ab hier gilt ein Flat als "expanded" statt "regular".
    flat_expanded_b: float = 1.05
    # Relative Toleranz bei Preisvergleichen, faengt Rundung ab.
    eps: float = 1e-9

    @staticmethod
    def leveraged() -> "Config":
        """Voreinstellung fuer Futures/Perpetuals.

        Das Buch nimmt gehebelte Maerkte von der strikten Nicht-Ueberlappung
        aus, weil dort kurzfristige Preisausreisser vorkommen, die im
        Cash-Markt nicht entstehen wuerden.
        """
        return Config(overlap_tol=0.05)


@dataclass
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


@dataclass
class Check:
    pattern: PatternType
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


# --------------------------------------------------------------------------
# Strukturelle Vorbedingungen
# --------------------------------------------------------------------------

def _structural(pivots: list[Pivot], pattern: PatternType) -> list[Violation]:
    v: list[Violation] = []
    need = WAVE_COUNT[pattern] + 1
    if len(pivots) != need:
        v.append(Violation("STRUKTUR", f"{len(pivots)} Pivots, erwartet {need}"))
        return v
    if not g.alternates(pivots):
        v.append(Violation("STRUKTUR", "Pivots wechseln nicht zwischen Hoch und Tief"))
    if not g.monotonic_time(pivots):
        v.append(Violation("STRUKTUR", "Pivots nicht zeitlich geordnet"))
    return v


# --------------------------------------------------------------------------
# Motive Wellen: gemeinsame Regeln von Impuls und Diagonale
# --------------------------------------------------------------------------

def _motive_rules(pivots: list[Pivot], cfg: Config) -> list[Violation]:
    """Die vier Regeln, die fuer jede motive Welle gelten (Lesson 4)."""
    v: list[Violation] = []
    d = g.direction(pivots)
    p0, p1, p2, p3, p4, p5 = pivots
    L = g.log_lengths(pivots)  # prozentual, wie im Buch formuliert

    # R1: Welle 2 retraciert Welle 1 nie zu mehr als 100 %.
    if not g.beyond(p2.price, p0.price, d):
        v.append(Violation(
            "W2_RETRACE", f"Welle 2 endet bei {p2.price:.6g} jenseits des Starts {p0.price:.6g}"
        ))

    # R2: Welle 3 laeuft immer ueber das Ende von Welle 1 hinaus.
    if not g.beyond(p3.price, p1.price, d):
        v.append(Violation(
            "W3_BEYOND_W1", f"Welle 3 endet bei {p3.price:.6g}, Welle 1 bei {p1.price:.6g}"
        ))

    # R3: Welle 3 ist nie die kuerzeste der Aktionswellen 1, 3, 5.
    if L[2] < L[0] and L[2] < L[4]:
        v.append(Violation(
            "W3_SHORTEST",
            f"Welle 3 ist die kuerzeste (log-Laengen 1/3/5: "
            f"{L[0]:.4f}/{L[2]:.4f}/{L[4]:.4f})",
        ))

    # R4: Welle 4 retraciert Welle 3 nie zu mehr als 100 %.
    if not g.beyond(p4.price, p2.price, d):
        v.append(Violation(
            "W4_RETRACE", f"Welle 4 endet bei {p4.price:.6g} jenseits des Starts {p2.price:.6g}"
        ))

    return v


def _overlap_amount(pivots: list[Pivot]) -> float:
    """Wie weit dringt Welle 4 in das Gebiet von Welle 1 ein?

    Positiv = Ueberlappung, als Anteil der Laenge von Welle 1.
    """
    d = g.direction(pivots)
    p1, p4 = pivots[1], pivots[4]
    w1 = abs(pivots[1].price - pivots[0].price)
    if w1 <= 0:
        return np.inf
    depth = (p1.price - p4.price) if d > 0 else (p4.price - p1.price)
    return depth / w1


# --------------------------------------------------------------------------
# Muster
# --------------------------------------------------------------------------

def check_impulse(pivots: list[Pivot], cfg: Config = Config()) -> Check:
    """Impuls (Lesson 4): 5 Wellen, Welle 4 ueberlappt Welle 1 nicht."""
    v = _structural(pivots, PatternType.IMPULSE)
    if v:
        return Check(PatternType.IMPULSE, False, v)

    v = _motive_rules(pivots, cfg)
    notes: list[str] = []

    ov = _overlap_amount(pivots)
    if ov > cfg.overlap_tol + cfg.eps:
        v.append(Violation(
            "W4_OVERLAP",
            f"Welle 4 dringt {ov:.1%} in Welle 1 ein (erlaubt {cfg.overlap_tol:.1%}) "
            f"- deutet auf eine Diagonale hin",
        ))

    # Truncation ist erlaubt, aber vermerkenswert: sie signalisiert
    # Erschoepfung und veraendert die Erwartung an die Folgebewegung.
    d = g.direction(pivots)
    if not g.beyond(pivots[5].price, pivots[3].price, d):
        notes.append("truncated_fifth")

    L = g.log_lengths(pivots)
    ext = int(np.argmax([L[0], L[2], L[4]]))
    notes.append(f"extension_w{[1, 3, 5][ext]}")

    return Check(PatternType.IMPULSE, not v, v, notes)


def _lines_converge(pivots: list[Pivot]) -> tuple[bool, float]:
    """Konvergieren die Begrenzungslinien der Diagonale/des Dreiecks?

    Das Buch definiert die Begrenzung ueber die Verbindung der Endpunkte von
    Welle 1 und 3 sowie von Welle 2 und 4 (bei Dreiecken a/c und b/d).
    Gemessen wird der vertikale Abstand beider Linien am Anfang und am Ende.
    """
    p1, p2, p3, p4 = pivots[1], pivots[2], pivots[3], pivots[4]

    def at(xa, ya, xb, yb, x):
        if xb == xa:
            return ya
        return ya + (yb - ya) * (x - xa) / (xb - xa)

    x_start, x_end = float(p1.idx), float(p4.idx)
    gap_start = abs(
        at(p1.idx, p1.price, p3.idx, p3.price, x_start)
        - at(p2.idx, p2.price, p4.idx, p4.price, x_start)
    )
    gap_end = abs(
        at(p1.idx, p1.price, p3.idx, p3.price, x_end)
        - at(p2.idx, p2.price, p4.idx, p4.price, x_end)
    )
    ratio = gap_end / gap_start if gap_start > 0 else np.inf
    return ratio < 1.0, ratio


def check_diagonal(
    pivots: list[Pivot], cfg: Config = Config(), *, ending: bool = True
) -> Check:
    """Diagonale (Lesson 5).

    Motive Struktur, aber das einzige Fuenfwellen-Muster in Trendrichtung,
    bei dem Welle 4 in das Gebiet von Welle 1 eintritt. Der ausgeweitete
    Keil wird vom Buch ausdruecklich nicht als gueltige Variante gefuehrt.
    """
    ptype = PatternType.ENDING_DIAGONAL if ending else PatternType.LEADING_DIAGONAL
    v = _structural(pivots, ptype)
    if v:
        return Check(ptype, False, v)

    v = _motive_rules(pivots, cfg)
    notes: list[str] = []

    ov = _overlap_amount(pivots)
    if ov <= 0:
        v.append(Violation(
            "NO_OVERLAP",
            f"Welle 4 ueberlappt Welle 1 nicht ({ov:.1%}) - das waere ein Impuls",
        ))

    converging, ratio = _lines_converge(pivots)
    if not converging:
        v.append(Violation(
            "NOT_CONTRACTING",
            f"Begrenzungslinien konvergieren nicht (Verhaeltnis {ratio:.2f}); "
            f"der ausgeweitete Keil gilt nicht als gueltige Variante",
        ))

    d = g.direction(pivots)
    if not g.beyond(pivots[5].price, pivots[3].price, d):
        notes.append("truncated_fifth")

    return Check(ptype, not v, v, notes)


def check_zigzag(pivots: list[Pivot], cfg: Config = Config()) -> Check:
    """Zigzag (Lesson 6), Unterteilung 5-3-5.

    Scharfe Korrektur: B retraciert A nicht vollstaendig, C laeuft ueber das
    Ende von A hinaus.
    """
    v = _structural(pivots, PatternType.ZIGZAG)
    if v:
        return Check(PatternType.ZIGZAG, False, v)

    p0, p1, p2, p3 = pivots
    d = g.direction(pivots)  # Richtung von Welle A
    notes: list[str] = []

    # B darf den Startpunkt von A nicht ueberschreiten. B laeuft entgegen A,
    # der Vergleich erfolgt deshalb in Gegenrichtung (-d).
    if g.beyond(p2.price, p0.price, -d):
        v.append(Violation(
            "B_EXCEEDS_A_START",
            f"Welle B endet bei {p2.price:.6g} jenseits des A-Starts {p0.price:.6g}",
        ))

    b_retrace = g.retracement(pivots, 1)
    if b_retrace >= cfg.flat_min_b_retrace:
        v.append(Violation(
            "B_TOO_DEEP",
            f"B retraciert {b_retrace:.0%} von A - ab "
            f"{cfg.flat_min_b_retrace:.0%} ist es ein Flat",
        ))

    # C laeuft ueber das Ende von A hinaus; andernfalls ist es kein Zigzag.
    if not g.beyond(p3.price, p1.price, d):
        v.append(Violation(
            "C_SHORT_OF_A",
            f"Welle C endet bei {p3.price:.6g}, erreicht das A-Ende "
            f"{p1.price:.6g} nicht",
        ))

    return Check(PatternType.ZIGZAG, not v, v, notes)


def check_flat(pivots: list[Pivot], cfg: Config = Config()) -> Check:
    """Flat (Lesson 7), Unterteilung 3-3-5.

    B endet nahe dem Start von A. Die drei Spielarten regular / expanded /
    running unterscheiden sich darin, wie weit B ueber den A-Start und C
    ueber das A-Ende hinauslaeuft; sie werden als Notiz vermerkt, nicht als
    Regel erzwungen.
    """
    v = _structural(pivots, PatternType.FLAT)
    if v:
        return Check(PatternType.FLAT, False, v)

    p0, p1, p2, p3 = pivots
    d = g.direction(pivots)
    notes: list[str] = []

    b_retrace = g.retracement(pivots, 1)
    if b_retrace < cfg.flat_min_b_retrace:
        v.append(Violation(
            "B_TOO_SHALLOW",
            f"B retraciert nur {b_retrace:.0%} von A, ein Flat verlangt "
            f"mindestens {cfg.flat_min_b_retrace:.0%}",
        ))

    c_beyond_a = g.beyond(p3.price, p1.price, d)
    if b_retrace > cfg.flat_expanded_b:
        notes.append("expanded" if c_beyond_a else "running")
    else:
        notes.append("regular")
        if not c_beyond_a:
            notes.append("c_short")

    return Check(PatternType.FLAT, not v, v, notes)


def check_triangle(pivots: list[Pivot], cfg: Config = Config()) -> Check:
    """Dreieck (Lesson 8), Unterteilung 3-3-3-3-3.

    Fuenf ueberlappende Wellen a-b-c-d-e. Kontrahierend oder expandierend;
    laeuft b ueber den Start von a hinaus, spricht das Buch von einem
    "running triangle" - zulaessig, deshalb nur eine Notiz.
    """
    v = _structural(pivots, PatternType.TRIANGLE)
    if v:
        return Check(PatternType.TRIANGLE, False, v)

    notes: list[str] = []
    L = g.lengths(pivots)
    d = g.direction(pivots)

    converging, ratio = _lines_converge(pivots)
    notes.append("contracting" if converging else "expanding")

    # Wesensmerkmal des Dreiecks: fuenf einander ueberlappende Wellen. Beim
    # kontrahierenden Dreieck bleibt jedes Extrem innerhalb des uebernaechsten
    # davor (P3 innerhalb P1, P4 innerhalb P2, P5 innerhalb P3), beim
    # expandierenden gilt durchgehend das Gegenteil. Ohne diese Bedingung
    # wuerde nahezu jede Seitwaertsbewegung als Dreieck durchgehen.
    inside = []
    for k in (3, 4, 5):
        step_dir = d if (k % 2 == 1) else -d
        inside.append(not g.beyond(pivots[k].price, pivots[k - 2].price, step_dir))

    if converging and not all(inside):
        v.append(Violation(
            "NOT_OVERLAPPING",
            f"Kontrahierendes Dreieck verlangt, dass jedes Extrem innerhalb "
            f"des uebernaechsten bleibt (erfuellt: {inside})",
        ))
    if not converging and any(inside):
        v.append(Violation(
            "NOT_EXPANDING",
            f"Expandierendes Dreieck verlangt durchgehend wachsende Extreme "
            f"(erfuellt: {[not i for i in inside]})",
        ))

    # Monotonie der Wellenlaengen als zusaetzliche Konsistenzpruefung.
    if converging and not (L[1] > L[3] and L[2] > L[4]):
        v.append(Violation(
            "NOT_MONOTONE_CONTRACTING",
            f"Linien konvergieren, aber die Wellenlaengen schrumpfen nicht "
            f"monoton ({[round(x, 4) for x in L]})",
        ))

    # Running Triangle: b laeuft ueber den Start von a hinaus.
    if g.beyond(pivots[2].price, pivots[0].price, -d):
        notes.append("running")

    return Check(PatternType.TRIANGLE, not v, v, notes)


CHECKERS = {
    PatternType.IMPULSE: check_impulse,
    PatternType.ZIGZAG: check_zigzag,
    PatternType.FLAT: check_flat,
    PatternType.TRIANGLE: check_triangle,
    PatternType.ENDING_DIAGONAL: lambda p, c=Config(): check_diagonal(p, c, ending=True),
    PatternType.LEADING_DIAGONAL: lambda p, c=Config(): check_diagonal(p, c, ending=False),
}


def check(pattern: PatternType, pivots: list[Pivot], cfg: Config = Config()) -> Check:
    return CHECKERS[pattern](pivots, cfg)


def all_matching(pivots: list[Pivot], cfg: Config = Config()) -> list[Check]:
    """Alle Muster, die zu dieser Pivot-Folge regelkonform passen.

    Mehrdeutigkeit ist der Normalfall, nicht die Ausnahme. Genau deshalb ist
    das Ergebnis eine Liste und die Auswahl Sache des Scorings.
    """
    n = len(pivots) - 1
    out: list[Check] = []
    for ptype, need in WAVE_COUNT.items():
        if need != n:
            continue
        res = check(ptype, pivots, cfg)
        if res.ok:
            out.append(res)
    return out
