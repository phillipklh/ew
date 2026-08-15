"""Signalerzeugung aus laufenden Wellenhypothesen.

Der Aufbau folgt zwingend aus Befund F1: die Bestaetigung eines Pivots
trifft auf jeder Skala rund 1,5-mal so spaet ein, wie die Welle gedauert
hat. Wer auf die Bestaetigung in dem Grad wartet, den er handeln will,
kommt systematisch zu spaet. Handelbar wird die Struktur erst ueber zwei
Ebenen hinweg:

    Kontext  (grobe Ebene k)   Richtung und Invalidierung
    Ausloeser (feine Ebene j<k) Zeitpunkt des Einstiegs

Der Hebel dabei ist die Verschachtelung des Lattice: ein Pivot existiert auf
allen feineren Ebenen mit identischem Preis und Zeitpunkt - aber er wird dort
**frueher bestaetigt**, weil der Schwellwert kleiner ist. Die grobe Ebene
liefert also die These, die feine den rechtzeitigen Beleg dafuer, dass die
Korrektur vorbei ist.

Der Stop kommt nicht aus einem Indikator, sondern aus der Regel selbst:
Welle 2 darf den Start von Welle 1 nie unterschreiten. Das ist der Grund,
warum Elliott-Setups strukturell enge Verlustbegrenzungen haben - und die
Voraussetzung dafuer, dass der durchschnittliche Verlust unter 1R bleibt,
was die Drawdown-Rechnung zwingend verlangt.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..pivots.lattice import Lattice
from ..pivots.zigzag import Pivot


@dataclass
class Signal:
    """Ein handelbares Setup zum Zeitpunkt `bar`."""

    bar: int              # Bar, an dem das Signal entsteht (Close)
    direction: int        # +1 long, -1 short
    stop: float           # Regel-Invalidierung
    context_scale: int
    trigger_scale: int
    wave1_start: Pivot
    wave1_end: Pivot
    trigger_pivot: Pivot  # bestaetigtes Ende der Korrektur auf feiner Ebene
    retrace: float        # wie weit die Korrektur Welle 1 zurueckgeholt hat
    #: Erfuellte Richtlinien. Regeln sind Pflicht, Richtlinien sind Qualitaet -
    #: je mehr zutreffen, desto tragfaehiger die Zaehlung.
    guidelines: object | None = None

    @property
    def quality(self) -> int:
        return self.guidelines.score if self.guidelines is not None else -1

    def risk(self, entry: float) -> float:
        return abs(entry - self.stop)


def _last_two_confirmed(lat: Lattice, scale: int, bar: int) -> tuple[Pivot, Pivot] | None:
    """Die beiden zuletzt auf `scale` bestaetigten echten Pivots."""
    piv = [p for p in lat.visible_at(scale, bar) if not p.is_anchor]
    if len(piv) < 2:
        return None
    return piv[-2], piv[-1]


def generate(
    lat: Lattice,
    df: pd.DataFrame,
    bar: int,
    *,
    context_scale: int,
    trigger_offset: int = 2,
    min_retrace: float = 0.15,
    max_retrace: float = 0.95,
    stop_mode: str = "rule",
    trigger_buffer: float = 0.10,
    ctx=None,
) -> list[Signal]:
    """Signale an Bar `bar`. Streng kausal - nur bis `bar` Bestaetigtes.

    Bedingungen:
      1. Auf der Kontextebene liegen zwei bestaetigte Pivots vor, die eine
         Welle 1 aufspannen.
      2. Der Kurs hat den Start von Welle 1 nicht verletzt - sonst waere die
         Zaehlung regelwidrig und die These tot.
      3. Die Korrektur liegt in einem sinnvollen Band. Ein Retracement unter
         `min_retrace` ist noch keine Korrektur, eines ueber `max_retrace`
         laesst kaum Abstand zum Stop und damit kein brauchbares
         Chance-Risiko-Verhaeltnis.
      4. Auf der feinen Ebene wurde genau an dieser Bar ein Gegenextrem
         bestaetigt - der Beleg, dass die Korrektur zu Ende sein koennte.
    """
    trigger_scale = context_scale - trigger_offset
    if trigger_scale < 0:
        return []

    pair = _last_two_confirmed(lat, context_scale, bar)
    if pair is None:
        return []
    p0, p1 = pair

    d = 1 if p1.price > p0.price else -1
    w1 = abs(p1.price - p0.price)
    if w1 <= 0:
        return []

    # Bedingung 2: Regel-Invalidierung noch nicht verletzt.
    lo = float(df["low"].iloc[p1.idx : bar + 1].min())
    hi = float(df["high"].iloc[p1.idx : bar + 1].max())
    if (d > 0 and lo <= p0.price) or (d < 0 and hi >= p0.price):
        return []

    # Bedingung 4: feiner Pivot genau jetzt bestaetigt, Richtung passend.
    fine = [p for p in lat.visible_at(trigger_scale, bar) if not p.is_anchor]
    if not fine:
        return []
    trig = fine[-1]
    if trig.confirmed_idx != bar:
        return []
    # Ein Long braucht ein bestaetigtes Tief als Korrekturende, ein Short ein Hoch.
    if trig.kind != -d:
        return []
    if trig.idx <= p1.idx:
        return []

    # Bedingung 3: Korrekturtiefe.
    retr = abs(trig.price - p1.price) / w1
    if not (min_retrace <= retr <= max_retrace):
        return []

    gl = None
    if ctx is not None:
        from ..scoring.guidelines import evaluate as eval_guidelines

        gl = eval_guidelines(ctx, p0, p1, trig, bar, context_scale, d)

    # Zwei Stop-Varianten, die sich wirtschaftlich stark unterscheiden:
    #
    #   "rule"    hinter dem Start von Welle 1. Das ist die Regel-Invalidierung:
    #             erst dort ist die Zaehlung widerlegt. Weit, dafuer selten
    #             faelschlich getroffen.
    #   "trigger" knapp hinter dem ausloesenden feinen Pivot. Deutlich enger,
    #             damit ist dieselbe Bewegung ein Vielfaches an R wert - der
    #             eigentliche Hebel der Fraktal-Praezision. Preis dafuer ist
    #             eine hoehere Ausstoppquote.
    #
    # Ohne diese Unterscheidung bleibt ein feinerer Trigger wirkungslos: er
    # verbessert nur den Einstieg, waehrend das Risiko unveraendert an Welle 1
    # haengt.
    if stop_mode == "trigger":
        buf = trigger_buffer * abs(trig.price - p1.price)
        stop = trig.price - d * buf
        # Der taktische Stop darf die Regel-Invalidierung nicht ueberschreiten:
        # jenseits davon waere die Zaehlung ohnehin tot.
        if (d > 0 and stop < p0.price) or (d < 0 and stop > p0.price):
            stop = p0.price
    else:
        stop = p0.price

    return [
        Signal(
            bar=bar,
            direction=d,
            stop=stop,
            context_scale=context_scale,
            trigger_scale=trigger_scale,
            wave1_start=p0,
            wave1_end=p1,
            trigger_pivot=trig,
            retrace=retr,
            guidelines=gl,
        )
    ]


def scan(
    lat: Lattice,
    df: pd.DataFrame,
    *,
    context_scales: tuple[int, ...] = (4, 5, 6),
    trigger_offset: int = 2,
    start_bar: int | None = None,
    with_guidelines: bool = True,
    **kw,
) -> list[Signal]:
    """Laeuft die gesamte Historie Bar fuer Bar ab und sammelt alle Signale."""
    n = len(df)
    lo = start_bar if start_bar is not None else 0

    ctx = None
    if with_guidelines:
        from ..scoring.guidelines import Context

        ctx = Context.build(lat, df)

    out: list[Signal] = []
    for bar in range(lo, n):
        for cs in context_scales:
            out.extend(
                generate(lat, df, bar, context_scale=cs,
                         trigger_offset=trigger_offset, ctx=ctx, **kw)
            )
    return out
