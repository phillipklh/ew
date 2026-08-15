#!/usr/bin/env python3
"""Backtest der Signal-Engine ueber das Trainingsuniversum.

    python scripts/backtest.py
    python scripts/backtest.py --timeframe 1d --context 4 5 6

Das Holdout-Universum bleibt aussen vor und wird erst ganz am Ende einmal
angefasst - es ist der einzige echte Schutz gegen Ueberanpassung ueber viele
Iterationen hinweg.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ew import pivots  # noqa: E402
from ew.backtest.engine import Costs, ExitPolicy, evaluate, run  # noqa: E402
from ew.data import store  # noqa: E402
from ew.forecast.signals import scan  # noqa: E402


def backtest_one(src, sym, tf, context_scales, policy, costs, trigger_offset):
    df = store.load(src, sym, tf)
    lat = pivots.build(df)
    sigs = scan(lat, df, context_scales=context_scales, trigger_offset=trigger_offset)
    trades = run(df, sigs, costs=costs, policy=policy, symbol=sym)
    return df, sigs, trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", default="1d")
    ap.add_argument("--context", nargs="*", type=int, default=[4, 5, 6])
    ap.add_argument("--trigger-offset", type=int, default=2)
    ap.add_argument("--target-r", type=float, default=3.0)
    ap.add_argument("--breakeven-r", type=float, default=1.0)
    ap.add_argument("--holdout", action="store_true",
                    help="Statt Training das reservierte Holdout auswerten")
    args = ap.parse_args()

    policy = ExitPolicy(target_r=args.target_r, breakeven_at_r=args.breakeven_r)
    costs = Costs()
    ctx = tuple(args.context)

    datasets = store.usable(min_bars=800, timeframes=(args.timeframe,),
                            exclude_holdout=not args.holdout)
    if args.holdout:
        from ew.data.universe import HOLDOUT
        datasets = [d for d in datasets if d[1] in HOLDOUT]
    if not datasets:
        print("Keine passenden Datensaetze.")
        return 1

    print(f"{'Universum':<12}{'Holdout' if args.holdout else 'Training'}")
    print(f"{'Timeframe':<12}{args.timeframe}   Kontextebenen {ctx}   "
          f"Trigger-Offset {args.trigger_offset}")
    print(f"{'Exit':<12}Ziel {args.target_r}R, Breakeven ab {args.breakeven_r}R, "
          f"Kosten {costs.fee_bps + costs.slippage_bps:.0f} bps/Seite\n")

    all_trades, rows = [], []
    for src, sym, tf in datasets:
        df, sigs, trades = backtest_one(src, sym, tf, ctx, policy, costs,
                                        args.trigger_offset)
        all_trades.extend(trades)
        m = evaluate(trades, df)
        yrs = (df.index[-1] - df.index[0]).days / 365.25
        rows.append({
            "symbol": sym, "jahre": yrs, "signale": len(sigs), "trades": m.n_trades,
            "tr/jahr": m.n_trades / yrs if yrs else float("nan"),
            "trefferq.": m.win_rate, "avg_win_R": m.avg_win_r,
            "avg_loss_R": m.avg_loss_r, "erwartung_R": m.expectancy_r,
            "summe_R": m.total_r, "R/jahr": m.total_r / yrs if yrs else float("nan"),
        })

    res = pd.DataFrame(rows)
    pd.set_option("display.width", 170)
    print("=== Je Instrument ===")
    print(res.round(3).to_string(index=False))

    if not all_trades:
        print("\nKeine Trades erzeugt.")
        return 0

    # Gesamtbewertung auf echtem Kalender, nicht auf Bar-Indizes.
    m = evaluate(all_trades, n_configs_tried=1)
    ts = [t.entry_ts for t in all_trades] + [t.exit_ts for t in all_trades]
    span = (max(ts) - min(ts)).days / 365.25

    r = np.array([t.r_multiple for t in all_trades])
    print("\n=== Portfolio gesamt ===")
    print(f"  Zeitraum              {min(ts).date()} .. {max(ts).date()}  "
          f"({span:.1f} Jahre)")
    print(f"  Trades                {m.n_trades}")
    print(f"  Trefferquote          {m.win_rate:.1%}")
    print(f"  Durchschn. Gewinn     {m.avg_win_r:+.2f} R")
    print(f"  Durchschn. Verlust    {m.avg_loss_r:+.2f} R   "
          f"<- Ziel: deutlich ueber -1.0 R")
    print(f"  Erwartungswert        {m.expectancy_r:+.3f} R pro Trade")
    print(f"  Summe                 {m.total_r:+.1f} R")
    print(f"  Trades/Jahr           {m.trades_per_year:.1f}")
    print(f"  R pro Jahr            {m.total_r / span:+.1f} R")
    print(f"  Max. Drawdown         {m.max_dd_r:.1f} R  ({m.max_dd_pct:.1%} bei 1 % Risiko)")
    print(f"  CAGR                  {m.cagr:.1%}")
    print(f"  MAR                   {m.mar:.2f}")

    print("\n  Ausstiegsgruende:")
    for reason, n in pd.Series([t.reason for t in all_trades]).value_counts().items():
        share = n / len(all_trades)
        avg = np.mean([t.r_multiple for t in all_trades if t.reason == reason])
        print(f"    {reason:<12}{n:>5} ({share:>5.1%})   Mittel {avg:+.2f} R")

    print("\n  R-Verteilung:")
    for q in (5, 25, 50, 75, 95):
        print(f"    p{q:<3}{np.percentile(r, q):+8.2f} R")

    # Die Zielgroesse aus der Risikorechnung: fuer +100 %/Jahr bei 1 % Risiko
    # braucht es rund 70 R netto pro Jahr.
    need = np.log(2) / np.log(1.01)
    print(f"\n  Benoetigt fuer +100 %/Jahr: {need:.0f} R/Jahr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
