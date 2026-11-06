"""Caveat checks in src/agent/scoring.py: must_mention / must_not_mention and the comparison-claim check (KI-1).

    pytest -q
"""

from src.agent.scoring import caveat_check, comparison_claims

D15 = {"must_mention": [["partial"]], "must_not_mention": ["lower than", "fewer than", "may be lower"]}
KI1 = ["FY2027 is partial (44 loans and guarantees in total).", "Guarantees excluded, so the count may be lower than 44."]


def test_must_not_mention_fails_the_ki1_text():
    assert caveat_check(D15, "", KI1) == (False, [], ["lower than", "may be lower"])


def test_must_not_mention_passes_a_correct_caveat():
    assert caveat_check(D15, "", ["FY2027 is partial: Jul-Sep 2026 only.", "Guarantees excluded."]) == (True, [], [])


def test_no_terms_means_no_check():
    assert caveat_check({}, "anything", []) is None


def test_lower_than_the_result_is_contradicted():
    assert comparison_claims("", KI1, [[44]]) == ["lower than 44"]


def test_claims_that_hold_are_not_reported():
    assert comparison_claims("That is more than 40 and fewer than 50.", [], [[44]]) == []


def test_higher_than_with_units():
    assert comparison_claims("Likely higher than $2.5 billion.", [], [[2_400_000_000.0]]) == ["higher than $2.5 billion"]
    assert comparison_claims("Likely higher than US$2.5B.", [], [[2_600_000_000.0]]) == []


def test_only_single_number_results_are_checked():
    assert comparison_claims("lower than 44", [], [[44], [45]]) is None
    assert comparison_claims("lower than 44", [], [["Turkiye", 44, 1.5]]) is None
    assert comparison_claims("lower than 44", [], [["Turkiye", 44]]) == ["lower than 44"]
