"""Tests der Hypothesen-Aufzaehlung.

Schwerpunkt liegt auf Kausalitaet: die Aufzaehlung darf zu keinem Zeitpunkt
Pivots verwenden, die zu diesem Zeitpunkt noch nicht bestaetigt waren. Ein
Fehler hier waere im Backtest unsichtbar und im Livebetrieb fatal.
"""

from __future__ import annotations

import pytest

from ew import pivots
from ew.labeling import enumerate_complete, enumerate_in_progress
from ew.rules import Config, PatternType
from ew.rules import geometry as g

from .test_pivots import synth


@pytest.fixture(scope="module")
def lat():
    return pivots.build(synth(3000, seed=7))


@pytest.fixture(scope="module")
def df():
    return synth(3000, seed=7)


# --------------------------------------------------------------------------
# Kausalitaet
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bar", [800, 1400, 2200])
def test_complete_labelings_use_only_confirmed_pivots(lat, bar):
    for lab in enumerate_complete(lat, 3, up_to_bar=bar):
        for p in lab.pivots:
            assert p.confirmed_idx <= bar
        assert lab.confirmed_idx <= bar


@pytest.mark.parametrize("bar", [800, 1400, 2200])
def test_in_progress_uses_only_confirmed_pivots(lat, bar):
    for s in range(2, 6):
        for h in enumerate_in_progress(lat, s, bar):
            for p in h.pivots:
                assert p.confirmed_idx <= bar
            assert h.confirmed_idx <= bar


def test_labeling_is_stable_under_truncation(df):
    """Das Ergebnis darf nicht davon abhaengen, ob die Zukunft vorliegt."""
    bar = 1500
    full = pivots.build(df)
    trunc = pivots.build(df.iloc[: bar + 1])

    def key(labs):
        return sorted(
            (l.pattern.value, l.pivots[0].idx, l.pivots[-1].idx) for l in labs
        )

    for s in (2, 3, 4):
        a = key(enumerate_complete(full, s, up_to_bar=bar))
        b = key(enumerate_complete(trunc, s, up_to_bar=bar))
        assert a == b, f"Ebene {s} unterscheidet sich nach Abschneiden"


# --------------------------------------------------------------------------
# Regelkonformitaet der Ergebnisse
# --------------------------------------------------------------------------

def test_all_enumerated_labelings_satisfy_their_rules(lat):
    from ew.rules import WAVE_COUNT

    for s in (2, 3, 4):
        for lab in enumerate_complete(lat, s):
            assert lab.check.ok, (lab, [str(v) for v in lab.check.violations])
            # Pivotanzahl muss zur Wellenzahl des Musters passen.
            assert len(lab.pivots) == WAVE_COUNT[lab.pattern] + 1, lab
            assert g.alternates(lab.pivots)
            assert g.monotonic_time(lab.pivots)


def test_anchor_pivots_are_excluded(lat):
    for s in (2, 3, 4):
        for lab in enumerate_complete(lat, s):
            assert not any(p.is_anchor for p in lab.pivots)


def test_substructure_score_in_unit_range(lat):
    for lab in enumerate_complete(lat, 4):
        assert 0.0 <= lab.substructure <= 1.0


# --------------------------------------------------------------------------
# Invalidierungslevel der laufenden Hypothesen
# --------------------------------------------------------------------------

def test_wave3_hypothesis_invalidation_is_wave1_start(lat):
    """Vor Welle 3 ist der Start von Welle 1 die Grenze (Welle 2 darf ihn nie reissen)."""
    found = False
    for s in range(2, 6):
        for h in enumerate_in_progress(lat, s, 2500):
            if h.next_wave == 3:
                assert h.invalidation == h.pivots[0].price
                assert len(h.pivots) == 3
                found = True
    assert found, "keine Welle-3-Hypothese im Testfenster"


def test_wave5_hypothesis_invalidation_is_wave1_end(lat):
    """Vor Welle 5 ist das Ende von Welle 1 die Grenze (keine Ueberlappung)."""
    for s in range(2, 6):
        for bar in (1200, 1800, 2500):
            for h in enumerate_in_progress(lat, s, bar):
                if h.next_wave == 5:
                    assert h.invalidation == h.pivots[1].price
                    assert len(h.pivots) == 5


def test_hypothesis_direction_matches_wave_one(lat):
    for s in range(2, 6):
        for h in enumerate_in_progress(lat, s, 2500):
            expected = 1 if h.pivots[1].price > h.pivots[0].price else -1
            assert h.direction == expected


def test_is_alive_respects_invalidation(lat):
    for s in range(2, 6):
        for h in enumerate_in_progress(lat, s, 2500):
            inv = h.invalidation
            if h.direction > 0:
                assert not h.is_alive(high=inv, low=inv * 0.99)
                assert h.is_alive(high=inv * 1.05, low=inv * 1.01)
            else:
                assert not h.is_alive(high=inv * 1.01, low=inv)
                assert h.is_alive(high=inv * 0.99, low=inv * 0.95)


# --------------------------------------------------------------------------
# Mehrdeutigkeit
# --------------------------------------------------------------------------

def test_enumeration_surfaces_ambiguity(lat):
    """Mehrere zulaessige Lesarten sind der Normalfall und muessen sichtbar sein."""
    labs = enumerate_complete(lat, 3)
    kinds = {l.pattern for l in labs}
    assert len(labs) > 10
    assert len(kinds) >= 3


def test_config_affects_impulse_admissibility(lat):
    """Die Ueberlappungstoleranz muss durchschlagen."""
    strict = enumerate_complete(lat, 3, Config(), patterns=(PatternType.IMPULSE,))
    loose = enumerate_complete(lat, 3, Config.leveraged(),
                               patterns=(PatternType.IMPULSE,))
    assert len(loose) >= len(strict)
