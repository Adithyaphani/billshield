"""Request and response schemas."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.rules.corpus import (
    ANCILLARY_SPECIALTIES,
    COVERED_FACILITIES,
    NON_COVERED_FACILITIES,
    Protection,
    WAIVABLE_SPECIALTIES,
)

_FACILITIES = set(COVERED_FACILITIES) | set(NON_COVERED_FACILITIES)
_SPECIALTIES = set(ANCILLARY_SPECIALTIES) | set(WAIVABLE_SPECIALTIES)


class BillScenario(BaseModel):
    """The facts of a single medical bill."""

    care_type: Literal[
        "emergency", "post_stabilization", "scheduled", "air_ambulance",
        "ground_ambulance",
    ] = Field(description="What kind of care was delivered.")

    coverage: Literal["insured", "uninsured_self_pay"] = "insured"

    facility_type: Optional[str] = Field(
        default=None, description="Facility category key."
    )
    facility_in_network: Optional[bool] = Field(
        default=None, description="Was the facility in the patient's network?"
    )
    provider_in_network: Optional[bool] = Field(
        default=None, description="Was the treating provider in network?"
    )
    specialty: Optional[str] = Field(
        default=None, description="Treating provider's specialty key."
    )

    signed_consent: bool = Field(
        default=False, description="Did the patient sign a waiver form?"
    )
    consent_hours_before: Optional[float] = Field(
        default=None,
        description="Hours between receiving the consent form and service.",
    )
    same_day_scheduled: bool = Field(
        default=False, description="Was the appointment booked the same day?"
    )

    gfe_provided: Optional[bool] = Field(
        default=None, description="Was a Good Faith Estimate provided?"
    )
    gfe_amount: Optional[float] = Field(default=None, ge=0)
    billed_amount: Optional[float] = Field(default=None, ge=0)
    in_network_cost_share: Optional[float] = Field(default=None, ge=0)

    state: Optional[str] = Field(
        default=None, description="Two-letter state code, for state-law notes."
    )

    @field_validator("facility_type")
    @classmethod
    def _known_facility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _FACILITIES:
            raise ValueError(
                f"Unknown facility_type '{v}'. Expected one of: "
                + ", ".join(sorted(_FACILITIES))
            )
        return v

    @field_validator("specialty")
    @classmethod
    def _known_specialty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _SPECIALTIES:
            raise ValueError(
                f"Unknown specialty '{v}'. Expected one of: "
                + ", ".join(sorted(_SPECIALTIES))
            )
        return v

    @field_validator("state")
    @classmethod
    def _valid_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("state must be a two-letter code, e.g. 'TX'")
        return v

    @field_validator("billed_amount", "gfe_amount", "in_network_cost_share")
    @classmethod
    def _plausible_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v > 10_000_000:
            raise ValueError("Amount looks implausible; check the figure.")
        return v


class FiredRule(BaseModel):
    """One rule that contributed to the determination."""

    id: str
    title: str
    citation: str
    summary: str


class Counterfactual(BaseModel):
    """What single change would flip the outcome."""

    change: str
    would_become: str


class Assessment(BaseModel):
    """Full determination with its reasoning trace."""

    outcome: Protection
    headline: str
    explanation: str
    fired_rules: list[FiredRule]
    counterfactuals: list[Counterfactual] = []
    estimated_balance_bill: Optional[float] = None
    cost_sharing_note: Optional[str] = None
    next_steps: list[str] = []
    deadline_days: Optional[int] = None
    missing_facts: list[str] = []
    state_note: Optional[str] = None


class LetterRequest(BaseModel):
    """Inputs for generating a dispute letter."""

    scenario: BillScenario
    patient_name: str = Field(min_length=1, max_length=120)
    provider_name: str = Field(min_length=1, max_length=200)
    account_number: Optional[str] = Field(default=None, max_length=80)
    service_date: Optional[str] = Field(default=None, max_length=40)
