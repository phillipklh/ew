"""Tests fuer das Pivot-Lattice.

Der wichtigste Test dieser Datei ist `test_no_lookahead_truncation`. Er ist
die eigentliche Absicherung des gesamten Projekts: er beweist, dass die
Pivot-Erkennung auf einer bis Bar t abgeschnittenen Serie exakt dieselben
Pivots liefert wie auf der vollen Historie. Faellt dieser Test, ist jedes
Backtest-Ergebnis wertlos, egal wie gut es aussieht.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ew import pivots
from ew.pivots.lattice import build, verify_alternation, verify_causality, verify_nesting


def synth(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Synthetische OHLC-Serie: Random Walk mit aufgepraegten Schwingungen."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    trend = np.cumsum(rng.normal(0, 1, n))
    cycle = 12 * np.sin(t / 40.0) + 5 * np.sin(t / 9.0)
    close = 100 + trend + cycle
    close = np.maximum(close, 1.0)

    spread = np.abs(rng.normal(0, 0.6, n)) + 0.15
    high = close + spread
    low = np.maximum(close - spread, 0.5)
    open_ = np.concatenate([[close[0]], close[:-1]])
    open_ = np.clip(open_, low, high)

    idx = pd.date_range("2015-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.uniform(1, 100, n)},
        index=idx,
    ).rename_axis("ts")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return synth()


# --------------------------------------------------------------------------
# Invarianten
# --------------------------------------------------------------------------

def test_causality_invariant(df):
    assert verify_causality(build(df)) == []


def test_nesting_invariant(df):
    assert verify_nesting(build(df)) == []


def test_alternation_invariant(df):
    assert verify_alternation(build(df)) == []


def test_coarser_scales_have_fewer_pivots(df):
    lat = build(df)
    counts = [len(lat.pivots(s)) for s in range(lat.n_levels)]
    assert all(a >= b for a, b in zip(counts, counts[1:])), counts


def test_pivot_prices_match_bar_extremes(df):
    """Ein Hochpivot muss auf dem High seiner Bar liegen, ein Tief auf dem Low."""
    lat = build(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    for s in range(lat.n_levels):
        for p in lat.pivots(s):
            expected = high[p.idx] if p.kind > 0 else low[p.idx]
            assert p.price == pytest.approx(expected), (s, p)


# --------------------------------------------------------------------------
# Die zentrale Absicherung
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cut", [600, 900, 1200, 1500, 1800])
def test_no_lookahead_truncation(df, cut):
    """Abschneiden der Zukunft darf die bereits bestaetigten Pivots nicht aendern.

    Auf der vollen Serie werden alle Pivots betrachtet, die bis Bar `cut`
    bestaetigt sind. Genau diese muessen auch entstehen, wenn das Lattice nur
    die Bars bis `cut` ueberhaupt zu sehen bekommt - in Position, Preis, Typ
    und Bestaetigungszeitpunkt.
    """
    full = build(df)
    trunc = build(df.iloc[: cut + 1])

    for s in range(full.n_levels):
        a = [
            (p.idx, p.kind, round(p.price, 9), p.confirmed_idx)
            for p in full.visible_at(s, cut)
        ]
        b = [
            (p.idx, p.kind, round(p.price, 9), p.confirmed_idx)
            for p in trunc.visible_at(s, cut)
        ]
        assert a == b, f"Lookahead auf Ebene {s} bei cut={cut}"


def test_visible_at_never_leaks_future(df):
    lat = build(df)
    for s in range(lat.n_levels):
        for bar in (500, 1000, 1500):
            for p in lat.visible_at(s, bar):
                assert p.confirmed_idx <= bar
                assert p.idx <= bar


# --------------------------------------------------------------------------
# Verhalten des ZigZag
# --------------------------------------------------------------------------

def test_monotonic_series_has_no_real_reversal():
    """Eine streng steigende Serie enthaelt keinen echten Wendepunkt.

    Der Startpunkt wird als Anker markiert, nicht als Pivot - sonst wuerde der
    willkuerliche Anfang des Datenfensters zum Wellenursprung erklaert.
    """
    n = 300
    close = np.linspace(100, 300, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5,
         "close": close, "volume": 1.0},
        index=idx,
    ).rename_axis("ts")
    lat = build(df)

    real = [p for p in lat.pivots(0) if not p.is_anchor]
    assert real == [], f"Monotone Serie darf keinen echten Wendepunkt haben: {real}"
    assert all(p.is_anchor for p in lat.pivots(0))


def test_only_first_pivot_is_anchor(df):
    """Pro Ebene darf hoechstens der erste Pivot ein Anker sein."""
    lat = build(df)
    for s in range(lat.n_levels):
        ps = lat.pivots(s)
        assert all(not p.is_anchor for p in ps[1:]), f"Ebene {s}"


def test_warmup_skips_unstable_atr(df):
    """Vor Ablauf der ATR-Warmup-Phase darf kein Extremwert verankert werden."""
    lat = build(df)
    for s in range(lat.n_levels):
        for p in lat.pivots(s):
            assert p.idx >= 14, (s, p)


def test_higher_theta_needs_larger_move(df):
    """Groessere Schwelle darf nur Pivots entfernen, nie neue hinzufuegen."""
    lat = build(df)
    for s in range(1, lat.n_levels):
        coarse = {(p.idx, p.kind) for p in lat.pivots(s)}
        fine = {(p.idx, p.kind) for p in lat.pivots(s - 1)}
        assert coarse <= fine


def test_lag_is_non_negative(df):
    lat = build(df)
    for s in range(lat.n_levels):
        assert all(p.lag >= 0 for p in lat.pivots(s))


def test_empty_and_tiny_inputs():
    idx = pd.date_range("2020-01-01", periods=1, freq="D", tz="UTC")
    tiny = pd.DataFrame(
        {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [1.0]},
        index=idx,
    ).rename_axis("ts")
    lat = build(tiny)
    assert all(lat.pivots(s) == [] for s in range(lat.n_levels))
