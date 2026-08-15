"""Kausaler ATR-normierter ZigZag.

Zwei Eigenschaften, die dieses Modul von einem Lehrbuch-ZigZag unterscheiden
und ohne die eine EW-Automatisierung nicht funktioniert:

1. **Kein Repainting.** Jeder Pivot traegt zwei Zeitpunkte:
     `idx`           - die Bar des Extremwerts (nur rueckblickend bekannt)
     `confirmed_idx` - die Bar, an der die Gegenbewegung den Schwellwert riss
   Erst ab `confirmed_idx` existiert der Pivot fuer das System. Der uebliche
   Fehler ist, den Extrempunkt zu verwenden, sobald er im Chart sichtbar ist -
   damit sieht jeder Backtest hervorragend aus und jedes Live-System versagt.

2. **ATR-normierte Schwelle.** Ein Prozent-Threshold ist bei BTC 2017 etwas
   voellig anderes als bei Gold 2019. In ATR-Einheiten ist die Schwelle ueber
   Assets und Volatilitaetsregime hinweg vergleichbar, ohne Nachjustieren.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HIGH = 1
LOW = -1


@dataclass(frozen=True)
class Pivot:
    """Ein bestaetigter Wendepunkt."""

    idx: int            # Bar-Index des Extremwerts
    price: float
    kind: int           # HIGH (+1) oder LOW (-1)
    confirmed_idx: int  # Bar-Index, ab dem der Pivot bekannt ist
    scale: int = 0      # Ebene im Lattice
    is_anchor: bool = False  # aus der Bootstrap-Phase, kein echter Wendepunkt

    @property
    def lag(self) -> int:
        """Verzoegerung zwischen Entstehung und Bestaetigung, in Bars."""
        return self.confirmed_idx - self.idx


def _threshold(atr: np.ndarray, idx: int, theta: float) -> float:
    return float(theta * atr[idx])


def zigzag_from_bars(
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    theta: float,
    scale: int = 0,
    warmup: int = 14,
) -> list[Pivot]:
    """ZigZag direkt auf OHLC-Bars. Streng kausal.

    Ein Bar, der ein neues Extrem setzt, kann im selben Schritt keinen Pivot
    bestaetigen (`elif`). Das ist bewusst konservativ: innerhalb einer Bar ist
    die Reihenfolge von High und Low unbekannt, und eine optimistische
    Annahme waere genau die Art von verstecktem Lookahead, die spaeter nicht
    reproduzierbar ist.

    `warmup` ueberspringt die ersten Bars, in denen die ATR noch aus zu wenigen
    Beobachtungen geschaetzt ist und der Schwellwert damit unbrauchbar waere.

    Der allererste emittierte Pivot ist `is_anchor=True`: er stammt aus der
    Bootstrap-Phase und ist kein belegter Wendepunkt, sondern nur der
    Startpunkt der Serie. Ihn als echten Pivot zu behandeln hiesse, den
    willkuerlichen Anfang des Datenfensters zum Wellenursprung zu erklaeren.
    """
    n = len(high)
    start = min(warmup, max(n - 2, 0))
    if n - start < 2:
        return []

    pivots: list[Pivot] = []

    # Bootstrap: Richtung ist anfangs unbekannt, deshalb laufen Hoch- und
    # Tiefpunkt parallel mit, bis eine Seite den Schwellwert reisst.
    direction = 0
    hi_price, hi_idx = high[start], start
    lo_price, lo_idx = low[start], start

    for i in range(start + 1, n):
        if direction == 0:
            if high[i] > hi_price:
                hi_price, hi_idx = high[i], i
            if low[i] < lo_price:
                lo_price, lo_idx = low[i], i

            down = hi_price - low[i]
            up = high[i] - lo_price
            if down >= _threshold(atr, hi_idx, theta) and down >= up:
                pivots.append(Pivot(hi_idx, float(hi_price), HIGH, i, scale, True))
                direction = LOW
                lo_price, lo_idx = low[i], i
            elif up >= _threshold(atr, lo_idx, theta):
                pivots.append(Pivot(lo_idx, float(lo_price), LOW, i, scale, True))
                direction = HIGH
                hi_price, hi_idx = high[i], i

        elif direction == HIGH:
            if high[i] > hi_price:
                hi_price, hi_idx = high[i], i
            elif hi_price - low[i] >= _threshold(atr, hi_idx, theta):
                pivots.append(Pivot(hi_idx, float(hi_price), HIGH, i, scale))
                direction = LOW
                lo_price, lo_idx = low[i], i

        else:  # direction == LOW
            if low[i] < lo_price:
                lo_price, lo_idx = low[i], i
            elif high[i] - lo_price >= _threshold(atr, lo_idx, theta):
                pivots.append(Pivot(lo_idx, float(lo_price), LOW, i, scale))
                direction = HIGH
                hi_price, hi_idx = high[i], i

    return pivots


def zigzag_from_pivots(
    pivots: list[Pivot], atr: np.ndarray, theta: float, scale: int
) -> list[Pivot]:
    """Vergroebert eine bestehende Pivot-Folge zur naechsten Lattice-Ebene.

    Der entscheidende Punkt: die groebere Ebene wird NICHT unabhaengig auf den
    Bars gerechnet, sondern auf der feineren Pivot-Folge. Dadurch ist
    `pivots(scale k+1)` per Konstruktion eine echte Teilmenge von
    `pivots(scale k)`. Genau das macht "Zyklusgrad" wohldefiniert: ein Grad
    ist eine Ebene in diesem Baum, und jeder Eltern-Pivot ist zugleich ein
    Kind-Pivot - er kann gar nicht an anderer Stelle liegen.

    Die Bestaetigung erbt den `confirmed_idx` des ausloesenden feinen Pivots.
    Ein grober Pivot ist fruehestens dann bekannt, wenn der feine Pivot, der
    die Gegenbewegung belegt, selbst bestaetigt ist.
    """
    if len(pivots) < 2:
        return []

    out: list[Pivot] = []
    direction = 0
    hi: Pivot | None = None
    lo: Pivot | None = None

    for p in pivots:
        if direction == 0:
            if hi is None or p.price > hi.price:
                hi = p
            if lo is None or p.price < lo.price:
                lo = p

            down = hi.price - p.price
            up = p.price - lo.price
            if down >= _threshold(atr, hi.idx, theta) and down >= up:
                out.append(Pivot(hi.idx, hi.price, HIGH, p.confirmed_idx, scale, True))
                direction = LOW
                lo = p
            elif up >= _threshold(atr, lo.idx, theta):
                out.append(Pivot(lo.idx, lo.price, LOW, p.confirmed_idx, scale, True))
                direction = HIGH
                hi = p

        elif direction == HIGH:
            if p.price > hi.price:
                hi = p
            elif hi.price - p.price >= _threshold(atr, hi.idx, theta):
                out.append(Pivot(hi.idx, hi.price, HIGH, p.confirmed_idx, scale))
                direction = LOW
                lo = p

        else:  # direction == LOW
            if p.price < lo.price:
                lo = p
            elif p.price - lo.price >= _threshold(atr, lo.idx, theta):
                out.append(Pivot(lo.idx, lo.price, LOW, p.confirmed_idx, scale))
                direction = HIGH
                hi = p

    return out


def to_frame(pivots: list[Pivot], index: pd.DatetimeIndex) -> pd.DataFrame:
    """Pivot-Liste als DataFrame mit echten Zeitstempeln."""
    if not pivots:
        return pd.DataFrame(
            columns=["idx", "ts", "price", "kind", "confirmed_idx", "confirmed_ts",
                     "scale", "lag", "is_anchor"]
        )
    return pd.DataFrame(
        {
            "idx": [p.idx for p in pivots],
            "ts": [index[p.idx] for p in pivots],
            "price": [p.price for p in pivots],
            "kind": [p.kind for p in pivots],
            "confirmed_idx": [p.confirmed_idx for p in pivots],
            "confirmed_ts": [index[p.confirmed_idx] for p in pivots],
            "scale": [p.scale for p in pivots],
            "lag": [p.lag for p in pivots],
            "is_anchor": [p.is_anchor for p in pivots],
        }
    )
