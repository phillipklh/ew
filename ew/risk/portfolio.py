"""Portfolio-Risiko: Heat-Cap, Korrelations-Cluster, Streak-Drosselung.

Der Drawdown ist bei diesem Zielprofil die bindende Nebenbedingung, nicht die
Rendite. Drei Mechanismen halten ihn - jeder adressiert eine andere Ursache:

**Heat-Cap.** Zehn gleichzeitige Positionen zu je 1 % sind ein 10-%-Einsatz,
kein 1-%-Einsatz. Begrenzt wird deshalb das gleichzeitig offene Gesamtrisiko.

**Korrelations-Cluster.** Zehn Krypto-Longs sind wirtschaftlich eine einzige
Position. Das Risiko wird deshalb je Cluster gedeckelt, nicht nur je Position.

**Streak-Drosselung.** Nach mehreren Verlusten in Folge wird das Risiko
reduziert. Das ist keine Aberglaubensregel, sondern folgt direkt aus der
Barriere-Logik: naeher am Limit ist ein kleinerer Einsatz optimal, weil ein
weiterer voller Verlust das Aus bedeuten kann.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Limits:
    base_risk: float = 0.01
    max_portfolio_heat: float = 0.04     # gleichzeitig offenes Gesamtrisiko
    max_cluster_heat: float = 0.02       # je Korrelationsgruppe
    max_positions: int = 6
    #: Ab dieser Zahl aufeinanderfolgender Verluste wird gedrosselt.
    streak_threshold: int = 3
    streak_factor: float = 0.5
    #: Naeher als dieser Abstand am Drawdown-Limit wird zusaetzlich gedrosselt.
    dd_guard: float = 0.6


@dataclass
class Position:
    symbol: str
    cluster: str
    risk: float


@dataclass
class Book:
    """Offene Positionen und die daraus folgende Risikofreigabe."""

    limits: Limits = field(default_factory=Limits)
    positions: list[Position] = field(default_factory=list)
    loss_streak: int = 0

    @property
    def heat(self) -> float:
        return sum(p.risk for p in self.positions)

    def cluster_heat(self, cluster: str) -> float:
        return sum(p.risk for p in self.positions if p.cluster == cluster)

    def allowed_risk(
        self, cluster: str, *, drawdown_used: float = 0.0
    ) -> float:
        """Wie viel Risiko darf eine neue Position tragen?

        `drawdown_used` ist der bereits verbrauchte Anteil des erlaubten
        Drawdowns (0 = unberuehrt, 1 = Limit erreicht).
        """
        lim = self.limits
        if len(self.positions) >= lim.max_positions:
            return 0.0

        risk = lim.base_risk
        if self.loss_streak >= lim.streak_threshold:
            risk *= lim.streak_factor
        if drawdown_used >= lim.dd_guard:
            # Linear gegen null, je naeher das Limit rueckt.
            risk *= max(0.0, (1.0 - drawdown_used) / (1.0 - lim.dd_guard))

        risk = min(risk, lim.max_portfolio_heat - self.heat)
        risk = min(risk, lim.max_cluster_heat - self.cluster_heat(cluster))
        return max(risk, 0.0)

    def open(self, symbol: str, cluster: str, risk: float) -> bool:
        if risk <= 0:
            return False
        self.positions.append(Position(symbol, cluster, risk))
        return True

    def close(self, symbol: str, r_multiple: float) -> None:
        self.positions = [p for p in self.positions if p.symbol != symbol]
        self.loss_streak = self.loss_streak + 1 if r_multiple <= 0 else 0


def correlation_clusters(
    returns: dict[str, np.ndarray], threshold: float = 0.6
) -> dict[str, str]:
    """Bildet Cluster aus tatsaechlich gemessener Korrelation.

    Die statische Zuordnung im Universum (crypto_major, equity_tech, ...) ist
    eine Annahme. Gemessene Korrelationen sind belastbarer, besonders weil
    sie sich in Stressphasen verschieben - und genau dort entscheidet sich
    der Drawdown.
    """
    syms = sorted(returns)
    if len(syms) < 2:
        return {s: s for s in syms}

    n = min(len(returns[s]) for s in syms)
    m = np.vstack([returns[s][-n:] for s in syms])
    c = np.corrcoef(m)

    cluster_of: dict[str, str] = {}
    for i, s in enumerate(syms):
        if s in cluster_of:
            continue
        cluster_of[s] = s
        for j in range(i + 1, len(syms)):
            if syms[j] not in cluster_of and c[i, j] >= threshold:
                cluster_of[syms[j]] = s
    return cluster_of
