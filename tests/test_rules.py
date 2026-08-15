"""Tests der harten Elliott-Regeln.

Aufbau: zu jeder Regel ein Muster, das sie erfuellt, und eines, das sie
gezielt und nur sie verletzt. Das prueft nicht nur, dass Verletzungen
erkannt werden, sondern auch, dass die Engine nicht zu streng ist - der
haeufigere und teurere Fehler, weil er gueltige Zaehlungen verwirft.
"""

from __future__ import annotations

import pytest

from ew.pivots.zigzag import HIGH, LOW, Pivot
from ew.rules import patterns as P
from ew.rules.patterns import Config, PatternType


def seq(prices: list[float], start_idx: int = 0, step: int = 10) -> list[Pivot]:
    """Baut eine alternierende Pivot-Folge aus reinen Preisen."""
    out: list[Pivot] = []
    for i, pr in enumerate(prices):
        if i == 0:
            kind = HIGH if prices[1] < pr else LOW
        else:
            kind = HIGH if pr > prices[i - 1] else LOW
        idx = start_idx + i * step
        out.append(Pivot(idx=idx, price=float(pr), kind=kind, confirmed_idx=idx + 2))
    return out


# --------------------------------------------------------------------------
# Impuls
# --------------------------------------------------------------------------

VALID_IMPULSE = [100, 120, 110, 160, 145, 180]


def test_valid_impulse_passes():
    r = P.check_impulse(seq(VALID_IMPULSE))
    assert r.ok, [str(v) for v in r.violations]


def test_impulse_downward_passes():
    r = P.check_impulse(seq([200, 180, 190, 140, 155, 120]))
    assert r.ok, [str(v) for v in r.violations]


def test_w2_may_not_exceed_w1_start():
    #                       W2 faellt unter den Start
    r = P.check_impulse(seq([100, 120, 95, 160, 145, 180]))
    assert not r.ok
    assert any(v.rule == "W2_RETRACE" for v in r.violations)


def test_w3_must_pass_w1_end():
    r = P.check_impulse(seq([100, 120, 110, 118, 112, 140]))
    assert not r.ok
    assert any(v.rule == "W3_BEYOND_W1" for v in r.violations)


def test_w3_never_shortest():
    # W1 = 40, W3 = 15, W5 = 40  ->  W3 ist die kuerzeste
    r = P.check_impulse(seq([100, 140, 130, 145, 138, 178]))
    assert not r.ok
    assert any(v.rule == "W3_SHORTEST" for v in r.violations)


def test_w3_shortest_uses_percentage_not_absolute():
    """Die Regel ist prozentual formuliert.

    Ueber Historien mit vervielfachtem Kursniveau wirkt eine spaete Welle
    allein durch das Niveau riesig; arithmetisch verglichen wuerde die Regel
    dann falsch greifen.
    """
    # W1: 100->200 (+100%), W3: 180->400 (+122%), W5: 360->700 (+94%)
    # Arithmetisch waere W3 (220) laenger als W1 (100) - beides konsistent.
    r = P.check_impulse(seq([100, 200, 180, 400, 360, 700]))
    assert r.ok, [str(v) for v in r.violations]


def test_w4_may_not_overlap_w1_in_impulse():
    r = P.check_impulse(seq([100, 120, 110, 160, 115, 180]))
    assert not r.ok
    assert any(v.rule == "W4_OVERLAP" for v in r.violations)


def test_overlap_tolerance_for_leveraged_markets():
    """Das Buch nimmt gehebelte Maerkte von der strikten Regel aus."""
    pivots = seq([100, 120, 110, 160, 119, 180])  # 5 % Eindringen in W1
    assert not P.check_impulse(pivots, Config()).ok
    assert P.check_impulse(pivots, Config.leveraged()).ok


def test_truncated_fifth_is_allowed_but_noted():
    """Truncation ist eine zulaessige Variante, keine Regelverletzung."""
    r = P.check_impulse(seq([100, 120, 110, 160, 145, 155]))
    assert r.ok, [str(v) for v in r.violations]
    assert "truncated_fifth" in r.notes


def test_impulse_reports_extension_wave():
    r = P.check_impulse(seq(VALID_IMPULSE))
    assert any(n.startswith("extension_w") for n in r.notes)


# --------------------------------------------------------------------------
# Diagonale
# --------------------------------------------------------------------------

def test_valid_ending_diagonal():
    # Keilform: W4 dringt in W1 ein, die Wellen werden kuerzer, Linien konvergieren
    r = P.check_diagonal(seq([100, 150, 120, 155, 132, 158]), ending=True)
    assert r.ok, [str(v) for v in r.violations]


def test_diagonal_requires_overlap():
    """Ohne Ueberlappung ist es ein Impuls, keine Diagonale."""
    r = P.check_diagonal(seq(VALID_IMPULSE), ending=True)
    assert not r.ok
    assert any(v.rule == "NO_OVERLAP" for v in r.violations)


def test_expanding_wedge_rejected():
    """Der ausgeweitete Keil gilt im Buch nicht als gueltige Variante.

    Die motiven Regeln und die Ueberlappung sind hier erfuellt - allein die
    Divergenz der Begrenzungslinien fuehrt zur Ablehnung.
    """
    r = P.check_diagonal(seq([100, 130, 115, 155, 118, 200]), ending=True)
    assert not r.ok
    assert [v.rule for v in r.violations] == ["NOT_CONTRACTING"]


# --------------------------------------------------------------------------
# Korrekturen
# --------------------------------------------------------------------------

def test_valid_zigzag():
    # A abwaerts, B flach zurueck, C unter A-Ende
    r = P.check_zigzag(seq([200, 150, 175, 120]))
    assert r.ok, [str(v) for v in r.violations]


def test_zigzag_b_may_not_exceed_a_start():
    r = P.check_zigzag(seq([200, 150, 205, 120]))
    assert not r.ok
    assert any(v.rule == "B_EXCEEDS_A_START" for v in r.violations)


def test_zigzag_c_must_pass_a_end():
    r = P.check_zigzag(seq([200, 150, 175, 160]))
    assert not r.ok
    assert any(v.rule == "C_SHORT_OF_A" for v in r.violations)


def test_deep_b_is_flat_not_zigzag():
    """Ein B, das A fast vollstaendig zurueckholt, ist ein Flat."""
    pivots = seq([200, 150, 197, 140])
    assert not P.check_zigzag(pivots).ok
    assert P.check_flat(pivots).ok


def test_flat_requires_deep_b():
    r = P.check_flat(seq([200, 150, 165, 120]))
    assert not r.ok
    assert any(v.rule == "B_TOO_SHALLOW" for v in r.violations)


def test_expanded_flat_noted():
    # B laeuft ueber den A-Start hinaus, C deutlich ueber das A-Ende
    r = P.check_flat(seq([200, 150, 210, 130]))
    assert r.ok, [str(v) for v in r.violations]
    assert "expanded" in r.notes


def test_running_flat_noted():
    """Running Flat: B ueber den A-Start, C verfehlt das A-Ende."""
    r = P.check_flat(seq([200, 150, 212, 160]))
    assert r.ok, [str(v) for v in r.violations]
    assert "running" in r.notes


# --------------------------------------------------------------------------
# Dreieck
# --------------------------------------------------------------------------

def test_contracting_triangle():
    r = P.check_triangle(seq([200, 140, 185, 150, 175, 158]))
    assert r.ok, [str(v) for v in r.violations]
    assert "contracting" in r.notes


# --------------------------------------------------------------------------
# Struktur und Mehrdeutigkeit
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ptype,n", [(PatternType.IMPULSE, 6), (PatternType.ZIGZAG, 4),
                (PatternType.TRIANGLE, 6), (PatternType.FLAT, 4)]
)
def test_wrong_pivot_count_rejected(ptype, n):
    r = P.check(ptype, seq([100.0 + 10 * i for i in range(n + 1)]))
    assert not r.ok
    assert any(v.rule == "STRUKTUR" for v in r.violations)


def test_non_alternating_pivots_rejected():
    bad = [
        Pivot(0, 100, LOW, 1), Pivot(10, 120, HIGH, 11), Pivot(20, 130, HIGH, 21),
        Pivot(30, 160, HIGH, 31), Pivot(40, 145, LOW, 41), Pivot(50, 180, HIGH, 51),
    ]
    assert not P.check_impulse(bad).ok


def test_all_matching_returns_every_valid_reading():
    """Mehrdeutigkeit ist der Normalfall - die Engine darf sie nicht verstecken."""
    got = {c.pattern for c in P.all_matching(seq([200, 150, 197, 140]))}
    assert PatternType.FLAT in got
    assert PatternType.ZIGZAG not in got


def test_valid_impulse_is_not_also_a_diagonal():
    got = {c.pattern for c in P.all_matching(seq(VALID_IMPULSE))}
    assert PatternType.IMPULSE in got
    assert PatternType.ENDING_DIAGONAL not in got
