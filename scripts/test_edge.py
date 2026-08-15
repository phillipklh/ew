#!/usr/bin/env python3
"""Prueft, ob die Wellenlogik selbst einen Beitrag leistet.

Ein positiver Backtest belegt fuer sich genommen nichts. Auf einem Universum
aus Aktien im Saekularaufwaertstrend erzeugt jedes long-lastige System
Gewinne - unabhaengig davon, ob seine Signallogik traegt. Die Frage ist
deshalb nicht "ist das Ergebnis positiv?", sondern "ist es besser als eine
Kontrolle, die alles Uebrige gleich haelt und nur den Zeitpunkt zerstoert?"

Kontrollgruppe: zu jedem echten Signal ein Placebo-Trade auf demselben
Instrument, in derselben Richtung, mit demselben relativen Stop-Abstand und
derselben Ausstiegsregel - aber zu einem zufaellig gewaehlten Zeitpunkt.
Damit bleiben Richtungsbias, Trendumfeld, Volatilitaet und Kostenmodell
identisch; verworfen wird ausschliesslich die Information ueber den
Einstiegszeitpunkt.

Schlaegt das echte System die Kontrolle nicht, stammt der Ertrag aus dem
Richtungsbias und nicht aus der Elliott-Struktur.

    python scripts/test_edge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ew import pivots  # noqa: E402
from ew.backtest.engine import Costs, ExitPolicy, Trade, _exit_price_and_reason, run  # noqa: E402
from ew.data import store  # noqa: E402
from ew.forecast.signals import Signal, scan  # noqa: E402

N_PLACEBO = 20


def placebo_trades(df, sigs, policy, costs, symbol, rng):
    """Erzeugt Placebo-Trades mit zerstoertem Zeitpunkt."""
    out = []
    n = len(df)
    opens = df["open"].to_numpy("float64")
    for sig in sigs:
        entry_ref = sig.bar + 1
        if entry_ref >= n:
            continue
        ref_entry = float(opens[entry_ref])
        if ref_entry <= 0:
            continue
        # Relativer Stop-Abstand des echten Signals beibehalten.
        rel_risk = abs(ref_entry - sig.stop) / ref_entry
        if not np.isfinite(rel_risk) or rel_risk <= 0:
            continue

        bar = int(rng.integers(20, n - 2))
        entry = float(opens[bar + 1])
        if entry <= 0:
            continue
        stop = entry - sig.direction * rel_risk * entry

        fake = Signal(
            bar=bar, direction=sig.direction, stop=stop,
            context_scale=sig.context_scale, trigger_scale=sig.trigger_scale,
            wave1_start=sig.wave1_start, wave1_end=sig.wave1_end,
            trigger_pivot=sig.trigger_pivot, retrace=sig.retrace,
        )
        exit_bar, exit_px, reason = _exit_price_and_reason(
            df, fake, entry, stop, policy
        )
        risk = abs(entry - stop)
        gross = (exit_px - entry) * sig.direction
        cost = (entry + exit_px) * costs.per_side
        out.append(((gross - cost) / risk, sig.direction))
    return out


def main() -> int:
    policy = ExitPolicy(target_r=3.0, breakeven_at_r=1.0)
    costs = Costs()
    rng = np.random.default_rng(42)

    datasets = store.usable(min_bars=800, timeframes=("1d",), exclude_holdout=True)
    real: list[Trade] = []
    plac: list[float] = []

    for src, sym, tf in datasets:
        df = store.load(src, sym, tf)
        lat = pivots.build(df)
        sigs = scan(lat, df, context_scales=(4, 5, 6))
        real += run(df, sigs, costs=costs, policy=policy, symbol=sym)
        for _ in range(N_PLACEBO):
            plac += placebo_trades(df, sigs, policy, costs, sym, rng)

    r = np.array([t.r_multiple for t in real])
    p = np.array([x[0] for x in plac])
    p_dir = np.array([x[1] for x in plac])

    print(f"Echte Signale : n={len(r):>6}")
    print(f"Placebo       : n={len(p):>6}  ({N_PLACEBO} Ziehungen je Signal)\n")

    def line(name, x):
        return (f"{name:<14}{x.mean():>+9.3f}{np.median(x):>+9.2f}"
                f"{(x > 0).mean():>9.1%}{x[x > 0].mean():>+9.2f}"
                f"{x[x <= 0].mean():>+9.2f}")

    print(f"{'':<14}{'Erwart.':>9}{'Median':>9}{'Treffer':>9}{'ØGewinn':>9}{'ØVerlust':>9}")
    print("-" * 59)
    print(line("echt", r))
    print(line("placebo", p))

    diff = r.mean() - p.mean()
    se = np.sqrt(r.var(ddof=1) / len(r) + p.var(ddof=1) / len(p))
    t_stat = diff / se if se > 0 else np.nan
    print(f"\nDifferenz der Erwartungswerte: {diff:+.3f} R   t = {t_stat:.2f}")

    # Getrennt nach Richtung, und zwar richtungsgleich verglichen: nur so
    # kuerzt sich der Richtungsbias heraus. Ein Long-Trade darf ausschliesslich
    # gegen Long-Placebos gemessen werden, sonst misst der Test den
    # Trendbias des Universums statt der Signalguete.
    print(f"\n{'Richtung':<10}{'n_echt':>8}{'echt':>9}{'placebo':>9}"
          f"{'Differenz':>11}{'t':>7}")
    print("-" * 54)
    for d, name in ((1, "long"), (-1, "short")):
        rr = np.array([t.r_multiple for t in real if t.direction == d])
        pp = p[p_dir == d]
        if len(rr) < 20 or len(pp) < 20:
            continue
        dd = rr.mean() - pp.mean()
        s = np.sqrt(rr.var(ddof=1) / len(rr) + pp.var(ddof=1) / len(pp))
        print(f"{name:<10}{len(rr):>8}{rr.mean():>+9.3f}{pp.mean():>+9.3f}"
              f"{dd:>+11.3f}{dd / s if s > 0 else np.nan:>7.2f}")

    print("\nLesart: liegt die Differenz nahe null, stammt der Ertrag aus dem")
    print("Richtungsbias und dem Marktumfeld - nicht aus der Wellenlogik.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
