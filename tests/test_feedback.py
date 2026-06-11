
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortlist.feedback import build_priors, OUTCOME_REWARD


CSV = str(Path(__file__).resolve().parents[1] / "sample_input" / "outcomes.csv")


def test_flags_data_errors():
    priors = build_priors(CSV)
    flagged_outcomes = {f["outcome"] for f in priors.flagged_for_review}
    assert "WRONG_PERSON" in flagged_outcomes
    assert "BOUNCE" in flagged_outcomes
    assert len(priors.flagged_for_review) == 3


def test_positive_pi_gets_boost():
    priors = build_priors(CSV)
    mult = priors.score_multiplier("A5012340008", "Stanford University", "PTSD")
    assert mult > 1.0


def test_wrong_person_gets_penalised():
    priors = build_priors(CSV)
    mult = priors.score_multiplier("A5012340005", "National Bureau of Economic Research", "Pilgrim")
    assert mult < 1.0


def test_multiplier_bounded():
    priors = build_priors(CSV)
    worst = priors.score_multiplier("A5012340005", "National Bureau of Economic Research", "Pilgrim")
    best = priors.score_multiplier("A5012340008", "Stanford University", "PTSD")
    assert 0.6 <= worst <= 1.4
    assert 0.6 <= best <= 1.4


def test_unknown_supervisor_falls_back_to_area():
    priors = build_priors(CSV)
    mult = priors.score_multiplier("A_NEVER_SEEN", "Some Uni", "PTSD")
    assert 0.6 <= mult <= 1.4


def test_reward_table_sanity():
    assert OUTCOME_REWARD["WRONG_PERSON"] < OUTCOME_REWARD["REJECT"] < OUTCOME_REWARD["ADMIT"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
