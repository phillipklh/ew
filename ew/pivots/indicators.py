"""Kausale Indikatoren.

Jede Funktion hier garantiert: der Wert an Position i haengt ausschliesslich
von Bars <= i ab. Das ist keine Stilfrage, sondern die Voraussetzung dafuer,
dass ein Backtest-Ergebnis etwas ueber die Zukunft aussagt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder-ATR, kausal.

    Die ersten n Werte werden mit dem expandierenden Mittel gefuellt, damit
    der Serienanfang nutzbar bleibt statt NaN zu sein.
    """
    tr = true_range(df)
    out = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=1).mean()
    return out.bfill()


def rsi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder-RSI auf Close-Basis, kausal."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False, min_periods=1).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0)


def macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})
