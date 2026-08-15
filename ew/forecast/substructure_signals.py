"""Setups aus der Substruktur der laufenden Korrektur.

Unterschied zum einfachen Zonen-System: dort wurde die Zielzone aus einem
Standardband der uebergeordneten Welle abgeleitet (0.382-0.618 von Welle 1).
Hier entsteht sie aus der Korrektur selbst - aus der Projektion ihrer
laufenden Teilwelle, gegebenenfalls der abschliessenden c-Welle eines
W-X-Y - und wird mit den Projektionen anderer Grade zur Deckung gebracht.

Der Ablauf entspricht der beschriebenen Praxis:

  1. Welle 1 auf dem Kontextgrad steht.
  2. Die Korrektur laeuft; ihre Teilwellen werden auf der feinsten
     brauchbaren Ebene gezaehlt - 3 Wellen einfach, 7 ein W-X-Y, 11 ein
     dreifaches.
  3. Die laufende Schlusswelle wird projiziert (c = a bzw. 1.618 a).
  4. Ist die c bereits angelaufen, wird ihre fuenfte Teilwelle zusaetzlich
     projiziert - der Blick in den naechstkleineren Zyklus.
  5. Diese Projektionen werden mit dem Retracement-Band der uebergeordneten
     Welle geschnitten. Der **Schnitt** ist die Zielzone, nicht das Band.
  6. Einstieg an der zuerst erreichten Kante des Schnitts, Stop knapp
     jenseits der Gegenkante, Ziel an der Extension der uebergeordneten
     Struktur.

Der entscheidende Punkt ist Schritt 5: eine Zone aus mehreren unabhaengigen
Projektionen ist erheblich enger als ein Standardband - und ein engerer
Stop bei gleichem Ziel ist genau das, was das Chance-Risiko-Verhaeltnis
traegt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..pivots.lattice import Lattice
from ..pivots.zigzag import Pivot
from .zones import (
    ZONE_EXTENDED,
    ZONE_NORMAL,
    Decomposition,
    Zone,
    decompose_correction,
    extension_target,
    project_fifth_of_c,
    project_pending_leg,
    retracement_zone,
)


@dataclass
class SubSignal:
    """Limit-Setup, dessen Zone aus der Substruktur projiziert wurde."""

    bar: int
    direction: int
    limit: float
    stop: float
    target: float
    zone: Zone
    context_scale: int
    wave1_start: Pivot
    wave1_end: Pivot
    decomposition: str          # "einfach", "double_three", ...
    legs: int
    n_projections: int          # wie viele Projektionen die Zone stuetzen
    sources: list[str] = field(default_factory=list)
    expiry_bar: int = 0
    extended: bool = False
    squeeze_on: bool = False
    rsi: float = np.nan

    @property
    def rr(self) -> float:
        risk = abs(self.limit - self.stop)
        return abs(self.target - self.limit) / risk if risk > 0 else np.nan

    @property
    def confluence(self) -> int:
        return self.n_projections


def _intersect(zones: list[Zone]) -> Zone | None:
    """Schnittmenge mehrerer Zonen.

    Ohne gemeinsamen Bereich gibt es kein Setup - die Projektionen
    widersprechen sich dann, und genau das ist die Information.
    """
    if not zones:
        return None
    lo = max(z.lo for z in zones)
    hi = min(z.hi for z in zones)
    if hi <= lo:
        return None
    return Zone(lo=lo, hi=hi, scale=zones[0].scale,
                source="+".join(z.source for z in zones))


def generate(
    lat: Lattice,
    df: pd.DataFrame,
    bar: int,
    *,
    context_scale: int,
    min_rr: float = 2.0,
    min_projections: int = 2,
    stop_pct: float = 0.01,
    max_wait_bars: int = 40,
    target_ratio: float = 1.618,
    ind: dict | None = None,
) -> list[SubSignal]:
    """Erzeugt ein Setup, sobald die Substruktur eine Zone hergibt."""
    piv = [p for p in lat.visible_at(context_scale, bar) if not p.is_anchor]
    if len(piv) < 2:
        return []
    p0, p1 = piv[-2], piv[-1]
    d = 1 if p1.price > p0.price else -1
    w1 = abs(p1.price - p0.price)
    if w1 <= 0:
        return []

    px = float(df["close"].iloc[bar])
    lo_since = float(df["low"].iloc[p1.idx: bar + 1].min())
    hi_since = float(df["high"].iloc[p1.idx: bar + 1].max())
    # Regel-Invalidierung bereits verletzt: die Zaehlung ist tot.
    if (d > 0 and lo_since <= p0.price) or (d < 0 and hi_since >= p0.price):
        return []

    dec = decompose_correction(lat, context_scale, p1, bar)
    if dec is None or dec.pending == "offen":
        return []

    zones: list[Zone] = []
    pending = project_pending_leg(dec)
    if pending is not None:
        zones.append(pending)
    fifth = project_fifth_of_c(lat, dec, bar)
    if fifth is not None:
        zones.append(fifth)

    # Retracement-Band der uebergeordneten Welle als dritte Projektion.
    # Ist die Korrektur schon tief, wird das erweiterte Band verwendet.
    depth = abs((lo_since if d > 0 else hi_since) - p1.price) / w1
    extended = depth > ZONE_NORMAL[1]
    band = ZONE_EXTENDED if extended else ZONE_NORMAL
    zones.append(retracement_zone(p0, p1, band, context_scale, "welle1_band"))

    if len(zones) < min_projections:
        return []
    zone = _intersect(zones)
    if zone is None:
        return []

    # Einstieg an der Kante der Schnittzone, die der Kurs zuerst erreicht -
    # hier zahlt sich die Praezision der Substruktur aus.
    limit = zone.hi if d > 0 else zone.lo

    # Der Stop gehoert dagegen unter das **weite** Band, nicht unter die
    # Schnittzone. Die Substruktur-Analyse entscheidet, ob das Setup genommen
    # wird und ob auszuweiten ist - sie verengt nicht die Verlustbegrenzung.
    # Ein Stop an der Schnittzone waere so eng, dass ihn normales Rauschen
    # reisst: in einer ersten Fassung fiel die Trefferquote dadurch auf 16,6 %
    # und die Kosten machten aus jedem Verlust 1,1 bis 1,3 R.
    wide = retracement_zone(p0, p1, ZONE_EXTENDED, context_scale, "stopband")
    far = wide.lo if d > 0 else wide.hi
    stop = far * (1 - stop_pct * d)

    # Der Einstieg muss noch vor dem Kurs liegen, sonst ist er ueberholt.
    if (d > 0 and px <= limit) or (d < 0 and px >= limit):
        return []

    risk = abs(limit - stop)
    if risk <= 0 or not np.isfinite(risk):
        return []
    target = extension_target(p0, p1, far, target_ratio)
    rr = abs(target - limit) / risk
    if rr < min_rr or not np.isfinite(rr):
        return []

    sig = SubSignal(
        bar=bar, direction=d, limit=float(limit), stop=float(stop),
        target=float(target), zone=zone, context_scale=context_scale,
        wave1_start=p0, wave1_end=p1, decomposition=dec.label, legs=dec.legs,
        n_projections=len(zones), sources=[z.source for z in zones],
        expiry_bar=bar + max_wait_bars, extended=extended,
    )
    if ind is not None:
        sig.squeeze_on = bool(ind["squeeze_on"].iloc[bar])
        sig.rsi = float(ind["rsi"].iloc[bar])
    return [sig]


def scan(
    lat: Lattice,
    df: pd.DataFrame,
    *,
    context_scales: tuple[int, ...] = (4, 5, 6),
    with_indicators: bool = True,
    **kw,
) -> list[SubSignal]:
    ind = None
    if with_indicators:
        from ..pivots.indicators import rsi, squeeze

        ind = {"rsi": rsi(df, 14), "squeeze_on": squeeze(df)["on"]}

    # Pro Korrektur wird nur ein Setup gestellt. Ohne diese Entdopplung
    # entstuende auf jeder Bar ein neues, leicht verschobenes Setup zur
    # selben Struktur - im Backtest waere das eine kuenstliche Vervielfachung
    # derselben Entscheidung.
    seen: set[tuple[int, int]] = set()
    out: list[SubSignal] = []
    for bar in range(len(df)):
        for cs in context_scales:
            for sig in generate(lat, df, bar, context_scale=cs, ind=ind, **kw):
                key = (cs, sig.wave1_end.idx)
                if key in seen:
                    continue
                seen.add(key)
                out.append(sig)
    return out
