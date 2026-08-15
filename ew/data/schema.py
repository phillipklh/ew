"""Kanonisches OHLCV-Schema.

Jede Datenquelle wird auf exakt diese Form normalisiert. Alles, was danach
kommt (Pivots, Regeln, Backtest), darf voraussetzen:

  - Index `ts`: UTC-tz-aware DatetimeIndex, streng monoton steigend, eindeutig
  - Spalten: open, high, low, close, volume (float64)
  - Keine NaN in OHLC
  - OHLC-Konsistenz: low <= min(open, close) <= max(open, close) <= high

Der Zeitstempel bezeichnet immer den **Open** der Bar (Konvention Binance).
Das ist wichtig fuer Kausalitaet: eine Bar mit ts=T ist erst zum Zeitpunkt
T + timeframe abgeschlossen und darf vorher nicht verwendet werden.
"""

from __future__ import annotations

import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
INDEX_NAME = "ts"

# Kanonische Timeframes -> pandas-Offset und Dauer in Sekunden.
TIMEFRAMES: dict[str, int] = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def normalize(df: pd.DataFrame, *, tz_source: str | None = None) -> pd.DataFrame:
    """Bringt einen rohen OHLCV-DataFrame in die kanonische Form.

    Idempotent: ein bereits normalisierter Frame bleibt unveraendert.
    """
    out = df.copy()

    # Spaltennamen vereinheitlichen (yfinance liefert 'Open', 'High', ...).
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    if "adj_close" in out.columns and "close" not in out.columns:
        out = out.rename(columns={"adj_close": "close"})

    missing = [c for c in OHLCV_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"Fehlende Spalten nach Normalisierung: {missing}")
    out = out[OHLCV_COLUMNS]

    # Index auf UTC-tz-aware DatetimeIndex bringen.
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is None:
        idx = idx.tz_localize(tz_source or "UTC")
    out.index = idx.tz_convert("UTC")
    out.index.name = INDEX_NAME

    out = out.astype("float64")

    # Duplikate: letzten Eintrag gewinnen lassen (spaetere Korrektur der Quelle).
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()

    # Bars ohne gueltigen Preis sind unbrauchbar und werden verworfen.
    out = out.dropna(subset=["open", "high", "low", "close"])
    out["volume"] = out["volume"].fillna(0.0)

    return out


def expected_bar_seconds(timeframe: str) -> int:
    try:
        return TIMEFRAMES[timeframe]
    except KeyError:
        raise ValueError(
            f"Unbekannter Timeframe {timeframe!r}, erlaubt: {sorted(TIMEFRAMES)}"
        ) from None
