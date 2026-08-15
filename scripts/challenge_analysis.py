#!/usr/bin/env python3
"""Was liefert das System unter Funding-Bedingungen?

Simuliert wird auf der **empirischen R-Verteilung** aus dem Backtest, nicht
auf einer Normalannahme - die Schiefe der Verteilung ist fuer ein
Barriereproblem entscheidend.

Ausgegeben werden drei Dinge:

  1. das Risiko pro Trade, das die Bestehenswahrscheinlichkeit maximiert
  2. der Vergleich gegen die Wahrscheinlichkeit **ohne jede Edge** - die
     Bezugsgroesse, ohne die ein Ergebnis nicht einzuordnen ist
  3. die realistisch erreichbare Monatsrendite bei der Trade-Frequenz, die
     das System tatsaechlich erzeugt

    python scripts/challenge_analysis.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from ew import pivots  # noqa: E402
from ew.backtest.engine import Costs, run_limit  # noqa: E402
from ew.data import store  # noqa: E402
from ew.forecast import zone_signals  # noqa: E402
from ew.risk.challenge import Rules, optimal_risk, simulate, theoretical_no_edge  # noqa: E402


def collect_r(timeframes: list[str]) -> tuple[np.ndarray, float]:
    """R-Verteilung und Trades pro Jahr aus dem besten verfuegbaren System."""
    costs = Costs()
    trades = []
    for tf in timeframes:
        for src, sym, t in store.usable(min_bars=800, timeframes=(tf,),
                                        exclude_holdout=True):
            df = store.load(src, sym, t)
            lat = pivots.build(df)
            sigs = zone_signals.scan(lat, df, context_scales=(4, 5, 6),
                                     stop_from="extended", with_indicators=False)
            tr, _ = run_limit(df, sigs, costs=costs, symbol=sym, timeframe=t)
            trades += tr

    r = np.array([t.r_multiple for t in trades], dtype="float64")
    ts = [t.entry_ts for t in trades]
    span_years = (max(ts) - min(ts)).days / 365.25 if ts else np.nan
    return r, len(r) / span_years if span_years else np.nan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d", "4h"])
    ap.add_argument("--paths", type=int, default=20_000)
    args = ap.parse_args()

    r, per_year = collect_r(args.timeframes)
    per_day = per_year / 252.0

    print("=== Empirische R-Verteilung (Zonen-System, Training-Universum) ===")
    print(f"  Trades              {len(r):,}")
    print(f"  Erwartung           {r.mean():+.3f} R")
    print(f"  Trefferquote        {(r > 0).mean():.1%}")
    print(f"  Durchschn. Gewinn   {r[r > 0].mean():+.2f} R")
    print(f"  Durchschn. Verlust  {r[r <= 0].mean():+.2f} R")
    print(f"  Trades/Jahr         {per_year:.0f}   Trades/Tag {per_day:.2f}")

    rules = Rules(trades_per_day=max(per_day, 0.05))
    no_edge = theoretical_no_edge(rules)
    print(f"\n=== Challenge: Ziel {rules.profit_target:.0%}, "
          f"max. DD {rules.max_drawdown:.0%}, Tageslimit "
          f"{rules.daily_loss_limit:.0%}, {rules.max_days} Tage ===")
    print(f"  Bezugsgroesse ohne jede Edge: {no_edge:.1%}\n")

    best, results = optimal_risk(r, rules, n_paths=args.paths)
    print(f"{'Risiko':>8}{'bestanden':>12}{'DD-Aus':>10}{'Zeit-Aus':>10}"
          f"{'Tageslimit':>12}{'Median Tage':>13}")
    print("-" * 65)
    for res in results:
        mark = "  <-- Optimum" if res.risk == best else ""
        print(f"{res.risk:>8.2%}{res.p_pass:>12.1%}{res.p_fail_dd:>10.1%}"
              f"{res.p_fail_time:>10.1%}{res.p_daily_breach:>12.1%}"
              f"{res.median_days:>13.0f}{mark}")

    top = max(results, key=lambda z: z.p_pass)
    print(f"\n  Optimales Risiko: {best:.2%} pro Trade")
    print(f"  Bestehenswahrscheinlichkeit: {top.p_pass:.1%} "
          f"gegen {no_edge:.1%} ohne Edge")

    # Realistische Monatsrendite bei der tatsaechlichen Frequenz.
    print("\n=== Realistisch erreichbare Monatsrendite ===")
    per_month = per_year / 12.0
    for risk in (0.005, 0.01, 0.02, best):
        monthly = (1 + risk * r.mean()) ** per_month - 1
        print(f"  Risiko {risk:>6.2%}: {monthly:>+7.2%} pro Monat "
              f"({(1 + monthly) ** 12 - 1:>+8.1%} pro Jahr) "
              f"bei {per_month:.1f} Trades/Monat")

    need = np.log(1.20) / np.log(1 + 0.01)
    print(f"\n  Fuer 20 %/Monat noetig: {need:.1f} R pro Monat bei 1 % Risiko")
    print(f"  Das System liefert:     {per_month * r.mean():.2f} R pro Monat")
    if per_month * r.mean() > 0:
        print(f"  Faktor:                 {need / (per_month * r.mean()):.0f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
