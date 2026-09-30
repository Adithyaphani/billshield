"""
Statutory rule corpus for the federal No Surprises Act (NSA).

Every rule carries its legal citation. The engine never invents a
determination: it fires rules from this corpus and reports which ones
fired, so a user can check the reasoning against the source text.

Primary sources:
  - Public Health Service Act ss. 2799A-1, 2799A-2 (42 U.S.C. 300gg-111/112)
  - 45 CFR Part 149 (HHS implementing regulations)
  - 45 CFR 149.610 (Good Faith Estimate, uninsured/self-pay)
  - 45 CFR 149.620 (Patient-Provider Dispute Resolution)
"""

from enum import Enum
from typing import NamedTuple


class Protection(str, Enum):
    """Outcome of an assessment."""

    PROTECTED = "protected"
    NOT_PROTECTED = "not_protected"
    WAIVED = "waived"
    GFE_DISPUTE = "gfe_dispute"
    NEEDS_INFO = "needs_info"


class Rule(NamedTuple):
    """A single statutory rule."""

    id: str
    title: str
    citation: str
    summary: str
    outcome: Protection


# --- Facility types where the in-network-facility protection attaches -------
# 45 CFR 149.30 definition of "health care facility"
COVERED_FACILITIES = {
    "hospital": "Hospital",
    "hospital_outpatient": "Hospital outpatient department",
    "ambulatory_surgical": "Ambulatory surgical center",
    "critical_access": "Critical access hospital",
}

NON_COVERED_FACILITIES = {
    "urgent_care": "Urgent care clinic",
    "physician_office": "Independent physician office",
    "imaging_center": "Freestanding imaging center",
}

# --- Ancillary services: protection can NEVER be waived by consent ---------
# 45 CFR 149.420(g) - notice and consent is unavailable for these
ANCILLARY_SPECIALTIES = {
    "emergency_medicine": "Emergency medicine",
    "anesthesiology": "Anesthesiology",
    "pathology": "Pathology",
    "radiology": "Radiology",
    "neonatology": "Neonatology",
    "assistant_surgeon": "Assistant surgeon",
    "hospitalist": "Hospitalist",
    "intensivist": "Intensivist",
    "diagnostic": "Diagnostic services (laboratory and imaging)",
}

WAIVABLE_SPECIALTIES = {
    "surgery": "Surgery (non-assistant)",
    "cardiology": "Cardiology",
    "orthopedics": "Orthopedics",
    "dermatology": "Dermatology",
    "other": "Other non-ancillary specialty",
}


RULES: dict[str, Rule] = {
    "EMERGENCY": Rule(
        id="EMERGENCY",
        title="Emergency services are protected regardless of network status",
        citation="PHSA s. 2799A-1(a); 45 CFR 149.110",
        summary=(
            "Emergency services furnished at any hospital emergency department "
            "or freestanding emergency department are protected from balance "
            "billing, whether or not the provider or facility is in network. "
            "Prior authorisation cannot be required."
        ),
        outcome=Protection.PROTECTED,
    ),
    "POST_STABILIZATION": Rule(
        id="POST_STABILIZATION",
        title="Post-stabilisation care remains protected until safe transfer",
        citation="45 CFR 149.110(b); 45 CFR 149.410",
        summary=(
            "Care after stabilisation stays protected until the patient can "
            "safely travel by non-medical transport, unless the provider "
            "obtained valid written notice and consent."
        ),
        outcome=Protection.PROTECTED,
    ),
    "IN_NETWORK_FACILITY": Rule(
        id="IN_NETWORK_FACILITY",
        title="Out-of-network provider at an in-network facility",
        citation="PHSA s. 2799A-1(b); 45 CFR 149.120",
        summary=(
            "Non-emergency services delivered by an out-of-network provider at "
            "an in-network health care facility are protected. The patient "
            "cannot be billed more than in-network cost sharing."
        ),
        outcome=Protection.PROTECTED,
    ),
    "ANCILLARY_NO_WAIVER": Rule(
        id="ANCILLARY_NO_WAIVER",
        title="Ancillary services cannot be waived by consent",
        citation="45 CFR 149.420(g)",
        summary=(
            "For ancillary specialties, a provider may not ask the patient to "
            "waive balance-billing protections. Any signed consent form for "
            "these services is void and protection stands."
        ),
        outcome=Protection.PROTECTED,
    ),
    "AIR_AMBULANCE": Rule(
        id="AIR_AMBULANCE",
        title="Out-of-network air ambulance is protected",
        citation="PHSA s. 2799A-2; 45 CFR 149.130",
        summary=(
            "Out-of-network air ambulance services are protected. The patient "
            "owes only in-network cost sharing, and it must count toward the "
            "in-network deductible and out-of-pocket maximum."
        ),
        outcome=Protection.PROTECTED,
    ),
    "GROUND_AMBULANCE_GAP": Rule(
        id="GROUND_AMBULANCE_GAP",
        title="Ground ambulance is NOT covered by the federal NSA",
        citation="PHSA s. 2799A-2 (air ambulance only)",
        summary=(
            "The federal No Surprises Act does not cover ground ambulance "
            "transport. This is a known statutory gap. Some states have their "
            "own ground ambulance balance-billing laws, so a state-level check "
            "is worthwhile."
        ),
        outcome=Protection.NOT_PROTECTED,
    ),
    "VALID_WAIVER": Rule(
        id="VALID_WAIVER",
        title="Valid notice and consent waived the protection",
        citation="45 CFR 149.410; 45 CFR 149.420",
        summary=(
            "For non-emergency, non-ancillary services, a provider may obtain "
            "written consent to waive protections using the standard federal "
            "notice, delivered at least 72 hours before the appointment (or 3 "
            "hours if scheduled same-day). A valid waiver permits balance "
            "billing."
        ),
        outcome=Protection.WAIVED,
    ),
    "DEFECTIVE_WAIVER_TIMING": Rule(
        id="DEFECTIVE_WAIVER_TIMING",
        title="Consent obtained too late is invalid",
        citation="45 CFR 149.420(e)",
        summary=(
            "Notice and consent must be given at least 72 hours before a "
            "scheduled appointment, or at least 3 hours before service when "
            "the appointment is made same-day. Consent collected inside that "
            "window does not waive protection."
        ),
        outcome=Protection.PROTECTED,
    ),
    "OUT_OF_NETWORK_FACILITY": Rule(
        id="OUT_OF_NETWORK_FACILITY",
        title="Non-emergency care at an out-of-network facility",
        citation="45 CFR 149.120 (scope)",
        summary=(
            "Choosing an out-of-network facility for non-emergency, scheduled "
            "care falls outside the federal protections. Balance billing is "
            "generally permitted in this situation."
        ),
        outcome=Protection.NOT_PROTECTED,
    ),
    "UNCOVERED_FACILITY_TYPE": Rule(
        id="UNCOVERED_FACILITY_TYPE",
        title="Facility type is outside the statutory definition",
        citation="45 CFR 149.30 (definition of health care facility)",
        summary=(
            "The in-network-facility protection applies to hospitals, hospital "
            "outpatient departments, ambulatory surgical centers and critical "
            "access hospitals. Urgent care clinics, independent physician "
            "offices and freestanding imaging centers are not included unless "
            "the visit was genuinely emergency care."
        ),
        outcome=Protection.NOT_PROTECTED,
    ),
    "GFE_400_THRESHOLD": Rule(
        id="GFE_400_THRESHOLD",
        title="Bill exceeds the Good Faith Estimate by $400 or more",
        citation="45 CFR 149.620(b)",
        summary=(
            "An uninsured or self-pay patient billed at least $400 above the "
            "Good Faith Estimate may start Patient-Provider Dispute "
            "Resolution. The initiation deadline is 120 calendar days from "
            "receipt of the bill."
        ),
        outcome=Protection.GFE_DISPUTE,
    ),
    "GFE_UNDER_THRESHOLD": Rule(
        id="GFE_UNDER_THRESHOLD",
        title="Bill is within the Good Faith Estimate tolerance",
        citation="45 CFR 149.620(b)",
        summary=(
            "The billed amount is less than $400 above the Good Faith "
            "Estimate, so the federal dispute resolution process is not "
            "available on that basis."
        ),
        outcome=Protection.NOT_PROTECTED,
    ),
    "GFE_NOT_PROVIDED": Rule(
        id="GFE_NOT_PROVIDED",
        title="No Good Faith Estimate was provided",
        citation="45 CFR 149.610",
        summary=(
            "Providers must give uninsured and self-pay patients a written "
            "Good Faith Estimate for scheduled care. Failure to provide one is "
            "itself a compliance failure and is worth raising with the "
            "provider and with CMS."
        ),
        outcome=Protection.GFE_DISPUTE,
    ),
}


# Cost-sharing consequence when protection attaches.
COST_SHARING_NOTE = (
    "When protection applies, the patient owes only the in-network cost "
    "sharing for the service. Any amount billed above that is the balance "
    "bill. The in-network amount must also count toward the in-network "
    "deductible and out-of-pocket maximum."
)

CMS_COMPLAINT = {
    "name": "No Surprises Help Desk (CMS)",
    "phone": "1-800-985-3059",
    "url": "https://www.cms.gov/nosurprises",
}

PPDR_DEADLINE_DAYS = 120
GFE_THRESHOLD_USD = 400
