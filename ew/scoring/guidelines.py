"""Richtlinien als bewertbare Merkmale.

Regeln muessen erfuellt sein, sonst ist die Zaehlung ungueltig. Richtlinien
sind typisch, aber nicht zwingend - je mehr von ihnen zutreffen, desto
tragfaehiger die Zaehlung. Genau diese Abstufung wird hier messbar gemacht.

Zwei Einschraenkungen, die den Aufbau bestimmen:

**Nur Einstiegszeitpunkt-Wissen.** Bewertet wird ausschliesslich, was zum
Zeitpunkt des Signals bekannt ist: Welle 1 und die Korrektur. Kanalbildung,
Alternation zwischen Welle 2 und 4 oder Gleichheit von Welle 1 und 5 lassen
sich erst spaeter pruefen und waeren hier Lookahead - auch wenn sie im Buch
prominent stehen.

**Keine Fibonacci-Naehe.** Befund F5 hat gezeigt, dass die Naehe zu einem
Fib-Level in diesen Daten nicht haeufiger auftritt als in strukturlosen
Surrogaten. Was hier stattdessen geprueft wird, ist etwas anderes: ob das
Retracement in einem *breiten typischen Band* liegt. Das ist eine
schwaechere und pruefbare Aussage, keine Punktlandung auf 0.618.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..pivots.indicators import atr, macd, rsi
from ..pivots.lattice import Lattice
from ..pivots.zigzag import Pivot


@dataclass
class GuidelineSet:
    """Ergebnis der Richtlinienpruefung fuer ein Setup."""

    hits: dict[str, bool] = field(default_factory=dict)
    values: dict[str, float] = field(default_factory=dict)

    @property
    def score(self) -> int:
        return sum(self.hits.values())

    @property
    def n(self) -> int:
        return len(self.hits)

    @property
    def fraction(self) -> float:
        return self.score / self.n if self.n else 0.0


@dataclass
class Context:
    """Alles, was zur Bewertung eines Setups gebraucht wird."""

    lat: Lattice
    df: pd.DataFrame
    rsi14: pd.Series
    macd_hist: pd.Series
    atr14: pd.Series
    vol_ma: pd.Series

    @classmethod
    def build(cls, lat: Lattice, df: pd.DataFrame) -> "Context":
        return cls(
            lat=lat,
            df=df,
            rsi14=rsi(df, 14),
            macd_hist=macd(df)["hist"],
            atr14=atr(df, 14),
            vol_ma=df["volume"].rolling(50, min_periods=5).mean(),
        )


def _subwaves(lat: Lattice, scale: int, a: Pivot, b: Pivot, depth: int = 3) -> int:
    """Beste Unterwellenzahl ueber die naechsten feineren Ebenen."""
    best = 0
    for s in range(scale - 1, max(scale - 1 - depth, -1), -1):
        inner = [p for p in lat.pivots(s) if a.idx < p.idx < b.idx]
        n = len(inner) + 1
        if n >= 3:
            return n
        best = max(best, n)
    return best


def evaluate(
    ctx: Context,
    p0: Pivot,
    p1: Pivot,
    trigger: Pivot,
    bar: int,
    context_scale: int,
    direction: int,
) -> GuidelineSet:
    """Prueft die zum Signalzeitpunkt bekannten Richtlinien.

    `p0`/`p1` spannen Welle 1 auf, `trigger` ist das bestaetigte Ende der
    Korrektur. Alle Groessen werden ausschliesslich aus Bars <= `bar`
    berechnet.
    """
    g = GuidelineSet()
    df, lat = ctx.df, ctx.lat
    w1 = abs(p1.price - p0.price)

    # --- G1: Welle 1 zerfaellt in eine motive Fuenferstruktur -------------
    n1 = _subwaves(lat, context_scale, p0, p1)
    g.values["w1_subwaves"] = n1
    g.hits["w1_ist_fuenf"] = n1 in (5, 9, 13)

    # --- G2: Die Korrektur zerfaellt in eine korrektive Dreierstruktur ----
    n2 = _subwaves(lat, context_scale, p1, trigger)
    g.values["w2_subwaves"] = n2
    g.hits["w2_ist_drei"] = n2 in (3, 7, 11)

    # --- G3: Retracement im typischen Band --------------------------------
    # Bewusst ein breites Band, keine Punktlandung auf einem Fib-Level:
    # Befund F5 hat gezeigt, dass Fib-Naehe kein Signal traegt.
    retr = abs(trigger.price - p1.price) / w1 if w1 > 0 else np.nan
    g.values["retracement"] = retr
    g.hits["retrace_typisch"] = 0.35 <= retr <= 0.80

    # --- G4: Korrektur ist zeitlich kuerzer als der Impuls ----------------
    t1 = max(p1.idx - p0.idx, 1)
    t2 = trigger.idx - p1.idx
    g.values["zeit_verhaeltnis"] = t2 / t1
    g.hits["korrektur_kuerzer"] = t2 <= t1

    # --- G5: Volumen kontrahiert in der Korrektur -------------------------
    # Klassisches Merkmal: die Gegenbewegung laeuft auf abnehmendem Umsatz.
    v1 = float(df["volume"].iloc[p0.idx : p1.idx + 1].mean())
    v2 = float(df["volume"].iloc[p1.idx : trigger.idx + 1].mean())
    g.values["vol_verhaeltnis"] = v2 / v1 if v1 > 0 else np.nan
    g.hits["volumen_kontrahiert"] = bool(v1 > 0 and v2 < v1)

    # --- G6: Momentum-Schub in Welle 1 ------------------------------------
    # Eine echte erste Welle bewegt sich mit Nachdruck; ein blosses Rauschen
    # tut das nicht.
    h = ctx.macd_hist
    m1 = float(h.iloc[p0.idx : p1.idx + 1].abs().max())
    m_prior = float(h.iloc[max(0, p0.idx - t1) : p0.idx + 1].abs().max())
    g.values["momentum_verhaeltnis"] = m1 / m_prior if m_prior > 0 else np.nan
    g.hits["momentum_schub"] = bool(m_prior > 0 and m1 > m_prior)

    # --- G7: Momentum-Divergenz am Korrekturende --------------------------
    # Das Extrem der Korrektur zeigt schwaecheres Momentum als der Kurs
    # nahelegt - ein Hinweis auf Erschoepfung der Gegenbewegung.
    r = ctx.rsi14
    if direction > 0:
        g.hits["divergenz"] = bool(
            trigger.price < p0.price * 1.02
            and r.iloc[trigger.idx] > r.iloc[p0.idx]
        )
    else:
        g.hits["divergenz"] = bool(
            trigger.price > p0.price * 0.98
            and r.iloc[trigger.idx] < r.iloc[p0.idx]
        )
    g.values["rsi_trigger"] = float(r.iloc[trigger.idx])

    # --- G8: Uebergeordnete Ebene stimmt der Richtung zu ------------------
    # Top-down: das Setup soll nicht gegen den naechstgroesseren Grad laufen.
    #
    # Gemessen wird die Lage des Kurses relativ zum letzten bestaetigten
    # Pivot der groeberen Ebene, nicht die Richtung der letzten zwei Pivots
    # dort. Grund ist Befund F1: auf der groeberen Ebene liegen wegen der
    # langen Bestaetigungsverzoegerung oft gar keine zwei Pivots vor - eine
    # Zwei-Pivot-Bedingung waere in ueber 90 % der Faelle nicht auswertbar
    # und wuerde als "nicht erfuellt" gezaehlt statt als "unbekannt".
    higher = context_scale + 1
    hp = [p for p in lat.visible_at(higher, bar) if not p.is_anchor]
    if hp:
        last = hp[-1]
        px = float(df["close"].iloc[bar])
        # Nach einem bestaetigten Tief laeuft der groebere Grad aufwaerts,
        # solange der Kurs darueber notiert - und umgekehrt.
        hd = 1 if (last.kind < 0 and px > last.price) else (
            -1 if (last.kind > 0 and px < last.price) else 0
        )
        g.values["hoehere_ebene"] = hd
        g.hits["hoehere_ebene_stimmt"] = hd == direction
    else:
        g.values["hoehere_ebene"] = np.nan
        g.hits["hoehere_ebene_stimmt"] = False

    # --- G9: Welle 1 ist gross gegenueber vergleichbaren Wellen -----------
    # Ein ATR-Vergleich taugt hier nicht: der ZigZag-Schwellwert ist selbst
    # ATR-normiert, weshalb praktisch jede Welle die Huerde nimmt (98,7 % in
    # der ersten Fassung). Eine Richtlinie, die immer zutrifft, unterscheidet
    # nichts. Verglichen wird deshalb mit den letzten Wellen derselben Ebene.
    piv = [p for p in lat.visible_at(context_scale, bar) if not p.is_anchor]
    recent = [abs(b.price - a.price) / a.price
              for a, b in zip(piv[-11:], piv[-10:]) if a.price > 0]
    if len(recent) >= 5 and p0.price > 0:
        rel = w1 / p0.price
        g.values["w1_perzentil"] = float(np.mean([rel > x for x in recent]))
        g.hits["w1_signifikant"] = g.values["w1_perzentil"] >= 0.6
    else:
        g.values["w1_perzentil"] = np.nan
        g.hits["w1_signifikant"] = False

    return g


GUIDELINE_NAMES = [
    "w1_ist_fuenf", "w2_ist_drei", "retrace_typisch", "korrektur_kuerzer",
    "volumen_kontrahiert", "momentum_schub", "divergenz",
    "hoehere_ebene_stimmt", "w1_signifikant",
]
