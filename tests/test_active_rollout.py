import pytest

from tools.active_rollout import (ACTIVE_COUNTRIES, RolloutRegistryError,
                                  country_record, load_active, requested_selection)


def test_active_rollout_is_exactly_the_user_approved_twenty():
    data = load_active()
    assert tuple(data["countries"]) == ACTIVE_COUNTRIES
    assert set(data["delivery_status"]) == set(ACTIVE_COUNTRIES)


def test_sheet_provenance_is_separate_from_rollout_order():
    assert country_record("AR")["content_locale"] == "es-AR"
    assert country_record("AR")["language_pack"] == "es-419"
    assert country_record("AR")["source_rank"] is None
    assert country_record("AR")["selection_provenance"] == "user-provided image 20ประเทศ.png; rollout_order=4"


def test_requested_eight_are_separate_from_delivery_and_admission():
    selection = requested_selection(["TH", "ZA", "MY", "BR", "AR", "CL", "RU", "MX"])
    assert selection["requested"] == ["TH", "ZA", "MY", "BR", "AR", "CL", "RU", "MX"]
    assert selection["held"] == []
    rows = {row["country_code"]: row for row in selection["countries"]}
    assert rows["TH"]["eligible"] is True
    assert rows["ZA"]["output_folder"] == "ZA-South-Africa"
    assert rows["RU"]["hold_reason"] is None
    assert {row["delivered"] for row in rows.values()} == {"UNVERIFIED"}
    assert {row["admitted"] for row in rows.values()} == {"UNVERIFIED"}


def test_requested_selection_rejects_unknown_and_duplicate_codes():
    with pytest.raises(RolloutRegistryError, match="outside active rollout"):
        requested_selection(["TH", "XX"])
    with pytest.raises(RolloutRegistryError, match="duplicates"):
        requested_selection(["TH", "TH"])
