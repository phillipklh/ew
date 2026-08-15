"""Antizipative Setups: Limit-Order in eine projizierte Zone.

Ablauf, wie ihn ein Analyst beschreibt:

  1. Welle 1 auf dem Kontextgrad identifizieren.
  2. Zielzone der Korrektur projizieren (0.382-0.618 der Welle 1).
  3. Zone gegen Projektionen anderer Grade abgleichen - Konfluenz.
  4. Feinere Struktur pruefen: haelt das enge Band, oder muss auf
     0.618-1.0 ausgeweitet werden?
  5. Limit-Einstieg an der flacheren Kante der Zone.
  6. Stop knapp unter der Gegenkante.
  7. Ziel an der Extension der uebergeordneten Struktur.

Der Unterschied zum Bestaetigungssystem ist wirtschaftlich entscheidend:
das Risiko ist die Zonenbreite statt der Laenge von Welle 1, waehrend das
Ziel unveraendert an der uebergeordneten Extension haengt. Damit steigt das
Chance-Risiko-Verhaeltnis um ein Vielfaches - und die Bestaetigungs-
verzoegerung aus Befund F1 entfaellt, weil auf nichts gewartet wird.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..pivots.lattice import Lattice
from ..pivots.zigzag import Pivot
from .zones import Confluence, Zone, build_confluence, extension_target


@dataclass
class ZoneSignal:
    """Eine Limit-Order in eine projizierte Zone."""

    bar: int              # Bar, an dem die Order gestellt wird
    direction: int
    limit: float          # Einstiegskurs (flachere Zonenkante)
    stop: float
    target: float
    zone: Zone
    conf: Confluence
    context_scale: int
    wave1_start: Pivot
    wave1_end: Pivot
    extended: bool        # wurde auf 0.618-1.0 ausgeweitet
    expiry_bar: int
    rsi: float = np.nan
    macd_hist: float = np.nan
    squeeze_on: bool = False

    @property
    def rr(self) -> float:
        risk = abs(self.limit - self.stop)
        return abs(self.target - self.limit) / risk if risk > 0 else np.nan

    @property
    def confluence(self) -> int:
        return self.conf.n_supporting


def _should_extend(
    lat: Lattice, p1: Pivot, bar: int, direction: int, zone: Zone
) -> bool:
    """Legt die feinere Struktur nahe, dass das enge Band nicht haelt?

    Kriterium: die Korrektur ist bereits durch die flachere Kante gelaufen
    und hat dabei auf einer feineren Ebene keinen Wendepunkt gebildet - die
    Bewegung ist also noch im Gange statt zu drehen.
    """
    for s in range(zone.scale - 1, max(zone.scale - 3, -1), -1):
        sub = [p for p in lat.visible_at(s, bar)
               if p.idx > p1.idx and not p.is_anchor]
        if len(sub) >= 3:
            return False
    return True


def generate(
    lat: Lattice,
    df: pd.DataFrame,
    bar: int,
    *,
    context_scale: int,
    min_rr: float = 2.0,
    max_wait_bars: int = 60,
    stop_pct: float = 0.01,
    stop_from: str = "operative",
    target_ratio: float = 1.618,
    ind: dict | None = None,
) -> list[ZoneSignal]:
    """Erzeugt Limit-Setups an Bar `bar`. Streng kausal.

    `stop_from` waehlt die Kante, unter der der Stop liegt:
      "operative" - Gegenkante der operativen Zone (enger, hoeheres RR)
      "extended"  - Gegenkante des ausgeweiteten Bandes 0.618-1.0
                    (weiter, uebersteht das tiefere Szenario)
    """
    piv = [p for p in lat.visible_at(context_scale, bar) if not p.is_anchor]
    if len(piv) < 2:
        return []
    p0, p1 = piv[-2], piv[-1]

    d = 1 if p1.price > p0.price else -1
    w1 = abs(p1.price - p0.price)
    if w1 <= 0:
        return []

    # Die Order wird gestellt, sobald Welle 1 bestaetigt ist - nicht spaeter.
    if p1.confirmed_idx != bar:
        return []

    px = float(df["close"].iloc[bar])
    # Der Kurs darf die Zone noch nicht durchlaufen haben, sonst ist das
    # Setup bereits vorbei.
    if (d > 0 and px < p1.price - 0.382 * w1) or (d < 0 and px > p1.price + 0.382 * w1):
        return []

    conf = build_confluence(lat, p0, p1, context_scale, bar, d, extend=False)
    zone = conf.primary
    extended = _should_extend(lat, p1, bar, d, zone)
    if extended:
        conf = build_confluence(lat, p0, p1, context_scale, bar, d, extend=True)
        zone = conf.primary

    # Flachere Kante = Einstieg, Gegenkante = Bezug fuer den Stop.
    limit = zone.hi if d > 0 else zone.lo
    stop_edge = (conf.extended.lo if stop_from == "extended" else zone.lo) if d > 0 \
        else (conf.extended.hi if stop_from == "extended" else zone.hi)
    stop = stop_edge * (1 - stop_pct * d)

    # Ziel an der Extension, gemessen ab der Gegenkante der Zone - also dem
    # ungünstigsten plausiblen Ende der Korrektur.
    origin = zone.lo if d > 0 else zone.hi
    target = extension_target(p0, p1, origin, target_ratio)

    risk = abs(limit - stop)
    if risk <= 0 or not np.isfinite(risk):
        return []
    rr = abs(target - limit) / risk
    if rr < min_rr:
        return []

    sig = ZoneSignal(
        bar=bar, direction=d, limit=float(limit), stop=float(stop),
        target=float(target), zone=zone, conf=conf,
        context_scale=context_scale, wave1_start=p0, wave1_end=p1,
        extended=extended, expiry_bar=bar + max_wait_bars,
    )
    if ind is not None:
        sig.rsi = float(ind["rsi"].iloc[bar])
        sig.macd_hist = float(ind["macd_hist"].iloc[bar])
        sig.squeeze_on = bool(ind["squeeze_on"].iloc[bar])
    return [sig]


def scan(
    lat: Lattice,
    df: pd.DataFrame,
    *,
    context_scales: tuple[int, ...] = (4, 5, 6),
    with_indicators: bool = True,
    **kw,
) -> list[ZoneSignal]:
    ind = None
    if with_indicators:
        from ..pivots.indicators import macd, rsi, squeeze

        sq = squeeze(df)
        ind = {
            "rsi": rsi(df, 14),
            "macd_hist": macd(df)["hist"],
            "squeeze_on": sq["on"],
        }

    out: list[ZoneSignal] = []
    for bar in range(len(df)):
        for cs in context_scales:
            out.extend(generate(lat, df, bar, context_scale=cs, ind=ind, **kw))
    return out
