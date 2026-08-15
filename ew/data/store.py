"""Parquet-Store mit Manifest.

Die Daten selbst liegen ausserhalb des Repos (siehe .gitignore). Damit ein
Backtest-Ergebnis trotzdem reproduzierbar bleibt, schreibt der Store zu jedem
Datensatz einen Manifest-Eintrag mit Inhalts-Hash, Zeitraum und Bar-Anzahl.
Wer die Zahlen nachrechnen will, zieht die Daten neu und vergleicht den Hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .schema import normalize

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data"


def _path(root: Path, source: str, symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("/", "_").replace("^", "idx_").replace("=", "_")
    return root / "ohlcv" / source / safe / f"{timeframe}.parquet"


def content_hash(df: pd.DataFrame) -> str:
    """Stabiler Hash ueber Index und OHLCV-Werte."""
    h = hashlib.sha256()
    h.update(df.index.asi8.tobytes())
    for col in ["open", "high", "low", "close", "volume"]:
        h.update(df[col].to_numpy("float64").tobytes())
    return h.hexdigest()[:16]


def save(
    df: pd.DataFrame,
    source: str,
    symbol: str,
    timeframe: str,
    *,
    root: Path = DEFAULT_ROOT,
    meta: dict | None = None,
) -> Path:
    p = _path(root, source, symbol, timeframe)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, engine="pyarrow", compression="zstd")

    entry = {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "path": str(p.relative_to(root)),
        "n_bars": int(len(df)),
        "start": str(df.index[0]) if len(df) else None,
        "end": str(df.index[-1]) if len(df) else None,
        "sha256_16": content_hash(df) if len(df) else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if meta:
        entry.update(meta)
    _update_manifest(root, entry)
    return p


def load(
    source: str, symbol: str, timeframe: str, *, root: Path = DEFAULT_ROOT
) -> pd.DataFrame:
    p = _path(root, source, symbol, timeframe)
    if not p.exists():
        raise FileNotFoundError(
            f"Kein Datensatz {source}/{symbol}/{timeframe}. "
            f"Erst 'python scripts/fetch_data.py' ausfuehren."
        )
    return normalize(pd.read_parquet(p, engine="pyarrow"))


def manifest_path(root: Path = DEFAULT_ROOT) -> Path:
    return root / "manifest.json"


def read_manifest(root: Path = DEFAULT_ROOT) -> dict:
    p = manifest_path(root)
    if not p.exists():
        return {"datasets": {}}
    return json.loads(p.read_text())


def _update_manifest(root: Path, entry: dict) -> None:
    man = read_manifest(root)
    key = f"{entry['source']}/{entry['symbol']}/{entry['timeframe']}"
    man.setdefault("datasets", {})[key] = entry
    man["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest_path(root).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(root).write_text(json.dumps(man, indent=2, sort_keys=True))


def available(root: Path = DEFAULT_ROOT) -> pd.DataFrame:
    """Uebersicht ueber alle gespeicherten Datensaetze."""
    man = read_manifest(root)
    rows = list(man.get("datasets", {}).values())
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["source", "symbol", "timeframe"])
