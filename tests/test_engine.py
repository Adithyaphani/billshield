"""Rule engine tests. Each asserts both the outcome and the rule that drove it."""

import pytest

from app.models import BillScenario
from app.rules.corpus import Protection
from app.rules.engine import assess


def ids(result):
    return {r.id for r in result.fired_rules}


# --- Emergency -------------------------------------------------------------

def test_emergency_protected_even_out_of_network():
    r = assess(BillScenario(
        care_type="emergency", facility_in_network=False,
        provider_in_network=False,
    ))
    assert r.outcome == Protection.PROTECTED
    assert "EMERGENCY" in ids(r)


def test_emergency_consent_form_does_not_waive():
    r = assess(BillScenario(
        care_type="emergency", signed_consent=True, consent_hours_before=200,
    ))
    assert r.outcome == Protection.PROTECTED


# --- Ambulance -------------------------------------------------------------

def test_air_ambulance_protected():
    r = assess(BillScenario(care_type="air_ambulance"))
    assert r.outcome == Protection.PROTECTED
    assert "AIR_AMBULANCE" in ids(r)


def test_ground_ambulance_not_covered_federally():
    r = assess(BillScenario(care_type="ground_ambulance"))
    assert r.outcome == Protection.NOT_PROTECTED
    assert "GROUND_AMBULANCE_GAP" in ids(r)


def test_ground_ambulance_state_note_when_state_protects():
    r = assess(BillScenario(care_type="ground_ambulance", state="MD"))
    assert r.state_note is not None and "MD" in r.state_note


# --- In-network facility, OON provider -------------------------------------

def test_oon_provider_at_in_network_facility_protected():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="surgery",
    ))
    assert r.outcome == Protection.PROTECTED
    assert "IN_NETWORK_FACILITY" in ids(r)


def test_ancillary_specialty_cannot_be_waived():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="anesthesiology",
        signed_consent=True, consent_hours_before=500,
    ))
    assert r.outcome == Protection.PROTECTED
    assert "ANCILLARY_NO_WAIVER" in ids(r)


def test_valid_waiver_for_non_ancillary():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="surgery", signed_consent=True, consent_hours_before=96,
    ))
    assert r.outcome == Protection.WAIVED
    assert "VALID_WAIVER" in ids(r)


def test_late_consent_is_invalid():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="surgery", signed_consent=True, consent_hours_before=12,
    ))
    assert r.outcome == Protection.PROTECTED
    assert "DEFECTIVE_WAIVER_TIMING" in ids(r)


def test_same_day_three_hour_window_is_valid():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="cardiology", signed_consent=True,
        consent_hours_before=4, same_day_scheduled=True,
    ))
    assert r.outcome == Protection.WAIVED


def test_same_day_under_three_hours_is_invalid():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="cardiology", signed_consent=True,
        consent_hours_before=1, same_day_scheduled=True,
    ))
    assert r.outcome == Protection.PROTECTED


# --- Out of scope ----------------------------------------------------------

def test_oon_facility_not_protected():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=False, provider_in_network=False,
    ))
    assert r.outcome == Protection.NOT_PROTECTED
    assert "OUT_OF_NETWORK_FACILITY" in ids(r)


def test_urgent_care_outside_facility_definition():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="urgent_care",
        facility_in_network=True, provider_in_network=False,
        specialty="other",
    ))
    assert r.outcome == Protection.NOT_PROTECTED
    assert "UNCOVERED_FACILITY_TYPE" in ids(r)


def test_in_network_provider_not_a_surprise_bill():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=True,
    ))
    assert r.outcome == Protection.NOT_PROTECTED


def test_missing_network_facts_requests_them():
    r = assess(BillScenario(care_type="scheduled"))
    assert r.outcome == Protection.NEEDS_INFO
    assert len(r.missing_facts) == 2


# --- Good Faith Estimate ---------------------------------------------------

def test_gfe_gap_at_threshold_allows_dispute():
    r = assess(BillScenario(
        care_type="scheduled", coverage="uninsured_self_pay",
        gfe_provided=True, gfe_amount=1000, billed_amount=1400,
    ))
    assert r.outcome == Protection.GFE_DISPUTE
    assert r.deadline_days == 120


def test_gfe_gap_below_threshold():
    r = assess(BillScenario(
        care_type="scheduled", coverage="uninsured_self_pay",
        gfe_provided=True, gfe_amount=1000, billed_amount=1399,
    ))
    assert r.outcome == Protection.NOT_PROTECTED


def test_no_gfe_provided_is_a_violation():
    r = assess(BillScenario(
        care_type="scheduled", coverage="uninsured_self_pay",
        gfe_provided=False,
    ))
    assert r.outcome == Protection.GFE_DISPUTE
    assert "GFE_NOT_PROVIDED" in ids(r)


# --- Arithmetic and determinism -------------------------------------------

def test_balance_bill_arithmetic():
    r = assess(BillScenario(
        care_type="emergency", billed_amount=8420.50,
        in_network_cost_share=1200.00,
    ))
    assert r.estimated_balance_bill == 7220.50


def test_balance_bill_never_negative():
    r = assess(BillScenario(
        care_type="emergency", billed_amount=100, in_network_cost_share=500,
    ))
    assert r.estimated_balance_bill == 0.0


def test_same_scenario_is_deterministic():
    s = BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="radiology",
    )
    a, b = assess(s), assess(s)
    assert a.model_dump() == b.model_dump()


@pytest.mark.parametrize("specialty", [
    "anesthesiology", "pathology", "radiology", "neonatology",
    "assistant_surgeon", "hospitalist", "intensivist", "diagnostic",
])
def test_every_ancillary_specialty_resists_waiver(specialty):
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty=specialty, signed_consent=True, consent_hours_before=999,
    ))
    assert r.outcome == Protection.PROTECTED


# --- Regression: bugs found in robustness review --------------------------

def test_unknown_specialty_is_rejected_not_guessed():
    """A typo must not yield a confident verdict."""
    with pytest.raises(Exception):
        BillScenario(
            care_type="scheduled", facility_type="hospital",
            facility_in_network=True, provider_in_network=False,
            specialty="anesthesiollogy",
        )


def test_unknown_facility_is_rejected():
    with pytest.raises(Exception):
        BillScenario(care_type="scheduled", facility_type="spaceship")


def test_implausible_amount_is_rejected():
    with pytest.raises(Exception):
        BillScenario(care_type="emergency", billed_amount=1e12)


def test_bad_state_code_is_rejected():
    with pytest.raises(Exception):
        BillScenario(care_type="ground_ambulance", state="ZZZ9")


def test_state_code_is_normalised():
    assert BillScenario(care_type="ground_ambulance", state=" tx ").state == "TX"


def test_consent_without_timing_asks_rather_than_guesses():
    r = assess(BillScenario(
        care_type="scheduled", facility_type="hospital",
        facility_in_network=True, provider_in_network=False,
        specialty="surgery", signed_consent=True,
    ))
    assert r.outcome == Protection.NEEDS_INFO
    assert r.missing_facts


def test_letter_survives_ampersands_and_angle_brackets():
    """ReportLab parses markup; unescaped '&' in a hospital name crashed it."""
    from app.letter import build_letter
    from app.models import LetterRequest
    s = BillScenario(care_type="emergency")
    pdf = build_letter(
        LetterRequest(
            scenario=s, patient_name="Mary O'Brien & Sons",
            provider_name="Barnes & Jewish <Hospital>",
        ),
        assess(s),
    )
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
