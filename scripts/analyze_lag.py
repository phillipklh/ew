#!/usr/bin/env python3
"""Quantifiziert die Bestaetigungsverzoegerung je Lattice-Ebene.

Hintergrund: ein Pivot ist erst bekannt, wenn die Gegenbewegung den
Schwellwert gerissen hat. Die Frage, wie gross diese Verzoegerung im
Verhaeltnis zur Wellendauer ist, entscheidet darueber, ob eine Ebene
ueberhaupt handelbar ist - und faellt damit direkt in die Architektur.

    python scripts/analyze_lag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ew import pivots  # noqa: E402
from ew.data import store  # noqa: E402


def analyze(source: str, symbol: str, timeframe: str) -> pd.DataFrame:
    df = store.load(source, symbol, timeframe)
    lat = pivots.build(df)

    rows = []
    for s in range(lat.n_levels):
        ps = lat.pivots(s)
        if len(ps) < 3:
            continue
        lags = np.array([p.lag for p in ps], dtype=float)
        durations = np.diff(np.array([p.idx for p in ps], dtype=float))
        moves = np.abs(np.diff(np.array([p.price for p in ps], dtype=float)))
        starts = np.array([p.price for p in ps], dtype=float)[:-1]

        rows.append(
            {
                "symbol": symbol,
                "tf": timeframe,
                "scale": s,
                "theta": lat.thetas[s],
                "n": len(ps),
                "lag_med": np.median(lags),
                "dauer_med": np.median(durations),
                # Der entscheidende Quotient: Verzoegerung relativ zur
                # Wellendauer. Werte nahe/ueber 1 heissen, dass die
                # Bestaetigung erst eintrifft, wenn die Welle im Wesentlichen
                # vorbei ist.
                "lag/dauer": np.median(lags) / max(np.median(durations), 1e-9),
                "move_med_%": float(np.median(moves / starts) * 100),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    man = store.read_manifest()
    datasets = [
        (d["source"], d["symbol"], d["timeframe"])
        for d in man.get("datasets", {}).values()
        if d.get("n_bars", 0) > 500
    ]
    if not datasets:
        print("Keine Datensaetze. Erst scripts/fetch_data.py ausfuehren.")
        return 1

    out = pd.concat([analyze(*d) for d in datasets], ignore_index=True)
    pd.set_option("display.width", 160)

    print("=== Pro Datensatz ===")
    print(out.round(2).to_string(index=False))

    print("\n=== Aggregiert ueber alle Datensaetze ===")
    agg = out.groupby("scale").agg(
        theta=("theta", "first"),
        n_datasets=("n", "size"),
        lag_med=("lag_med", "median"),
        dauer_med=("dauer_med", "median"),
        lag_dauer=("lag/dauer", "median"),
        move_pct=("move_med_%", "median"),
    )
    print(agg.round(2).to_string())

    ratio = agg["lag_dauer"]
    print(
        f"\nQuotient lag/dauer ueber alle Ebenen: "
        f"min={ratio.min():.2f} max={ratio.max():.2f} median={ratio.median():.2f}"
    )
    print(
        "Ist der Quotient auf allen Ebenen aehnlich gross, ist die\n"
        "Verzoegerung skaleninvariant - dann laesst sich keine einzelne Ebene\n"
        "isoliert handeln und der Top-down-Ansatz ist zwingend."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
