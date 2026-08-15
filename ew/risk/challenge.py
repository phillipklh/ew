"""Prop-Challenge als Barriereproblem.

Eine Funding-Challenge ist kein Renditeproblem, sondern ein Barriereproblem:
gesucht ist die Wahrscheinlichkeit, ein Gewinnziel zu erreichen, **bevor**
ein Drawdown-Limit reisst. Das aendert die Optimierung grundlegend.

Bei reiner Wachstumsoptimierung (Kelly) gilt: mehr Risiko heisst mehr
Wachstum, bis zum Kelly-Punkt. Beim Barriereproblem ist das falsch. Es gibt
ein **inneres Optimum**:

  zu kleines Risiko  - das Ziel wird in der verfuegbaren Zeit nicht erreicht
  zu grosses Risiko  - das Drawdown-Limit reisst vorher

Bemerkenswert und fuer die Einordnung wichtig: schon **ohne jede Edge** ist
die Erfolgswahrscheinlichkeit betraechtlich. Bei einem Ziel von 10 % und
einem Limit von 5 % liegt sie nach der klassischen Ruinformel bei 1/3 - das
Verhaeltnis der Barriereabstaende. Wer eine Challenge besteht, hat damit
noch nichts ueber seine Edge bewiesen; und wer sie nicht besteht, hat noch
nichts widerlegt.

Simuliert wird auf der **empirischen R-Verteilung** aus dem Backtest, nicht
auf einer Normalverteilung. Die Schiefe der Verteilung - viele kleine
Verluste, wenige grosse Gewinne - ist fuer das Barriereproblem entscheidend
und ginge bei einer Normalannahme verloren.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Rules:
    """Regelwerk einer Funding-Challenge.

    Die Voreinstellungen entsprechen dem verbreiteten Zuschnitt: 10 %
    Gewinnziel, 10 % maximaler Gesamtverlust, 5 % Tagesverlustlimit.
    """

    profit_target: float = 0.10
    max_drawdown: float = 0.10      # vom Hoechststand aus
    daily_loss_limit: float = 0.05  # vom Tagesstartwert aus
    max_days: int = 60
    trades_per_day: float = 1.0

    @staticmethod
    def two_phase() -> tuple["Rules", "Rules"]:
        """Uebliche zweistufige Challenge: 10 % dann 5 %."""
        return (
            Rules(profit_target=0.10, max_days=30),
            Rules(profit_target=0.05, max_days=60),
        )


@dataclass
class Result:
    p_pass: float
    p_fail_dd: float
    p_fail_time: float
    median_days: float
    p_daily_breach: float
    risk: float

    def __str__(self) -> str:
        return (
            f"Risiko {self.risk:.2%}: bestanden {self.p_pass:.1%}  "
            f"DD-Aus {self.p_fail_dd:.1%}  Zeit-Aus {self.p_fail_time:.1%}  "
            f"Median {self.median_days:.0f} Tage"
        )


def simulate(
    r_samples: np.ndarray,
    rules: Rules,
    risk: float,
    *,
    n_paths: int = 20_000,
    seed: int = 0,
) -> Result:
    """Monte-Carlo ueber Bootstrap-Ziehungen der empirischen R-Verteilung.

    Modelliert werden alle drei Abbruchbedingungen gemeinsam - Gewinnziel,
    Gesamtverlust vom Hoechststand und Tagesverlustlimit. Das Tageslimit
    wird oft uebersehen, ist aber in der Praxis die haeufigste Ursache fuer
    ein vorzeitiges Aus, weil es sich auf den Tagesstartwert bezieht und
    nicht auf den Hoechststand.
    """
    rng = np.random.default_rng(seed)
    r = np.asarray(r_samples, dtype="float64")
    r = r[np.isfinite(r)]
    if len(r) < 20:
        raise ValueError("zu wenige R-Beobachtungen fuer eine Simulation")

    per_day = max(rules.trades_per_day, 1e-9)
    passed = failed_dd = failed_time = daily_breach = 0
    days_to_pass: list[int] = []

    for _ in range(n_paths):
        equity = 1.0
        peak = 1.0
        outcome = None

        for day in range(1, rules.max_days + 1):
            day_start = equity
            n_today = rng.poisson(per_day)
            for _ in range(n_today):
                equity *= 1.0 + risk * r[rng.integers(0, len(r))]
                peak = max(peak, equity)

                if equity <= peak * (1 - rules.max_drawdown):
                    outcome = "dd"
                    break
                if equity <= day_start * (1 - rules.daily_loss_limit):
                    outcome = "daily"
                    break
                if equity >= 1.0 + rules.profit_target:
                    outcome = "pass"
                    break
            if outcome:
                break

        if outcome == "pass":
            passed += 1
            days_to_pass.append(day)
        elif outcome == "dd":
            failed_dd += 1
        elif outcome == "daily":
            daily_breach += 1
        else:
            failed_time += 1

    return Result(
        p_pass=passed / n_paths,
        p_fail_dd=(failed_dd + daily_breach) / n_paths,
        p_fail_time=failed_time / n_paths,
        median_days=float(np.median(days_to_pass)) if days_to_pass else np.nan,
        p_daily_breach=daily_breach / n_paths,
        risk=risk,
    )


def optimal_risk(
    r_samples: np.ndarray,
    rules: Rules,
    *,
    grid: np.ndarray | None = None,
    n_paths: int = 20_000,
    seed: int = 0,
) -> tuple[float, list[Result]]:
    """Sucht das Risiko, das die Bestehenswahrscheinlichkeit maximiert.

    Das Optimum liegt im Inneren, nicht am Rand - genau das unterscheidet
    das Barriereproblem von der Wachstumsoptimierung.
    """
    if grid is None:
        grid = np.array([0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02,
                         0.025, 0.03, 0.04, 0.05])
    results = [simulate(r_samples, rules, float(x), n_paths=n_paths, seed=seed)
               for x in grid]
    best = max(results, key=lambda z: z.p_pass)
    return best.risk, results


def theoretical_no_edge(rules: Rules) -> float:
    """Bestehenswahrscheinlichkeit ohne jede Edge (klassische Ruinformel).

    Bei einem fairen Spiel entspricht sie dem Verhaeltnis der
    Barriereabstaende. Der Wert dient als Bezugsgroesse: liegt eine
    simulierte Wahrscheinlichkeit nicht deutlich darueber, belegt das
    Bestehen keine Faehigkeit.
    """
    a, b = rules.profit_target, rules.max_drawdown
    return b / (a + b)
