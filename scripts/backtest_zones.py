#!/usr/bin/env python3
"""Backtest des antizipativen Zonen-Systems.

    python scripts/backtest_zones.py --timeframes 1d 4h

Getestet werden beide Stop-Varianten, da die Beschreibung an dieser Stelle
mehrdeutig ist:
  "operative" - Stop unter der Gegenkante der operativen Zone
  "extended"  - Stop unter der Gegenkante des Bandes 0.618-1.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ew import pivots  # noqa: E402
from ew.backtest.engine import Costs, evaluate, run_limit  # noqa: E402
from ew.data import store  # noqa: E402
from ew.forecast import zone_signals  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d", "4h"])
    ap.add_argument("--context", nargs="*", type=int, default=[4, 5, 6])
    ap.add_argument("--min-rr", type=float, default=2.0)
    ap.add_argument("--holdout", action="store_true")
    args = ap.parse_args()

    costs = Costs()
    ctx = tuple(args.context)

    prepared = []
    for tf in args.timeframes:
        ds = store.usable(min_bars=800, timeframes=(tf,),
                          exclude_holdout=not args.holdout)
        if args.holdout:
            from ew.data.universe import HOLDOUT
            ds = [d for d in ds if d[1] in HOLDOUT]
        for src, sym, t in ds:
            df = store.load(src, sym, t)
            prepared.append((sym, t, df, pivots.build(df)))

    print(f"{'Universum':<12}{'Holdout' if args.holdout else 'Training'}")
    print(f"Instrument/TF-Kombinationen: {len(prepared)}   min RR {args.min_rr}\n")

    for stop_from in ("operative", "extended"):
        trades, stats = [], {}
        for sym, tf, df, lat in prepared:
            sigs = zone_signals.scan(lat, df, context_scales=ctx,
                                     min_rr=args.min_rr, stop_from=stop_from)
            t, s = run_limit(df, sigs, costs=costs, symbol=sym, timeframe=tf)
            trades += t
            for k, v in s.items():
                stats[k] = stats.get(k, 0) + v

        if not trades:
            print(f"Stop-Variante {stop_from}: keine Trades\n")
            continue

        r = np.array([t.r_multiple for t in trades])
        m = evaluate(trades)
        ts = [t.entry_ts for t in trades] + [t.exit_ts for t in trades]
        span = (max(ts) - min(ts)).days / 365.25

        print(f"=== Stop-Variante: {stop_from} ===")
        print(f"  Orders gestellt       {stats.get('gestellt', 0)}")
        print(f"  davon gefuellt        {stats.get('gefuellt', 0)} "
              f"({stats.get('gefuellt', 0) / max(stats.get('gestellt', 1), 1):.1%})")
        print(f"  verfallen / verpasst  {stats.get('verfallen', 0)} / "
              f"{stats.get('verpasst', 0)}")
        print(f"  Trades                {m.n_trades}")
        print(f"  Trefferquote          {m.win_rate:.1%}")
        print(f"  Durchschn. Gewinn     {m.avg_win_r:+.2f} R")
        print(f"  Durchschn. Verlust    {m.avg_loss_r:+.2f} R")
        print(f"  Erwartungswert        {m.expectancy_r:+.3f} R")
        print(f"  Summe                 {m.total_r:+.1f} R  ueber {span:.1f} Jahre")
        print(f"  R pro Jahr            {m.total_r / span:+.1f} R")
        print(f"  Max. Drawdown         {m.max_dd_r:.1f} R")

        df_t = pd.DataFrame([{
            "r": t.r_multiple, "konfluenz": t.quality, "tf": t.timeframe,
            **t.guideline_hits,
        } for t in trades])

        print("\n  Nach Konfluenz (Zahl stuetzender Projektionen):")
        for k, s in df_t.groupby("konfluenz")["r"]:
            if len(s) >= 15:
                print(f"    {k}: n={len(s):>5}  E={s.mean():+.3f} R  "
                      f"Treffer {(s > 0).mean():.1%}")

        for flag in ("squeeze", "erweitert"):
            if flag in df_t.columns:
                a = df_t.loc[df_t[flag] == True, "r"]   # noqa: E712
                b = df_t.loc[df_t[flag] == False, "r"]  # noqa: E712
                if len(a) >= 15 and len(b) >= 15:
                    print(f"  {flag:<12} ja: n={len(a):>5} E={a.mean():+.3f} | "
                          f"nein: n={len(b):>5} E={b.mean():+.3f}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
