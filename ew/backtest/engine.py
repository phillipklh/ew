"""Ereignisgetriebener, kausaler Backtest.

Grundsaetze, die hier nicht verhandelbar sind:

*Einstieg erst auf der Folgebar.* Ein Signal entsteht auf dem Close von Bar t
und wird auf dem Open von t+1 ausgefuehrt. Ein Einstieg auf dem Close, der
das Signal ausgeloest hat, waere Lookahead.

*Bei Mehrdeutigkeit innerhalb einer Bar gewinnt der Stop.* Werden Stop und
Ziel in derselben Bar beruehrt, wird der Stop angenommen. Die Reihenfolge
innerhalb einer Bar ist aus OHLC nicht rekonstruierbar; die optimistische
Annahme wuerde die Ergebnisse systematisch schoenen.

*Kosten sind Pflicht, nicht Option.* Gebuehren und Slippage werden auf beiden
Seiten abgezogen. Bei einem System mit engen Stops entscheidet das ueber
Erfolg und Misserfolg.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..forecast.signals import Signal


@dataclass(frozen=True)
class Costs:
    """Handelskosten in Basispunkten des Nominals, je Seite."""

    fee_bps: float = 5.0
    slippage_bps: float = 5.0

    @property
    def per_side(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 10_000.0


@dataclass(frozen=True)
class ExitPolicy:
    """Ausstiegsregeln.

    `breakeven_at_r` ist die wichtigste Stellschraube fuer das Ziel eines
    Drawdowns unter 5 %: die Drawdown-Rechnung verlangt einen mittleren
    Verlust von etwa 0,5R, was ohne Teilabsicherung nicht erreichbar ist.
    """

    target_r: float | None = 3.0     # Ziel als Vielfaches des Risikos
    breakeven_at_r: float | None = 1.0  # ab hier Stop auf Einstand
    max_bars: int | None = 200       # Zeitstop
    stop_buffer_r: float = 0.0       # Puffer hinter der Regel-Invalidierung


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    direction: int
    entry: float
    exit: float
    stop: float
    r_multiple: float
    reason: str
    context_scale: int
    trigger_scale: int
    symbol: str = ""
    #: Echte Zeitstempel. Zwingend fuer die Portfoliobewertung: Instrumente
    #: haben sehr unterschiedliche Historien (S&P 500 ab 1927, ADA ab 2018).
    #: Ohne Kalenderbezug wuerde eine Auswertung ueber Bar-Indizes die
    #: Trades pro Jahr um ein Vielfaches ueberschaetzen.
    entry_ts: pd.Timestamp | None = None
    exit_ts: pd.Timestamp | None = None

    @property
    def bars_held(self) -> int:
        return self.exit_bar - self.entry_bar


def _exit_price_and_reason(
    df: pd.DataFrame, sig: Signal, entry: float, stop: float, pol: ExitPolicy
) -> tuple[int, float, str]:
    """Simuliert den Verlauf ab Einstieg bis zum Ausstieg."""
    d = sig.direction
    risk = abs(entry - stop)
    if risk <= 0:
        return sig.bar + 1, entry, "kein_risiko"

    target = entry + d * pol.target_r * risk if pol.target_r else None
    cur_stop = stop
    moved_be = False

    n = len(df)
    last = min(n - 1, sig.bar + 1 + (pol.max_bars or n))
    high = df["high"].to_numpy("float64")
    low = df["low"].to_numpy("float64")

    for i in range(sig.bar + 1, last + 1):
        h, lo_ = high[i], low[i]

        # Stop zuerst pruefen: bei Mehrdeutigkeit innerhalb der Bar
        # gewinnt konservativ der Stop.
        if (d > 0 and lo_ <= cur_stop) or (d < 0 and h >= cur_stop):
            return i, cur_stop, "breakeven" if moved_be else "stop"

        if target is not None and ((d > 0 and h >= target) or (d < 0 and lo_ <= target)):
            return i, target, "ziel"

        # Stop auf Einstand nachziehen, sobald der Puffer verdient ist.
        if pol.breakeven_at_r is not None and not moved_be:
            # Bester Punkt der Bar in Trade-Richtung.
            gain = (h - entry) if d > 0 else (entry - lo_)
            if gain >= pol.breakeven_at_r * risk:
                cur_stop = entry
                moved_be = True

    return last, float(df["close"].iloc[last]), "zeitstop"


def run(
    df: pd.DataFrame,
    signals: list[Signal],
    *,
    costs: Costs = Costs(),
    policy: ExitPolicy = ExitPolicy(),
    symbol: str = "",
    one_at_a_time: bool = True,
) -> list[Trade]:
    """Fuehrt die Signale aus und liefert die Trade-Liste.

    `one_at_a_time` verhindert, dass sich ueberlappende Signale desselben
    Instruments zu einer verdeckten Mehrfachposition aufaddieren - das
    Risiko waere dann nicht mehr das kalkulierte.
    """
    trades: list[Trade] = []
    busy_until = -1
    opens = df["open"].to_numpy("float64")

    for sig in sorted(signals, key=lambda s: s.bar):
        entry_bar = sig.bar + 1
        if entry_bar >= len(df):
            continue
        if one_at_a_time and entry_bar <= busy_until:
            continue

        entry = float(opens[entry_bar])
        d = sig.direction

        stop = sig.stop - d * policy.stop_buffer_r * abs(entry - sig.stop)
        risk = abs(entry - stop)
        if risk <= 0 or not np.isfinite(risk):
            continue
        # Einstieg bereits jenseits des Stops: Setup ist ueberholt.
        if (d > 0 and entry <= stop) or (d < 0 and entry >= stop):
            continue

        exit_bar, exit_px, reason = _exit_price_and_reason(df, sig, entry, stop, policy)

        gross = (exit_px - entry) * d
        cost = (entry + exit_px) * costs.per_side
        r = (gross - cost) / risk

        trades.append(Trade(
            entry_bar=entry_bar, exit_bar=exit_bar, direction=d,
            entry=entry, exit=exit_px, stop=stop, r_multiple=float(r),
            reason=reason, context_scale=sig.context_scale,
            trigger_scale=sig.trigger_scale, symbol=symbol,
            entry_ts=df.index[entry_bar], exit_ts=df.index[exit_bar],
        ))
        busy_until = exit_bar

    return trades


# --------------------------------------------------------------------------
# Kennzahlen
# --------------------------------------------------------------------------

@dataclass
class Metrics:
    n_trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float
    total_r: float
    max_dd_r: float
    trades_per_year: float
    cagr: float
    max_dd_pct: float
    mar: float
    sharpe: float
    deflated_sharpe: float

    def to_series(self) -> pd.Series:
        return pd.Series(self.__dict__)


def _max_drawdown(curve: np.ndarray) -> float:
    peak = np.maximum.accumulate(curve)
    return float(np.max(peak - curve)) if len(curve) else 0.0


def evaluate(
    trades: list[Trade],
    df: pd.DataFrame | None = None,
    *,
    risk_per_trade: float = 0.01,
    n_configs_tried: int = 1,
    years: float | None = None,
) -> Metrics:
    """Kennzahlen mit Schwerpunkt auf der R-Verteilung.

    Die R-Verteilung ist wichtiger als die Kapitalkurve: die Drawdown-Vorgabe
    von 5 % bei 1 % Risiko ist nur erreichbar, wenn der mittlere Verlust
    deutlich unter 1R liegt. Das steht in `avg_loss_r`, nicht in der Rendite.

    Der Zeitraum wird aus den Zeitstempeln der Trades bestimmt, nicht aus der
    Bar-Anzahl eines beliebigen Instruments. Instrumente haben stark
    unterschiedliche Historien - der S&P 500 reicht bis 1927 zurueck, ADA bis
    2018 -, und ein Bar-Bezug wuerde die Trades pro Jahr um ein Vielfaches
    ueberschaetzen.

    `deflated_sharpe` korrigiert fuer Mehrfachtests: wer viele Konfigurationen
    probiert, findet zwangslaeufig eine gute. Ohne diese Korrektur ist ein
    hoher Sharpe ohne Aussagekraft.
    """
    if not trades:
        return Metrics(0, *[float("nan")] * 12)

    # Chronologisch: sonst ist jede Drawdown-Aussage bedeutungslos.
    trades = sorted(
        trades, key=lambda t: (t.exit_ts if t.exit_ts is not None else t.exit_bar)
    )
    r = np.array([t.r_multiple for t in trades], dtype=float)
    wins, losses = r[r > 0], r[r <= 0]

    if years is None:
        years = _calendar_years(trades, df)

    # Kapitalkurve mit fraktionalem Risiko.
    equity = np.cumprod(1.0 + risk_per_trade * r)
    curve = np.concatenate([[1.0], equity])
    dd_pct = float(np.max(np.maximum.accumulate(curve) - curve) /
                   np.max(np.maximum.accumulate(curve)))
    cagr = float(curve[-1] ** (1 / years) - 1) if years and years > 0 else np.nan

    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(len(r) / years)) if (
        r.std(ddof=1) > 0 and years and years > 0
    ) else np.nan

    return Metrics(
        n_trades=len(trades),
        win_rate=float((r > 0).mean()),
        avg_win_r=float(wins.mean()) if len(wins) else 0.0,
        avg_loss_r=float(losses.mean()) if len(losses) else 0.0,
        expectancy_r=float(r.mean()),
        total_r=float(r.sum()),
        max_dd_r=_max_drawdown(np.concatenate([[0.0], np.cumsum(r)])),
        trades_per_year=float(len(r) / years) if years and years > 0 else np.nan,
        cagr=cagr,
        max_dd_pct=dd_pct,
        mar=float(cagr / dd_pct) if dd_pct > 0 and np.isfinite(cagr) else np.nan,
        sharpe=sharpe,
        deflated_sharpe=_deflated_sharpe(r, sharpe, n_configs_tried, years),
    )


def _calendar_years(trades: list[Trade], df: pd.DataFrame | None) -> float:
    """Kalenderspanne, ueber die gehandelt wurde - in Jahren.

    Bevorzugt die Zeitstempel der Trades. Bei einem Portfolio ist das die
    Spanne von der ersten bis zur letzten Position, also die Zeit, in der
    tatsaechlich Kapital im Einsatz war.
    """
    ts = [t.entry_ts for t in trades if t.entry_ts is not None]
    ts += [t.exit_ts for t in trades if t.exit_ts is not None]
    if ts:
        span = (max(ts) - min(ts)).total_seconds()
        return span / (365.25 * 24 * 3600) if span > 0 else np.nan
    if df is not None and len(df) > 2:
        span = (df.index[-1] - df.index[0]).total_seconds()
        return span / (365.25 * 24 * 3600)
    return np.nan


def _deflated_sharpe(
    r: np.ndarray, sharpe: float, n_trials: int, years: float
) -> float:
    """Sharpe nach Korrektur fuer Mehrfachtests (Bailey/Lopez de Prado).

    Zieht die erwartete Bestleistung aus `n_trials` zufaelligen Versuchen ab.
    Bleibt danach nichts uebrig, war das Ergebnis Suchrauschen.
    """
    if not np.isfinite(sharpe) or n_trials < 1 or len(r) < 10:
        return np.nan
    from scipy.stats import norm

    e = 0.5772156649
    if n_trials > 1:
        expected_max = (1 - e) * norm.ppf(1 - 1 / n_trials) + e * norm.ppf(
            1 - 1 / (n_trials * np.e)
        )
    else:
        expected_max = 0.0
    # Erwartetes Maximum ist in Sharpe-Einheiten pro Trade skaliert.
    per_trade_sr = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    adj = per_trade_sr - expected_max / np.sqrt(len(r))
    return float(adj * np.sqrt(len(r) / years)) if years and years > 0 else np.nan
