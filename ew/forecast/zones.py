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
