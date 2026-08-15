#!/usr/bin/env python3
"""Prueft, ob feinere Substruktur den Einstieg tatsaechlich verbessert.

Hintergrund: ein erfahrener Analyst schaut fuer einen 1d- oder 4h-Trade in
den 15m- oder 5m-Chart, um den Einstieg zu praezisieren. Der Nutzen daraus
entsteht aber nur, wenn der engere Einstieg auch einen engeren Stop erlaubt -
sonst verbessert die feinere Aufloesung lediglich den Einstandspreis,
waehrend das Risiko unveraendert an Welle 1 haengt.

Verglichen werden deshalb zwei Dinge gleichzeitig:

  stop_mode      "rule"    Stop hinter dem Start von Welle 1 (Regel-Invalidierung)
                 "trigger" Stop knapp hinter dem ausloesenden feinen Pivot
  trigger_offset wie viele Lattice-Ebenen unter dem Kontext der Ausloeser liegt

Wichtig fuer die Bewertung: ein engerer Stop erhoeht das R jedes Gewinners,
aber auch die Ausstoppquote. Entscheidend ist deshalb allein der
Erwartungswert - und ob er den richtungsgleichen Placebo schlaegt.

    python scripts/test_fractal_entry.py --timeframes 4h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from ew import pivots  # noqa: E402
from ew.backtest.engine import Costs, ExitPolicy, run  # noqa: E402
from ew.data import store  # noqa: E402
from ew.forecast.signals import scan  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d", "4h"])
    ap.add_argument("--context", nargs="*", type=int, default=[4, 5, 6])
    ap.add_argument("--offsets", nargs="*", type=int, default=[1, 2, 3, 4])
    args = ap.parse_args()

    policy = ExitPolicy(target_r=3.0, breakeven_at_r=1.0)
    costs = Costs()
    ctx_scales = tuple(args.context)

    # Daten einmal laden und Lattice einmal bauen - der teure Teil.
    prepared = []
    for tf in args.timeframes:
        for src, sym, t in store.usable(min_bars=800, timeframes=(tf,),
                                        exclude_holdout=True):
            df = store.load(src, sym, t)
            prepared.append((sym, t, df, pivots.build(df)))
    print(f"Instrumente/Timeframes geladen: {len(prepared)}\n")

    print(f"{'Stop':<9}{'Offset':>7}{'n':>7}{'Erwart.':>10}{'Treffer':>9}"
          f"{'OGew':>8}{'OVerl':>8}{'Summe R':>10}")
    print("-" * 68)

    results = {}
    for mode in ("rule", "trigger"):
        for off in args.offsets:
            trades = []
            for sym, tf, df, lat in prepared:
                sigs = scan(lat, df, context_scales=ctx_scales,
                            trigger_offset=off, stop_mode=mode,
                            with_guidelines=False)
                trades += run(df, sigs, costs=costs, policy=policy,
                              symbol=sym, timeframe=tf)
            if len(trades) < 30:
                continue
            r = np.array([t.r_multiple for t in trades])
            w, l = r[r > 0], r[r <= 0]
            results[(mode, off)] = r
            print(f"{mode:<9}{off:>7}{len(r):>7}{r.mean():>+10.3f}"
                  f"{(r > 0).mean():>9.1%}"
                  f"{(w.mean() if len(w) else 0):>+8.2f}"
                  f"{(l.mean() if len(l) else 0):>+8.2f}{r.sum():>+10.1f}")

    # Direkter Vergleich der Stop-Varianten bei gleichem Offset.
    print("\n=== Stop-Variante im direkten Vergleich (gleicher Offset) ===")
    print(f"{'Offset':<8}{'rule':>10}{'trigger':>10}{'Differenz':>12}{'t':>7}")
    print("-" * 47)
    for off in args.offsets:
        a = results.get(("rule", off))
        b = results.get(("trigger", off))
        if a is None or b is None:
            continue
        d = b.mean() - a.mean()
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        print(f"{off:<8}{a.mean():>+10.3f}{b.mean():>+10.3f}{d:>+12.3f}"
              f"{d / se if se > 0 else np.nan:>7.2f}")

    print("\nLesart: ein engerer Stop erhoeht OGew und senkt die Trefferquote.")
    print("Nur der Erwartungswert entscheidet, ob der Tausch sich lohnt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
