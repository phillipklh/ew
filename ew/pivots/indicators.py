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


def _linreg_slope_value(s: pd.Series, n: int) -> pd.Series:
    """Wert der linearen Regression am aktuellen Punkt (Pine: linreg(x, n, 0)).

    Geschlossene Form statt Schleife: fuer eine feste Fensterlaenge sind die
    Regressionsgewichte konstant, sodass sich der Endpunktwert als gleitende
    Kombination aus Mittelwert und Steigung ergeben laesst.
    """
    idx = np.arange(n, dtype="float64")
    x_mean = idx.mean()
    denom = ((idx - x_mean) ** 2).sum()

    y_mean = s.rolling(n).mean()
    # Kovarianz von x und y im Fenster.
    cov = s.rolling(n).apply(
        lambda w: float(((idx - x_mean) * (w - w.mean())).sum()), raw=True
    )
    slope = cov / denom
    intercept = y_mean - slope * x_mean
    return intercept + slope * (n - 1)


def squeeze(
    df: pd.DataFrame,
    bb_len: int = 20,
    bb_mult: float = 2.0,
    kc_len: int = 20,
    kc_mult: float = 1.5,
    use_true_range: bool = True,
) -> pd.DataFrame:
    """Squeeze Momentum nach LazyBear.

    Der Squeeze ist aktiv, wenn die Bollinger-Baender vollstaendig innerhalb
    der Keltner-Kanaele liegen - ein Zustand zusammengedrueckter Volatilitaet,
    der typischerweise einer Expansion vorausgeht. Das passt strukturell zum
    Ende einer Korrektur, wo sich Volatilitaet vor dem Impuls zusammenzieht.

    Rueckgabe:
      on        Squeeze aktiv (BB innerhalb KC)
      off       Squeeze geloest
      momentum  Linearregressionswert der Abweichung vom Mittelwert

    Implementiert nach der veroeffentlichten Formel; die Momentum-Reihe ist
    `linreg(close - avg(avg(highest, lowest), sma(close)), kc_len, 0)`.
    """
    close = df["close"]
    basis = close.rolling(bb_len).mean()
    dev = bb_mult * close.rolling(bb_len).std(ddof=0)
    bb_upper, bb_lower = basis + dev, basis - dev

    ma = close.rolling(kc_len).mean()
    rng = true_range(df) if use_true_range else (df["high"] - df["low"])
    range_ma = rng.rolling(kc_len).mean()
    kc_upper, kc_lower = ma + range_ma * kc_mult, ma - range_ma * kc_mult

    on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    off = (bb_lower < kc_lower) & (bb_upper > kc_upper)

    highest = df["high"].rolling(kc_len).max()
    lowest = df["low"].rolling(kc_len).min()
    mid = ((highest + lowest) / 2.0 + close.rolling(kc_len).mean()) / 2.0
    mom = _linreg_slope_value(close - mid, kc_len)

    return pd.DataFrame(
        {"on": on.fillna(False), "off": off.fillna(False), "momentum": mom},
        index=df.index,
    )
