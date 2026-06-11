import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortlist.stages.resolve_pis import looks_like_fellowship, _career_years
from shortlist.stages.finalize import assign_tier, _is_last_author
from shortlist.stages.retrieve import _pick_in_country_affiliation
from shortlist.schema import Tier


def test_fellowship_detection():
    assert looks_like_fellowship("NIH F31 Predoctoral Fellowship")
    assert looks_like_fellowship("MSCA Postdoctoral Fellowship")
    assert looks_like_fellowship("UKRI doctoral studentship")
    assert not looks_like_fellowship("NSF Standard Grant: trauma intervention RCT")


def test_career_years():
    rec = {"counts_by_year": [{"year": 2015, "works_count": 2},
                              {"year": 2024, "works_count": 5}]}
    assert _career_years(rec) >= 9
    assert _career_years({"counts_by_year": []}) == 0


def test_last_author_detection():
    work = {"authorships": [
        {"author": {"id": "A1"}, "author_position": "first"},
        {"author": {"id": "A2"}, "author_position": "last"},
    ]}
    assert _is_last_author(work, "A2") is True
    assert _is_last_author(work, "A1") is False


def test_tiering_thresholds():
    assert assign_tier(0.9) == Tier.target
    assert assign_tier(0.5) == Tier.reach
    assert assign_tier(0.1) == Tier.safety


def test_country_affiliation_filter():
    authorship = {"institutions": [
        {"display_name": "ETH Zurich", "country_code": "ch"},
        {"display_name": "UNSW", "country_code": "au"},
    ]}
    inst, country = _pick_in_country_affiliation(authorship, {"au", "us"})
    assert country == "AU" and inst == "UNSW"

    inst, country = _pick_in_country_affiliation(authorship, {"us"})
    assert country is None 


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
