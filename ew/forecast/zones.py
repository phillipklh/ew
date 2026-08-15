"""Projizierte Zielzonen und ihre Konfluenz ueber mehrere Zyklusgrade.

Dies ist der Kern des antizipativen Ansatzes und unterscheidet sich
grundlegend von einem Bestaetigungssystem:

  Bestaetigungssystem  wartet, bis der Wendepunkt belegt ist, und steigt
                       danach ein. Befund F1 zeigt, dass dieser Beleg auf
                       jeder Skala rund 1,5-mal so spaet eintrifft wie die
                       Welle dauert - der Einstieg kommt also strukturell
                       zu spaet.

  Zonensystem          berechnet vorab, wo die Korrektur enden *sollte*, und
                       legt eine Limit-Order hinein. Die Verzoegerung aus F1
                       spielt keine Rolle mehr, weil auf nichts gewartet wird.
                       Das Risiko ist die Zonenbreite, nicht die Laenge von
                       Welle 1 - daher die deutlich groesseren R-Vielfachen.

Die Genauigkeit entsteht durch **Konfluenz**: dieselbe Zone wird aus mehreren
Zyklusgraden heraus projiziert. Wo sich diese Projektionen ueberlappen, ist
die Erwartung am besten belegt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..pivots.lattice import Lattice
from ..pivots.zigzag import Pivot

# Das uebliche Retracement-Band einer Welle 2 und die Ausweitung, falls die
# feinere Struktur nahelegt, dass das engere Band nicht haelt.
ZONE_NORMAL = (0.382, 0.618)
ZONE_EXTENDED = (0.618, 1.000)


@dataclass
class Zone:
    """Ein projizierter Preisbereich, in dem eine Welle enden sollte."""

    lo: float
    hi: float
    source: str          # woraus projiziert
    scale: int
    weight: float = 1.0

    @property
    def mid(self) -> float:
        return 0.5 * (self.lo + self.hi)

    @property
    def width(self) -> float:
        return self.hi - self.lo

    def overlaps(self, other: "Zone") -> float:
        """Ueberlappung mit einer anderen Zone, relativ zur eigenen Breite."""
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        if hi <= lo or self.width <= 0:
            return 0.0
        return (hi - lo) / self.width

    def contains(self, price: float) -> bool:
        return self.lo <= price <= self.hi


@dataclass
class Confluence:
    """Operative Zone plus die Projektionen, die sie stuetzen."""

    primary: Zone
    supporting: list[Zone] = field(default_factory=list)
    extended: Zone | None = None

    @property
    def score(self) -> float:
        """Summe der Ueberlappungsanteile aller stuetzenden Projektionen."""
        return float(sum(self.primary.overlaps(z) for z in self.supporting))

    @property
    def n_supporting(self) -> int:
        return sum(1 for z in self.supporting if self.primary.overlaps(z) > 0.1)


def retracement_zone(
    p0: Pivot, p1: Pivot, band: tuple[float, float], scale: int, source: str
) -> Zone:
    """Retracement-Zone einer Welle, gemessen vom Ende zurueck.

    Fuer eine Aufwaertswelle liegt die Zone unterhalb des Hochs; `hi` ist
    dabei immer der flachere (fuer einen Long teurere) Rand.
    """
    w = p1.price - p0.price
    a = p1.price - band[0] * w
    b = p1.price - band[1] * w
    return Zone(lo=min(a, b), hi=max(a, b), source=source, scale=scale)


def extension_target(
    p0: Pivot, p1: Pivot, origin: float, ratio: float = 1.618
) -> float:
    """Projiziertes Ziel als Extension der Ausgangswelle ab `origin`."""
    w = p1.price - p0.price
    return origin + ratio * w


def _subwave_projection(
    lat: Lattice, scale: int, p1: Pivot, bar: int, direction: int
) -> Zone | None:
    """Projiziert das Ende der laufenden Korrektur aus ihrer Substruktur.

    Sind auf einer feineren Ebene bereits Teilwellen der Korrektur sichtbar,
    laesst sich das Ende ueber die Gleichheitsbeziehung schaetzen: die
    letzte Teilwelle erreicht typischerweise etwa die Laenge der ersten.
    Genau dieser Schritt entspricht dem Blick in den kleineren Zyklus, um
    die 5-Teilung der c-Welle abzuschaetzen.
    """
    for s in range(scale - 1, max(scale - 4, -1), -1):
        sub = [p for p in lat.visible_at(s, bar)
               if p.idx >= p1.idx and not p.is_anchor]
        if len(sub) < 3:
            continue
        # a = erste Teilwelle der Korrektur, ab b wird c projiziert.
        a_len = abs(sub[1].price - sub[0].price)
        b_end = sub[-1].price
        if a_len <= 0:
            continue
        c_equal = b_end - direction * a_len
        c_1618 = b_end - direction * 1.618 * a_len
        return Zone(lo=min(c_equal, c_1618), hi=max(c_equal, c_1618),
                    source=f"substruktur_s{s}", scale=s)
    return None


#: Uebliche Verhaeltnisse der Schlusswelle einer Korrektur zur ersten
#: Teilwelle derselben Komponente. Die Gleichheit ist der haeufigste Fall.
C_RATIOS = (1.000, 1.618)
#: Verhaeltnisse der fuenften Teilwelle eines Impulses zur ersten.
W5_RATIOS = (0.618, 1.000)


@dataclass
class Decomposition:
    """Zerlegung der laufenden Korrektur in ihre Teilwellen."""

    scale: int
    legs: int                 # abgeschlossene Teilwellen seit dem Wellenende
    pivots: list[Pivot]       # beginnend mit dem Ausgangspivot
    label: str                # "einfach", "double_three", "triple_three", ...
    pending: str              # welche Teilwelle gerade laeuft

    @property
    def is_combination(self) -> bool:
        return self.legs >= 6


def decompose_correction(
    lat: Lattice, scale: int, p1: Pivot, bar: int, min_legs: int = 2
) -> Decomposition | None:
    """Zerlegt die laufende Korrektur auf der feinsten brauchbaren Ebene.

    Die Wellenzahl ordnet die Struktur ein (Lesson 9): 3 Wellen sind eine
    einfache Korrektur, 7 eine Kombination aus zwei einfachen Korrekturen
    (W-X-Y), 11 eine dreifache. Da die Korrektur noch laeuft, ist die letzte
    Teilwelle unvollstaendig - genau sie soll projiziert werden.

    Gesucht wird die feinste Ebene, die genug Teilwellen zeigt, ohne im
    Rauschen zu verschwinden. Das entspricht dem Grundsatz, nicht beliebig
    tief abzusteigen: sobald die Struktur klar ist, reicht sie.
    """
    # Wichtig: nicht die erstbeste Ebene nehmen. Die groebste Ebene zeigt fast
    # immer nur zwei bis drei Teilwellen und laesst damit jede Kombination wie
    # eine einfache Korrektur aussehen - eine erste Fassung erkannte so nur 30
    # von 318 Strukturen als W-X-Y. Gesucht wird stattdessen die Ebene, deren
    # Wellenzahl einer kanonischen korrektiven Zahl entspricht (Lesson 9:
    # 3 einfach, 7 doppelt, 11 dreifach), und unter diesen die groebste -
    # also die klarste, ohne unnoetig tief abzusteigen.
    LABELS = {
        2: ("einfach", "c"), 3: ("einfach", "c"),
        6: ("double_three", "c_von_Y"), 7: ("double_three", "c_von_Y"),
        10: ("triple_three", "c_von_Z"), 11: ("triple_three", "c_von_Z"),
    }

    candidates: list[Decomposition] = []
    for s in range(scale - 1, max(scale - 5, -1), -1):
        sub = [p for p in lat.visible_at(s, bar)
               if p.idx >= p1.idx and not p.is_anchor]
        # Der Ausgangspivot selbst muss enthalten sein; wegen der
        # Verschachtelung existiert er auf jeder feineren Ebene.
        if not sub or sub[0].idx != p1.idx:
            sub = [p1] + [p for p in sub if p.idx > p1.idx]
        legs = len(sub) - 1
        if legs < min_legs:
            continue
        label, pending = LABELS.get(legs, (f"legs_{legs}", "offen"))
        candidates.append(Decomposition(scale=s, legs=legs, pivots=sub,
                                        label=label, pending=pending))

    if not candidates:
        return None
    canonical = [c for c in candidates if c.pending != "offen"]
    if canonical:
        # Groebste Ebene mit kanonischer Wellenzahl: die hoechste Skala,
        # also der erste Treffer in der absteigenden Reihenfolge.
        return canonical[0]
    return candidates[0]


def project_pending_leg(dec: Decomposition) -> Zone | None:
    """Projiziert das Ende der laufenden Teilwelle.

    Unabhaengig davon, ob eine einfache Korrektur oder eine Kombination
    vorliegt, sind die beiden zuletzt abgeschlossenen Teilwellen die
    Bezugsgroessen: die vorletzte entspricht dem `a`, die letzte dem `b`,
    und projiziert wird das `c` ab dem aktuellen Endpunkt. Bei einem
    W-X-Y trifft das automatisch die Teilwellen des abschliessenden Y,
    weil W und X davor liegen.
    """
    sub = dec.pivots
    if len(sub) < 3:
        return None
    a_start, a_end, b_end = sub[-3], sub[-2], sub[-1]
    a_len = abs(a_end.price - a_start.price)
    if a_len <= 0:
        return None
    d_a = 1 if a_end.price > a_start.price else -1

    targets = [b_end.price + d_a * r * a_len for r in C_RATIOS]
    return Zone(lo=min(targets), hi=max(targets),
                source=f"{dec.label}:{dec.pending}", scale=dec.scale)


def project_fifth_of_c(
    lat: Lattice, dec: Decomposition, bar: int
) -> Zone | None:
    """Projiziert die fuenfte Teilwelle der laufenden c-Welle.

    Ist die c-Welle bereits angelaufen und zeigt auf einer feineren Ebene
    ihre Wellen 1 bis 4, laesst sich ihr Ende ueber das Verhaeltnis der
    fuenften zur ersten Teilwelle schaetzen. Das ist der Blick in den
    naechstkleineren Zyklus, um die 5-Teilung der c zu ueberpruefen.
    """
    c_start = dec.pivots[-1]
    for s in range(dec.scale - 1, max(dec.scale - 3, -1), -1):
        inner = [p for p in lat.visible_at(s, bar)
                 if p.idx >= c_start.idx and not p.is_anchor]
        if not inner or inner[0].idx != c_start.idx:
            inner = [c_start] + [p for p in inner if p.idx > c_start.idx]
        # Vier abgeschlossene Teilwellen bedeuten: Welle 5 laeuft.
        if len(inner) - 1 < 4:
            continue
        w1 = abs(inner[1].price - inner[0].price)
        w4_end = inner[4]
        if w1 <= 0:
            continue
        d = 1 if inner[1].price > inner[0].price else -1
        targets = [w4_end.price + d * r * w1 for r in W5_RATIOS]
        return Zone(lo=min(targets), hi=max(targets),
                    source=f"fuenfte_von_c_s{s}", scale=s)
    return None


def build_confluence(
    lat: Lattice,
    p0: Pivot,
    p1: Pivot,
    context_scale: int,
    bar: int,
    direction: int,
    *,
    extend: bool = False,
) -> Confluence:
    """Baut die operative Zone und sammelt stuetzende Projektionen.

    `extend` schaltet vom Band 0.382-0.618 auf 0.618-1.0 um - fuer den Fall,
    dass die feinere Struktur ein Durchbrechen des engeren Bandes nahelegt.
    """
    band = ZONE_EXTENDED if extend else ZONE_NORMAL
    primary = retracement_zone(p0, p1, band, context_scale, "welle1_retrace")
    extended = retracement_zone(p0, p1, ZONE_EXTENDED, context_scale, "erweitert")

    supporting: list[Zone] = []

    # Projektion aus dem naechsthoeheren Grad: dessen letzte Welle liefert
    # ein eigenes Retracement-Band. Ueberlappen sich beide, ist die Zone von
    # zwei Graden gestuetzt.
    hp = [p for p in lat.visible_at(context_scale + 1, bar) if not p.is_anchor]
    if len(hp) >= 2:
        supporting.append(
            retracement_zone(hp[-2], hp[-1], ZONE_NORMAL, context_scale + 1,
                             "hoeherer_grad")
        )

    # Projektion aus der Substruktur der laufenden Korrektur.
    sub = _subwave_projection(lat, context_scale, p1, bar, direction)
    if sub is not None:
        supporting.append(sub)

    # Fruehere Wellen-4-Zone desselben Grades: eine Korrektur endet oft im
    # Bereich der vorangegangenen Welle 4 einer Ebene tiefer.
    prev = [p for p in lat.visible_at(context_scale - 1, bar)
            if p.idx < p1.idx and not p.is_anchor]
    if len(prev) >= 4:
        cand = prev[-4:]
        lo = min(x.price for x in cand)
        hi = max(x.price for x in cand)
        if lo < hi:
            supporting.append(
                Zone(lo=lo, hi=hi, source="frueheres_w4", scale=context_scale - 1,
                     weight=0.5)
            )

    return Confluence(primary=primary, supporting=supporting, extended=extended)
