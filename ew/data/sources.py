"""Datenquellen: Binance (Krypto) und yfinance (Aktien, Indizes, Futures).

Getestet 2026-08:
  Binance   volle Historie ab 2017-08, echtes OHLCV, alle Timeframes
  yfinance  Gold ab 2000, AAPL ab 1980 - aber harte Intraday-Limits (s.u.)

Stooq wurde geprueft und verworfen: die Seite verlangt eine JS-Bot-Pruefung.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Iterator

import pandas as pd

from .schema import expected_bar_seconds, normalize

BINANCE_BASE = "https://api.binance.com/api/v3/klines"
BINANCE_LIMIT = 1000

# yfinance begrenzt Intraday-Historie serverseitig. Diese Grenzen sind hart -
# ein groesserer Zeitraum liefert stillschweigend weniger Daten, deshalb
# fragen wir gar nicht erst mehr an.
YF_MAX_PERIOD = {
    "15m": "60d",
    "1h": "730d",
    "1d": "max",
    "1w": "max",
}

_YF_INTERVAL = {"15m": "15m", "1h": "1h", "1d": "1d", "1w": "1wk"}
_BINANCE_INTERVAL = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"}


# --------------------------------------------------------------------------
# Binance
# --------------------------------------------------------------------------

def _get_json(url: str, *, retries: int = 5) -> list:
    """HTTP-GET mit exponentiellem Backoff fuer Rate-Limits (418/429)."""
    delay = 1.0
    last: Exception | None = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (418, 429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Binance-Abruf fehlgeschlagen: {last}")


def _binance_pages(symbol: str, interval: str, start_ms: int) -> Iterator[list]:
    """Blaettert die Klines-Pagination durch, bis keine neuen Bars mehr kommen."""
    cursor = start_ms
    while True:
        url = (
            f"{BINANCE_BASE}?symbol={symbol}&interval={interval}"
            f"&startTime={cursor}&limit={BINANCE_LIMIT}"
        )
        rows = _get_json(url)
        if not rows:
            return
        yield rows
        last_open = rows[-1][0]
        if last_open <= cursor and len(rows) < BINANCE_LIMIT:
            return
        cursor = last_open + 1
        if len(rows) < BINANCE_LIMIT:
            return
        time.sleep(0.12)  # unter dem Binance-Weight-Limit bleiben


def fetch_binance(symbol: str, timeframe: str, start: str | None = None) -> pd.DataFrame:
    """Laedt die vollstaendige Klines-Historie eines Binance-Symbols.

    Die letzte, noch laufende Bar wird verworfen - sie ist unvollstaendig und
    wuerde Lookahead in jede nachgelagerte Berechnung tragen.
    """
    interval = _BINANCE_INTERVAL.get(timeframe)
    if interval is None:
        raise ValueError(f"Binance kennt Timeframe {timeframe!r} nicht")

    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000) if start else 0

    frames: list[pd.DataFrame] = []
    for rows in _binance_pages(symbol, interval, start_ms):
        df = pd.DataFrame(
            rows,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades",
                "taker_base", "taker_quote", "ignore",
            ],
        )
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.pop("open_time"), unit="ms", utc=True)
        frames.append(df)

    if not frames:
        return normalize(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))

    out = normalize(pd.concat(frames))
    return _drop_incomplete_last_bar(out, timeframe)


# --------------------------------------------------------------------------
# yfinance
# --------------------------------------------------------------------------

def fetch_yfinance(
    symbol: str, timeframe: str, *, retries: int = 5, base_delay: float = 45.0
) -> pd.DataFrame:
    """Laedt Aktien-/Futures-Historie. Behandelt Yahoos Rate-Limiting.

    Yahoo drosselt pro IP mit einer Sperrzeit von rund einer Minute. Kurze
    Backoffs laufen deshalb ins Leere - die Wartezeit startet bewusst hoch.
    Das macht den Erstabruf langsam, aber zuverlaessig; danach liegen die
    Daten im Parquet-Store und werden nicht erneut geholt.
    """
    import yfinance as yf

    interval = _YF_INTERVAL.get(timeframe)
    if interval is None:
        raise ValueError(f"yfinance kennt Timeframe {timeframe!r} nicht (4h wird resampled)")
    period = YF_MAX_PERIOD[timeframe]

    delay = base_delay
    last: Exception | None = None
    for attempt in range(retries):
        try:
            raw = yf.Ticker(symbol).history(
                period=period, interval=interval, auto_adjust=True, raise_errors=True
            )
            if raw is not None and len(raw):
                out = normalize(raw)
                return _drop_incomplete_last_bar(out, timeframe)
            last = RuntimeError("leere Antwort")
        except Exception as e:  # yfinance wirft heterogene Fehlertypen
            last = e
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 1.6
    raise RuntimeError(f"yfinance-Abruf {symbol} {timeframe} fehlgeschlagen: {last}")


# --------------------------------------------------------------------------
# Ableitung
# --------------------------------------------------------------------------

def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregiert einen feineren Frame auf einen groeberen Timeframe.

    Nur fuer Quellen noetig, die einen Timeframe nicht nativ liefern (yfinance
    kennt kein 4h). Fuer die Pivot-Erkennung selbst wird ausdruecklich NICHT
    resampled - dort arbeitet das Lattice immer auf der feinsten Serie.
    """
    rule = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D", "1w": "1W"}[timeframe]
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return normalize(out.dropna(subset=["open", "high", "low", "close"]))


def _drop_incomplete_last_bar(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Entfernt die letzte Bar, falls ihre Periode noch laeuft."""
    if df.empty:
        return df
    step = expected_bar_seconds(timeframe)
    now = pd.Timestamp.utcnow()
    if (now - df.index[-1]).total_seconds() < step:
        return df.iloc[:-1]
    return df
