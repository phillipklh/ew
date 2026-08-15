#!/usr/bin/env python3
"""Laedt das Handelsuniversum und schreibt es in den Parquet-Store.

    python scripts/fetch_data.py                  # alles
    python scripts/fetch_data.py --source binance # nur Krypto
    python scripts/fetch_data.py --symbols BTCUSDT ETHUSDT --timeframes 1d

Datensaetze mit ERROR-Befund werden gespeichert, aber im Report deutlich
markiert - stille Fehler sind das Problem, nicht laute.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ew.data import integrity, sources, store  # noqa: E402
from ew.data.universe import UNIVERSE, TIMEFRAMES, Instrument  # noqa: E402


def fetch_one(inst: Instrument, timeframe: str):
    """Holt einen Datensatz; leitet 4h fuer yfinance aus 1h ab."""
    if inst.source == "binance":
        return sources.fetch_binance(inst.symbol, timeframe)

    if timeframe == "4h":
        base = sources.fetch_yfinance(inst.symbol, "1h")
        return sources.resample(base, "4h")
    return sources.fetch_yfinance(inst.symbol, timeframe)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["binance", "yfinance"])
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--timeframes", nargs="*", default=TIMEFRAMES)
    args = ap.parse_args()

    targets = UNIVERSE
    if args.source:
        targets = [i for i in targets if i.source == args.source]
    if args.symbols:
        targets = [i for i in targets if i.symbol in set(args.symbols)]

    reports: list[integrity.Report] = []
    failures: list[str] = []

    for inst in targets:
        for tf in args.timeframes:
            tag = f"{inst.symbol} {tf}"
            try:
                df = fetch_one(inst, tf)
                if df.empty:
                    failures.append(f"{tag}: leer")
                    print(f"  LEER      {tag}")
                    continue

                rep = integrity.check(df, inst.symbol, tf)
                reports.append(rep)
                store.save(
                    df, inst.source, inst.symbol, tf,
                    meta={"cluster": inst.cluster, "name": inst.name,
                          "integrity_ok": rep.ok},
                )
                flag = "OK  " if rep.ok else "FEHL"
                print(f"  {flag}      {tag:<16} {len(df):>7} Bars  "
                      f"{str(df.index[0])[:10]} .. {str(df.index[-1])[:10]}")
                for iss in rep.issues:
                    print(f"                {iss}")

            except Exception as e:
                failures.append(f"{tag}: {e}")
                print(f"  FEHLER    {tag}: {e}")
                traceback.print_exc(limit=1)

            if inst.source == "yfinance":
                time.sleep(20)  # Yahoo drosselt pro IP mit ~1 Minute Sperrzeit

    print("\n" + "=" * 70)
    n_err = sum(1 for r in reports if not r.ok)
    print(f"Datensaetze: {len(reports)}   mit ERROR: {n_err}   Fehlschlaege: {len(failures)}")
    for f in failures:
        print(f"  ! {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
