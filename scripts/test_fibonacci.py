#!/usr/bin/env python3
"""Testet, ob Fibonacci-Verhaeltnisse in Elliott-Wellen real sind.

Die Frage entscheidet, ob eine Fibonacci-basierte Bewertungsfunktion
ueberhaupt gebaut werden darf. Verglichen werden drei Groessen:

  beobachtet  - Trefferquote auf echten Kursdaten
  surrogat    - dieselbe Pipeline auf Block-Bootstrap-Serien ohne
                Wellenstruktur, aber gleicher Renditestatistik
  abdeckung   - Anteil des Wertebereichs, den die Toleranzbaender ueberdecken
                (die Trefferquote bei Gleichverteilung)

Nur wenn beobachtet deutlich ueber beiden liegt, ist das Signal verwertbar.

    python scripts/test_fibonacci.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ew import pivots  # noqa: E402
from ew.data import store  # noqa: E402
from ew.labeling import enumerate_complete  # noqa: E402
from ew.rules import Config  # noqa: E402
from ew.scoring import ratios as R  # noqa: E402
from ew.scoring.surrogate import block_bootstrap  # noqa: E402

SCALES = (3, 4, 5)
TOL = 0.05
N_SURROGATES = 3

# Welche Kennzahl gegen welche Levelfamilie geprueft wird.
TESTS = {
    "w2_retrace_w1": R.FIB_RETRACE,
    "w4_retrace_w3": R.FIB_RETRACE,
    "w3_ext_w1": R.FIB_EXTEND,
    "w5_ext_w1": R.FIB_EXTEND,
    "w5_ext_w3": R.FIB_EXTEND,
    "b_retrace_a": R.FIB_RETRACE,
    "c_ext_a": R.FIB_EXTEND,
}


def ratios_for(df: pd.DataFrame, cfg: Config, symbol="", tf="") -> pd.DataFrame:
    lat = pivots.build(df)
    frames = []
    for s in SCALES:
        labs = enumerate_complete(lat, s, cfg)
        if labs:
            frames.append(R.extract(labs, symbol=symbol, timeframe=tf))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> int:
    cfg = Config.leveraged()
    # Nur integritaetsgeprüfte Datensaetze - siehe store.usable().
    datasets = store.usable(min_bars=1500, timeframes=("4h", "1d"),
                            exclude_holdout=True)
    if not datasets:
        print("Keine passenden Datensaetze.")
        return 1

    print(f"Datensaetze: {len(datasets)}  Ebenen: {SCALES}  Toleranz: +/-{TOL:.0%}\n")

    obs_frames, sur_frames = [], []
    for src, sym, tf in datasets:
        df = store.load(src, sym, tf)
        obs_frames.append(ratios_for(df, cfg, sym, tf))
        for k in range(N_SURROGATES):
            sur = block_bootstrap(df, block=50, seed=1000 * k + len(sym))
            sur_frames.append(ratios_for(sur, cfg, sym, tf))
        print(f"  {sym} {tf}: fertig")

    obs = pd.concat(obs_frames, ignore_index=True)
    sur = pd.concat(sur_frames, ignore_index=True)

    print(f"\nLabelings: beobachtet {len(obs):,}  surrogat {len(sur):,}\n")
    print(f"{'Kennzahl':<16}{'n':>8}{'beob.':>9}{'surrog.':>9}"
          f"{'abdeck.':>9}{'Lift':>8}{'z':>8}")
    print("-" * 68)

    rows = []
    for col, levels in TESTS.items():
        if col not in obs.columns:
            continue
        o = obs[col].to_numpy("float64")
        s = sur[col].to_numpy("float64")
        o = o[np.isfinite(o)]
        s = s[np.isfinite(s)]
        if len(o) < 50 or len(s) < 50:
            continue

        # Wertebereich fuer die Abdeckung: robust auf das mittlere 98 % begrenzen,
        # damit einzelne Ausreisser den Nenner nicht dominieren.
        lo, hi = np.percentile(np.concatenate([o, s]), [1, 99])
        o_in = o[(o >= lo) & (o <= hi)]
        s_in = s[(s >= lo) & (s <= hi)]

        p_obs = R.near_fib(o_in, levels, TOL).mean()
        p_sur = R.near_fib(s_in, levels, TOL).mean()
        cov = R.coverage(levels, TOL, lo, hi)

        # Zweiseitiger Test auf Anteilsunterschied beobachtet vs. surrogat.
        p_pool = (p_obs * len(o_in) + p_sur * len(s_in)) / (len(o_in) + len(s_in))
        se = np.sqrt(p_pool * (1 - p_pool) * (1 / len(o_in) + 1 / len(s_in)))
        z = (p_obs - p_sur) / se if se > 0 else np.nan
        lift = p_obs / p_sur if p_sur > 0 else np.nan

        rows.append((col, len(o_in), p_obs, p_sur, cov, lift, z))
        print(f"{col:<16}{len(o_in):>8,}{p_obs:>8.1%}{p_sur:>9.1%}"
              f"{cov:>9.1%}{lift:>8.2f}{z:>8.1f}")

    print("\nLesart:")
    print("  Lift ~ 1.0  -> kein Unterschied zum strukturlosen Surrogat")
    print("  |z| < 2     -> Unterschied statistisch nicht gesichert")
    print("  beob. ~ abdeckung -> Treffer nur so haeufig wie durch die")
    print("                       Bandbreite der Toleranz ohnehin zu erwarten")

    if rows:
        lifts = [r[5] for r in rows if np.isfinite(r[5])]
        print(f"\nMedian-Lift ueber alle Kennzahlen: {np.median(lifts):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
