"""Integritaetspruefung fuer OHLCV-Daten.

Stille Datenfehler sind fuer ein Handelssystem gefaehrlicher als laute:
ein nicht adjustierter Split sieht aus wie eine perfekte Impulswelle, eine
Datenluecke verschiebt jede Pivot-Distanz. Diese Checks laufen deshalb
verpflichtend nach jedem Fetch, und ihr Ergebnis wandert ins Manifest.

Schweregrade:
  ERROR  - Daten sind unbrauchbar, Verwendung wird blockiert
  WARN   - auffaellig, aber erklaerbar (Feiertage, Boersenpausen, echte Crashs)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .schema import OHLCV_COLUMNS, expected_bar_seconds


@dataclass
class Issue:
    severity: str  # "ERROR" | "WARN"
    code: str
    message: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        ex = f" z.B. {', '.join(self.examples[:3])}" if self.examples else ""
        return f"[{self.severity}] {self.code}: {self.message} (n={self.count}){ex}"


@dataclass
class Report:
    symbol: str
    timeframe: str
    n_bars: int
    start: str
    end: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "ERROR" for i in self.issues)

    def summary(self) -> str:
        head = (
            f"{self.symbol} {self.timeframe}: {self.n_bars} Bars "
            f"{self.start} .. {self.end} -> {'OK' if self.ok else 'FEHLER'}"
        )
        return "\n".join([head] + [f"    {i}" for i in self.issues])


def check(df: pd.DataFrame, symbol: str, timeframe: str) -> Report:
    """Prueft einen normalisierten OHLCV-Frame."""
    rep = Report(
        symbol=symbol,
        timeframe=timeframe,
        n_bars=len(df),
        start=str(df.index[0]) if len(df) else "-",
        end=str(df.index[-1]) if len(df) else "-",
    )
    if df.empty:
        rep.issues.append(Issue("ERROR", "EMPTY", "Keine Daten"))
        return rep

    _check_index(df, rep)
    _check_ohlc_consistency(df, rep)
    _check_prices(df, rep)
    _check_gaps(df, timeframe, rep)
    _check_splits(df, rep)
    return rep


def _check_index(df: pd.DataFrame, rep: Report) -> None:
    if not df.index.is_monotonic_increasing:
        rep.issues.append(Issue("ERROR", "INDEX_UNSORTED", "Index nicht monoton", 1))
    dupes = int(df.index.duplicated().sum())
    if dupes:
        rep.issues.append(Issue("ERROR", "INDEX_DUPES", "Doppelte Zeitstempel", dupes))
    if df.index.tz is None:
        rep.issues.append(Issue("ERROR", "INDEX_NAIVE", "Index ohne Zeitzone", 1))


def _check_ohlc_consistency(df: pd.DataFrame, rep: Report) -> None:
    hi_ok = df["high"] >= df[["open", "close", "low"]].max(axis=1) - 1e-9
    lo_ok = df["low"] <= df[["open", "close", "high"]].min(axis=1) + 1e-9
    bad = ~(hi_ok & lo_ok)
    n = int(bad.sum())
    if n:
        rep.issues.append(
            Issue(
                "ERROR",
                "OHLC_INCONSISTENT",
                "high/low umschliessen open/close nicht",
                n,
                [str(t.date()) for t in df.index[bad][:3]],
            )
        )


def _check_prices(df: pd.DataFrame, rep: Report) -> None:
    nonpos = (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    n = int(nonpos.sum())
    if n:
        rep.issues.append(
            Issue("ERROR", "NONPOSITIVE_PRICE", "Preis <= 0", n,
                  [str(t.date()) for t in df.index[nonpos][:3]])
        )
    nan = df[OHLCV_COLUMNS].isna().any(axis=1)
    n = int(nan.sum())
    if n:
        rep.issues.append(Issue("ERROR", "NAN", "NaN in OHLCV", n))

    # Flatlines: viele identische Closes hintereinander deuten auf
    # forward-gefuellte Luecken hin - fuer Pivot-Erkennung toedlich.
    same = (df["close"].diff() == 0) & (df["high"] == df["low"])
    runs = same.ne(same.shift()).cumsum()[same]
    if len(runs):
        longest = int(runs.value_counts().max())
        if longest >= 5:
            rep.issues.append(
                Issue("WARN", "FLATLINE", f"Laengste Flatline {longest} Bars", longest)
            )


def _check_gaps(df: pd.DataFrame, timeframe: str, rep: Report) -> None:
    """Findet fehlende Bars relativ zum erwarteten Bar-Abstand.

    Bei Aktien/Futures sind Wochenenden und Feiertage normal, deshalb nur WARN
    und Bewertung ueber den Median statt ueber Einzelluecken.
    """
    step = expected_bar_seconds(timeframe)
    delta = df.index.to_series().diff().dt.total_seconds().dropna()
    if delta.empty:
        return

    gaps = delta[delta > step * 1.5]
    if len(gaps):
        worst = gaps.nlargest(3)
        rep.issues.append(
            Issue(
                "WARN",
                "GAPS",
                f"{len(gaps)} Luecken > 1.5x Bar-Abstand, groesste {worst.max()/86400:.1f} Tage",
                len(gaps),
                [str(t.date()) for t in worst.index],
            )
        )

    # Kleinere Abstaende als erwartet weisen auf ein Timeframe-Mismatch hin.
    too_small = delta[delta < step * 0.5]
    if len(too_small):
        rep.issues.append(
            Issue("ERROR", "SUBSTEP", f"Bar-Abstand kleiner als {timeframe}", len(too_small))
        )


def _check_splits(df: pd.DataFrame, rep: Report) -> None:
    """Erkennt Kurssprünge, die auf nicht adjustierte Splits hindeuten.

    Ein Overnight-Return nahe einem einfachen Verhaeltnis (1/2, 1/3, 2/3, 1/4,
    1/5, 1/10 und Kehrwerte) ist verdaechtig. Echte Crashs treffen diese
    Verhaeltnisse in aller Regel nicht so genau.
    """
    ret = (df["open"] / df["close"].shift()).dropna()
    if ret.empty:
        return

    ratios = np.array([2, 3, 4, 5, 10, 20, 3 / 2, 5 / 4])
    candidates = np.concatenate([ratios, 1 / ratios])

    suspects: list[pd.Timestamp] = []
    for ts, r in ret.items():
        if 0.9 < r < 1.1:
            continue
        if np.any(np.abs(r - candidates) / candidates < 0.02):
            suspects.append(ts)

    if suspects:
        rep.issues.append(
            Issue(
                "WARN",
                "POSSIBLE_SPLIT",
                "Overnight-Sprung nahe einfachem Split-Verhaeltnis",
                len(suspects),
                [str(t.date()) for t in suspects[:3]],
            )
        )

    extreme = ret[(ret > 2.0) | (ret < 0.5)]
    if len(extreme):
        rep.issues.append(
            Issue(
                "WARN",
                "EXTREME_JUMP",
                "Overnight-Sprung > 100% bzw. < -50%",
                len(extreme),
                [str(t.date()) for t in extreme.index[:3]],
            )
        )
