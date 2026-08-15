#!/usr/bin/env python3
"""Placebo-Kontrolle fuer das antizipative Zonen-System.

Dieselbe Logik wie in `test_edge.py`, angepasst an Limit-Orders: zu jedem
echten Setup werden Kontroll-Setups erzeugt, die dieselbe Geometrie haben -
gleiche Richtung, gleicher relativer Abstand von Limit, Stop und Ziel,
gleiche Fill- und Ausstiegsregeln - aber an einem zufaellig gewaehlten
Zeitpunkt platziert werden.

Damit bleibt alles gleich ausser der Information darueber, *wo* die Zone
liegt. Schlaegt das echte System die Kontrolle nicht, stammt der Ertrag aus
Richtungsbias und Marktumfeld statt aus der Zonenprognose.

    python scripts/test_edge_zones.py --timeframes 1d 4h
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
from ew.forecast.zone_signals import ZoneSignal  # noqa: E402

N_PLACEBO = 10


def placebo_for(df, sig: ZoneSignal, rng, n_bars: int) -> ZoneSignal | None:
    """Kopiert die Geometrie eines Setups an eine zufaellige Stelle."""
    ref = float(df["close"].iloc[sig.bar])
    if ref <= 0:
        return None
    # Relative Geometrie beibehalten.
    rel_limit = sig.limit / ref
    rel_stop = sig.stop / ref
    rel_target = sig.target / ref

    bar = int(rng.integers(50, n_bars - 80))
    px = float(df["close"].iloc[bar])
    if px <= 0:
        return None

    p0, p1 = sig.wave1_start, sig.wave1_end
    return ZoneSignal(
        bar=bar, direction=sig.direction,
        limit=px * rel_limit, stop=px * rel_stop, target=px * rel_target,
        zone=sig.zone, conf=sig.conf, context_scale=sig.context_scale,
        wave1_start=p0, wave1_end=p1, extended=sig.extended,
        expiry_bar=bar + (sig.expiry_bar - sig.bar),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d"])
    ap.add_argument("--context", nargs="*", type=int, default=[4, 5, 6])
    ap.add_argument("--stop-from", default="extended")
    args = ap.parse_args()

    costs = Costs()
    rng = np.random.default_rng(7)
    real, plac = [], []

    for tf in args.timeframes:
        for src, sym, t in store.usable(min_bars=800, timeframes=(tf,),
                                        exclude_holdout=True):
            df = store.load(src, sym, t)
            lat = pivots.build(df)
            sigs = zone_signals.scan(lat, df, context_scales=tuple(args.context),
                                     stop_from=args.stop_from,
                                     with_indicators=False)
            tr, _ = run_limit(df, sigs, costs=costs, symbol=sym, timeframe=tf)
            real += tr

            for _ in range(N_PLACEBO):
                fake = [p for p in (placebo_for(df, s, rng, len(df)) for s in sigs)
                        if p is not None]
                # Die Geometrie darf sich ueberlappen; one_at_a_time aus, damit
                # die Stichprobe nicht durch Verdraengung verzerrt wird.
                tr2, _ = run_limit(df, fake, costs=costs, symbol=sym,
                                   timeframe=tf, one_at_a_time=False)
                plac += tr2

    r = np.array([t.r_multiple for t in real])
    p = np.array([t.r_multiple for t in plac])
    rd = np.array([t.direction for t in real])
    pd_ = np.array([t.direction for t in plac])

    print(f"Stop-Variante: {args.stop_from}   Timeframes: {args.timeframes}")
    print(f"echt n={len(r)}   placebo n={len(p)}\n")
    print(f"{'':<10}{'n':>7}{'Erwart.':>10}{'Treffer':>9}{'OGew':>8}{'OVerl':>8}")
    print("-" * 52)
    for name, x in (("echt", r), ("placebo", p)):
        w, l = x[x > 0], x[x <= 0]
        print(f"{name:<10}{len(x):>7}{x.mean():>+10.3f}{(x > 0).mean():>9.1%}"
              f"{(w.mean() if len(w) else 0):>+8.2f}"
              f"{(l.mean() if len(l) else 0):>+8.2f}")

    print(f"\n{'Richtung':<10}{'n_echt':>8}{'echt':>9}{'placebo':>9}"
          f"{'Differenz':>11}{'t':>7}")
    print("-" * 54)
    for d, name in ((1, "long"), (-1, "short")):
        rr, pp = r[rd == d], p[pd_ == d]
        if len(rr) < 20 or len(pp) < 20:
            continue
        diff = rr.mean() - pp.mean()
        se = np.sqrt(rr.var(ddof=1) / len(rr) + pp.var(ddof=1) / len(pp))
        print(f"{name:<10}{len(rr):>8}{rr.mean():>+9.3f}{pp.mean():>+9.3f}"
              f"{diff:>+11.3f}{diff / se if se > 0 else np.nan:>7.2f}")

    # Der rohe Gesamtvergleich taugt nur, wenn beide Gruppen denselben
    # Long/Short-Mix haben. Weichen die Fill-Quoten je Richtung ab,
    # verschiebt sich der Mix und der Unterschied entsteht allein daraus
    # (Simpson-Paradox). Deshalb zusaetzlich richtungsgewichtet.
    w_long = float((rd > 0).mean())
    print(f"\nLong-Anteil   echt {w_long:.1%}   placebo {(pd_ > 0).mean():.1%}")

    diff_raw = r.mean() - p.mean()
    se = np.sqrt(r.var(ddof=1) / len(r) + p.var(ddof=1) / len(p))
    print(f"Gesamt roh              {diff_raw:+.3f} R   "
          f"t = {diff_raw / se if se > 0 else np.nan:.2f}")

    if (pd_ > 0).any() and (pd_ < 0).any():
        p_adj = w_long * p[pd_ > 0].mean() + (1 - w_long) * p[pd_ < 0].mean()
        diff_adj = r.mean() - p_adj
        print(f"Gesamt richtungsgewichtet {diff_adj:+.3f} R   "
              f"t = {diff_adj / se if se > 0 else np.nan:.2f}")
        print(f"  (Placebo roh {p.mean():+.3f} R, gewichtet {p_adj:+.3f} R)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
