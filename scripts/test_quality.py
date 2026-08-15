#!/usr/bin/env python3
"""Prueft, ob die Qualitaet einer Zaehlung den Ausgang vorhersagt.

Die Leitfrage: Regeln muessen erfuellt sein, Richtlinien nicht - je mehr
Richtlinien zusaetzlich zutreffen, desto besser sollte das Setup sein.
Trifft das zu, liegt die Edge in der Selektion.

**Warum Monotonie und nicht Schwellwertsuche.** Man koennte alle
Schwellwerte durchprobieren und den besten melden. Bei zehn Kandidaten
findet sich immer einer, der gut aussieht - das ist Suchrauschen, kein
Befund. Belastbar ist die staerkere Aussage: steigt die Erwartung
*durchgehend* mit der Zahl erfuellter Richtlinien? Gemessen wird das ueber
die Rangkorrelation (Spearman) zwischen Score und Ergebnis, die sich durch
Cherry-Picking nicht erzeugen laesst.

Zusaetzlich wird jede Richtlinie einzeln bewertet, damit sichtbar wird,
welche traegt und welche nur Rauschen beitraegt.

    python scripts/test_quality.py --timeframes 1d 4h 1h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from ew import pivots  # noqa: E402
from ew.backtest.engine import Costs, ExitPolicy, run  # noqa: E402
from ew.data import store  # noqa: E402
from ew.forecast.signals import scan  # noqa: E402
from ew.scoring.guidelines import GUIDELINE_NAMES  # noqa: E402


def collect(timeframes, context_scales, trigger_offset, policy, costs, holdout=False):
    from ew.data.universe import HOLDOUT

    trades = []
    for tf in timeframes:
        ds = store.usable(min_bars=800, timeframes=(tf,), exclude_holdout=not holdout)
        if holdout:
            ds = [d for d in ds if d[1] in HOLDOUT]
        for src, sym, t in ds:
            df = store.load(src, sym, t)
            lat = pivots.build(df)
            sigs = scan(lat, df, context_scales=context_scales,
                        trigger_offset=trigger_offset)
            trades += run(df, sigs, costs=costs, policy=policy,
                          symbol=sym, timeframe=t)
    return trades


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d", "4h"])
    ap.add_argument("--context", nargs="*", type=int, default=[4, 5, 6])
    ap.add_argument("--trigger-offset", type=int, default=2)
    ap.add_argument("--holdout", action="store_true")
    args = ap.parse_args()

    policy = ExitPolicy(target_r=3.0, breakeven_at_r=1.0)
    costs = Costs()
    trades = collect(args.timeframes, tuple(args.context), args.trigger_offset,
                     policy, costs, holdout=args.holdout)

    if not trades:
        print("Keine Trades.")
        return 1

    df = pd.DataFrame([{
        "r": t.r_multiple, "quality": t.quality, "tf": t.timeframe,
        "symbol": t.symbol, "dir": t.direction, "ctx": t.context_scale,
        **t.guideline_hits,
    } for t in trades])

    print(f"Timeframes {args.timeframes}  Kontext {args.context}  "
          f"Trigger-Offset {args.trigger_offset}")
    print(f"{'Universum':<12}{'Holdout' if args.holdout else 'Training'}")
    print(f"Trades: {len(df):,}\n")

    # --- Erwartung je Qualitaetsstufe -------------------------------------
    print("=== Erwartung nach Zahl erfuellter Richtlinien ===")
    print(f"{'Score':<7}{'n':>7}{'Erwart.':>10}{'Treffer':>9}"
          f"{'ØGew':>8}{'ØVerl':>8}{'Summe R':>10}")
    print("-" * 59)
    grp = df.groupby("quality")["r"]
    for q, s in grp:
        if len(s) < 10:
            continue
        w, l = s[s > 0], s[s <= 0]
        print(f"{q:<7}{len(s):>7}{s.mean():>+10.3f}{(s > 0).mean():>9.1%}"
              f"{(w.mean() if len(w) else 0):>+8.2f}"
              f"{(l.mean() if len(l) else 0):>+8.2f}{s.sum():>+10.1f}")

    # --- Der eigentliche Test ---------------------------------------------
    rho, p_rho = stats.spearmanr(df["quality"], df["r"])
    print(f"\nSpearman-Rangkorrelation Score vs. Ergebnis: "
          f"rho = {rho:+.4f}   p = {p_rho:.4f}")
    if p_rho < 0.05 and rho > 0:
        print("  -> Monotoner Zusammenhang vorhanden: die Qualitaet traegt.")
    else:
        print("  -> Kein gesicherter monotoner Zusammenhang.")

    # --- Einzelne Richtlinien ---------------------------------------------
    print("\n=== Beitrag der einzelnen Richtlinien ===")
    print(f"{'Richtlinie':<24}{'Anteil':>8}{'E[R|ja]':>10}{'E[R|nein]':>11}"
          f"{'Diff':>8}{'t':>7}")
    print("-" * 68)
    rows = []
    for name in GUIDELINE_NAMES:
        if name not in df.columns:
            continue
        yes = df.loc[df[name] == True, "r"].to_numpy()   # noqa: E712
        no = df.loc[df[name] == False, "r"].to_numpy()   # noqa: E712
        if len(yes) < 20 or len(no) < 20:
            continue
        d = yes.mean() - no.mean()
        se = np.sqrt(yes.var(ddof=1) / len(yes) + no.var(ddof=1) / len(no))
        t = d / se if se > 0 else np.nan
        rows.append((name, len(yes) / len(df), yes.mean(), no.mean(), d, t))
    for name, share, ey, en, d, t in sorted(rows, key=lambda x: -abs(x[5])):
        print(f"{name:<24}{share:>8.1%}{ey:>+10.3f}{en:>+11.3f}{d:>+8.3f}{t:>7.2f}")

    print(f"\n  Bonferroni-Schwelle bei {len(rows)} Tests: |t| > "
          f"{stats.norm.ppf(1 - 0.025 / max(len(rows), 1)):.2f}")

    # --- Nach Timeframe ----------------------------------------------------
    if len(args.timeframes) > 1:
        print("\n=== Nach Timeframe ===")
        print(f"{'TF':<6}{'n':>7}{'Erwart.':>10}{'rho':>9}{'p':>9}")
        print("-" * 41)
        for tf, s in df.groupby("tf"):
            r_, p_ = stats.spearmanr(s["quality"], s["r"])
            print(f"{tf:<6}{len(s):>7}{s['r'].mean():>+10.3f}{r_:>+9.4f}{p_:>9.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
