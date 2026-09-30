"""
Deterministic evaluation of a bill scenario against the NSA rule corpus.

Design rule: this module contains no model calls and no randomness. The
same scenario always produces the same assessment, and every assessment
names the rules that produced it.
"""

from app.models import Assessment, BillScenario, Counterfactual, FiredRule
from app.rules.corpus import (
    ANCILLARY_SPECIALTIES,
    CMS_COMPLAINT,
    COST_SHARING_NOTE,
    COVERED_FACILITIES,
    GFE_THRESHOLD_USD,
    PPDR_DEADLINE_DAYS,
    RULES,
    Protection,
)

# States with their own ground ambulance balance-billing protections.
GROUND_AMBULANCE_STATES = {
    "CO", "DE", "FL", "IL", "LA", "MD", "ME", "NY", "OH", "VT", "WV",
}


def _fired(rule_id: str) -> FiredRule:
    r = RULES[rule_id]
    return FiredRule(
        id=r.id, title=r.title, citation=r.citation, summary=r.summary
    )


def _balance_bill(s: BillScenario) -> float | None:
    """Amount billed above the lawful in-network cost share."""
    if s.billed_amount is None or s.in_network_cost_share is None:
        return None
    return round(max(0.0, s.billed_amount - s.in_network_cost_share), 2)


def _consent_is_valid(s: BillScenario) -> bool:
    """45 CFR 149.420(e): 72 hours normally, 3 hours if booked same-day."""
    if not s.signed_consent or s.consent_hours_before is None:
        return False
    required = 3.0 if s.same_day_scheduled else 72.0
    return s.consent_hours_before >= required


def _state_note(s: BillScenario) -> str | None:
    if s.care_type == "ground_ambulance" and s.state:
        code = s.state.upper()
        if code in GROUND_AMBULANCE_STATES:
            return (
                f"{code} has its own ground ambulance balance-billing law. "
                "The federal act does not help here, but your state one may. "
                "Contact your state insurance department."
            )
        return (
            f"{code} is not in our list of states with ground ambulance "
            "protections, though state laws change. Your state insurance "
            "department can confirm."
        )
    return None


def _evaluate_gfe(s: BillScenario) -> Assessment:
    """Uninsured / self-pay path: Good Faith Estimate and PPDR."""
    missing: list[str] = []

    if s.gfe_provided is False:
        return Assessment(
            outcome=Protection.GFE_DISPUTE,
            headline="No Good Faith Estimate was provided",
            explanation=(
                "Providers are required to give uninsured and self-pay "
                "patients a written Good Faith Estimate before scheduled "
                "care. Not receiving one is a compliance failure you can "
                "raise directly with the provider and with CMS."
            ),
            fired_rules=[_fired("GFE_NOT_PROVIDED")],
            next_steps=[
                "Ask the provider in writing for the Good Faith Estimate "
                "that should have been issued.",
                f"Report the failure to the {CMS_COMPLAINT['name']} at "
                f"{CMS_COMPLAINT['phone']}.",
                "Ask the provider's billing office for an itemised bill.",
            ],
        )

    if s.gfe_amount is None or s.billed_amount is None:
        if s.gfe_amount is None:
            missing.append("The Good Faith Estimate amount")
        if s.billed_amount is None:
            missing.append("The amount you were actually billed")
        return Assessment(
            outcome=Protection.NEEDS_INFO,
            headline="A couple more numbers are needed",
            explanation=(
                "The dispute route for self-pay patients turns on the gap "
                "between the estimate and the final bill."
            ),
            fired_rules=[],
            missing_facts=missing,
        )

    gap = round(s.billed_amount - s.gfe_amount, 2)

    if gap >= GFE_THRESHOLD_USD:
        return Assessment(
            outcome=Protection.GFE_DISPUTE,
            headline=f"Your bill is ${gap:,.2f} above the estimate",
            explanation=(
                f"That gap is at or above the ${GFE_THRESHOLD_USD} threshold, "
                "so you are eligible to start federal Patient-Provider "
                "Dispute Resolution. An independent reviewer then decides "
                "what you owe. The filing fee is nominal and the provider "
                "cannot move the bill to collections while the dispute is "
                "pending."
            ),
            fired_rules=[_fired("GFE_400_THRESHOLD")],
            estimated_balance_bill=gap,
            deadline_days=PPDR_DEADLINE_DAYS,
            next_steps=[
                f"Start dispute resolution within {PPDR_DEADLINE_DAYS} days "
                "of receiving the bill.",
                "Gather the Good Faith Estimate, the itemised bill and any "
                "written communication about price.",
                f"Call the {CMS_COMPLAINT['name']} at "
                f"{CMS_COMPLAINT['phone']} to begin.",
            ],
            counterfactuals=[
                Counterfactual(
                    change=(
                        f"If the gap were under ${GFE_THRESHOLD_USD}"
                    ),
                    would_become="Not eligible for federal dispute resolution",
                )
            ],
        )

    return Assessment(
        outcome=Protection.NOT_PROTECTED,
        headline="The bill is within the estimate tolerance",
        explanation=(
            f"Your bill is ${gap:,.2f} above the Good Faith Estimate, which "
            f"is under the ${GFE_THRESHOLD_USD} threshold for federal dispute "
            "resolution. You can still negotiate directly, ask for an "
            "itemised bill, and request financial assistance."
        ),
        fired_rules=[_fired("GFE_UNDER_THRESHOLD")],
        estimated_balance_bill=gap if gap > 0 else None,
        next_steps=[
            "Request a fully itemised bill and check it for errors.",
            "Ask the provider about financial assistance or charity care.",
            "Ask whether a prompt-payment discount is available.",
        ],
    )


def assess(s: BillScenario) -> Assessment:
    """Run the corpus against one scenario."""

    if s.coverage == "uninsured_self_pay":
        result = _evaluate_gfe(s)
        result.state_note = _state_note(s)
        return result

    balance = _balance_bill(s)
    note = _state_note(s)

    # --- Ambulance ---------------------------------------------------------
    if s.care_type == "air_ambulance":
        return Assessment(
            outcome=Protection.PROTECTED,
            headline="This air ambulance bill is protected",
            explanation=(
                "Out-of-network air ambulance transport is covered by the "
                "federal act. You owe only your in-network cost sharing, and "
                "that amount must count toward your in-network deductible "
                "and out-of-pocket maximum."
            ),
            fired_rules=[_fired("AIR_AMBULANCE")],
            estimated_balance_bill=balance,
            cost_sharing_note=COST_SHARING_NOTE,
            next_steps=[
                "Send the provider a written notice disputing the balance.",
                "Ask your plan to reprocess at in-network cost sharing.",
                f"Escalate to the {CMS_COMPLAINT['name']} at "
                f"{CMS_COMPLAINT['phone']} if billing continues.",
            ],
            counterfactuals=[
                Counterfactual(
                    change="If this had been a ground ambulance",
                    would_become="Not protected under federal law",
                )
            ],
            state_note=note,
        )

    if s.care_type == "ground_ambulance":
        return Assessment(
            outcome=Protection.NOT_PROTECTED,
            headline="Ground ambulance sits in a gap in the federal law",
            explanation=(
                "Congress covered air ambulance but left ground ambulance "
                "out of the No Surprises Act. This is the single most common "
                "surprise bill that the federal law does not reach. A growing "
                "number of states have passed their own protections."
            ),
            fired_rules=[_fired("GROUND_AMBULANCE_GAP")],
            estimated_balance_bill=balance,
            next_steps=[
                "Check your state's ground ambulance law with the state "
                "insurance department.",
                "Request an itemised bill and check mileage and level of "
                "service against what was actually provided.",
                "Ask the ambulance service about a hardship reduction.",
            ],
            counterfactuals=[
                Counterfactual(
                    change="If this had been an air ambulance",
                    would_become="Protected under federal law",
                )
            ],
            state_note=note,
        )

    # --- Emergency ---------------------------------------------------------
    if s.care_type == "emergency":
        return Assessment(
            outcome=Protection.PROTECTED,
            headline="Emergency care is protected",
            explanation=(
                "Emergency services are protected no matter whether the "
                "hospital or the treating clinicians were in your network, "
                "and no matter whether prior authorisation was obtained. A "
                "signed consent form does not change this."
            ),
            fired_rules=[_fired("EMERGENCY")],
            estimated_balance_bill=balance,
            cost_sharing_note=COST_SHARING_NOTE,
            next_steps=[
                "Do not pay the balance-billed portion while you dispute it.",
                "Send the provider written notice that the service was "
                "protected emergency care.",
                "Ask your plan to reprocess at in-network cost sharing.",
                f"Escalate to the {CMS_COMPLAINT['name']} at "
                f"{CMS_COMPLAINT['phone']} if the provider persists.",
            ],
            state_note=note,
        )

    if s.care_type == "post_stabilization":
        if _consent_is_valid(s):
            return Assessment(
                outcome=Protection.WAIVED,
                headline="Post-stabilisation protection appears waived",
                explanation=(
                    "Care after stabilisation normally stays protected until "
                    "you could safely be moved. That protection can be waived "
                    "by valid written notice and consent, and the timing you "
                    "described meets the requirement."
                ),
                fired_rules=[_fired("VALID_WAIVER")],
                estimated_balance_bill=balance,
                next_steps=[
                    "Request a copy of the signed consent form and check it "
                    "against the standard federal notice.",
                    "Confirm you were medically stable and able to travel by "
                    "non-medical transport at the time you signed.",
                ],
                counterfactuals=[
                    Counterfactual(
                        change="If you were not yet safe to travel when you "
                        "signed",
                        would_become="Protected, because consent was invalid",
                    )
                ],
                state_note=note,
            )
        return Assessment(
            outcome=Protection.PROTECTED,
            headline="Post-stabilisation care is protected",
            explanation=(
                "Protection continues after stabilisation until you can "
                "safely travel by ordinary transport. Without valid written "
                "notice and consent, the provider cannot balance bill you "
                "for that period."
            ),
            fired_rules=[_fired("POST_STABILIZATION")],
            estimated_balance_bill=balance,
            cost_sharing_note=COST_SHARING_NOTE,
            next_steps=[
                "Send written notice disputing the balance.",
                "Ask the provider to produce any consent form they rely on.",
                f"Escalate to the {CMS_COMPLAINT['name']} at "
                f"{CMS_COMPLAINT['phone']}.",
            ],
            state_note=note,
        )

    # --- Scheduled, non-emergency ------------------------------------------
    missing: list[str] = []
    if s.facility_in_network is None:
        missing.append("Whether the facility was in your network")
    if s.provider_in_network is None:
        missing.append("Whether the treating provider was in your network")
    if missing:
        return Assessment(
            outcome=Protection.NEEDS_INFO,
            headline="A few more facts are needed",
            explanation=(
                "For scheduled care, protection turns on the network status "
                "of the facility and of the individual provider. Your "
                "insurer's explanation of benefits usually shows both."
            ),
            fired_rules=[],
            missing_facts=missing,
        )

    if s.provider_in_network:
        return Assessment(
            outcome=Protection.NOT_PROTECTED,
            headline="An in-network provider billed you",
            explanation=(
                "The balance-billing protections address out-of-network "
                "providers. When the provider is in network, what you owe is "
                "governed by your plan's contract instead. A bill that looks "
                "too high is more likely a coding or processing error."
            ),
            fired_rules=[],
            estimated_balance_bill=balance,
            next_steps=[
                "Compare the bill line by line against your explanation of "
                "benefits.",
                "Ask your plan why the amount differs from the contracted "
                "rate.",
                "Request an itemised bill and check for duplicate charges.",
            ],
        )

    if not s.facility_in_network:
        return Assessment(
            outcome=Protection.NOT_PROTECTED,
            headline="Out-of-network care at an out-of-network facility",
            explanation=(
                "The federal protection covers an out-of-network provider "
                "working inside an in-network facility. When you chose an "
                "out-of-network facility for scheduled care, that protection "
                "does not attach."
            ),
            fired_rules=[_fired("OUT_OF_NETWORK_FACILITY")],
            estimated_balance_bill=balance,
            next_steps=[
                "Ask your plan whether any network-gap exception applies.",
                "Negotiate directly, and ask for the self-pay rate.",
                "Ask about financial assistance.",
            ],
            counterfactuals=[
                Counterfactual(
                    change="If the facility had been in network",
                    would_become="Protected from balance billing",
                )
            ],
        )

    if s.facility_type and s.facility_type not in COVERED_FACILITIES:
        return Assessment(
            outcome=Protection.NOT_PROTECTED,
            headline="This facility type is outside the definition",
            explanation=(
                "The protection applies at hospitals, hospital outpatient "
                "departments, ambulatory surgical centers and critical "
                "access hospitals. Urgent care clinics, physician offices "
                "and freestanding imaging centers are not included unless "
                "the visit was genuinely emergency care."
            ),
            fired_rules=[_fired("UNCOVERED_FACILITY_TYPE")],
            estimated_balance_bill=balance,
            next_steps=[
                "If the visit was for an emergency, re-run this as emergency "
                "care, because the facility type stops mattering.",
                "Check whether your state law reaches this setting.",
                "Negotiate directly with the provider.",
            ],
            counterfactuals=[
                Counterfactual(
                    change="If this had been at a hospital or surgical center",
                    would_become="Protected from balance billing",
                )
            ],
        )

    # Out-of-network provider inside a covered in-network facility.
    is_ancillary = s.specialty in ANCILLARY_SPECIALTIES

    if is_ancillary:
        rules = [_fired("IN_NETWORK_FACILITY"), _fired("ANCILLARY_NO_WAIVER")]
        extra = ""
        if s.signed_consent:
            extra = (
                " You signed a consent form, but for this specialty the "
                "provider was not permitted to ask, so the form is void."
            )
        return Assessment(
            outcome=Protection.PROTECTED,
            headline="Protected, and the protection cannot be waived",
            explanation=(
                "An out-of-network provider treated you at an in-network "
                f"facility, and {ANCILLARY_SPECIALTIES[s.specialty].lower()} "
                "is an ancillary specialty. Providers in these specialties "
                "are barred from asking patients to waive protection, because "
                "patients do not realistically get to choose them." + extra
            ),
            fired_rules=rules,
            estimated_balance_bill=balance,
            cost_sharing_note=COST_SHARING_NOTE,
            next_steps=[
                "Send written notice disputing the balance and citing the "
                "ancillary-services rule.",
                "Ask your plan to reprocess at in-network cost sharing.",
                f"Escalate to the {CMS_COMPLAINT['name']} at "
                f"{CMS_COMPLAINT['phone']} if billing continues.",
            ],
        )

    if s.signed_consent and s.consent_hours_before is None:
        return Assessment(
            outcome=Protection.NEEDS_INFO,
            headline="When did you get that consent form?",
            explanation=(
                "You signed a waiver, and whether it counts turns entirely on "
                "timing. The form must reach you at least 72 hours before a "
                "scheduled appointment, or at least 3 hours before service if "
                "you booked the same day. Without that detail this could go "
                "either way, so no verdict is given."
            ),
            fired_rules=[],
            missing_facts=[
                "How many hours before the service you received the consent "
                "form",
            ],
        )

    if _consent_is_valid(s):
        return Assessment(
            outcome=Protection.WAIVED,
            headline="You appear to have waived the protection",
            explanation=(
                "You would normally be protected here. Because this is not "
                "an ancillary specialty, the provider was allowed to ask you "
                "to waive protection, and the timing you described meets the "
                "notice requirement. It is still worth checking the form "
                "itself against the standard federal notice."
            ),
            fired_rules=[_fired("IN_NETWORK_FACILITY"), _fired("VALID_WAIVER")],
            estimated_balance_bill=balance,
            next_steps=[
                "Request a copy of the signed notice and consent form.",
                "Check that it used the standard federal form, named the "
                "provider, and gave a good-faith cost estimate.",
                "If any element was missing, the waiver may be invalid.",
            ],
            counterfactuals=[
                Counterfactual(
                    change="If the form had arrived under 72 hours before",
                    would_become="Protected, because consent was late",
                ),
                Counterfactual(
                    change="If the specialty had been ancillary",
                    would_become="Protected, because consent is not allowed",
                ),
            ],
        )

    rules = [_fired("IN_NETWORK_FACILITY")]
    if s.signed_consent:
        rules.append(_fired("DEFECTIVE_WAIVER_TIMING"))
        why = (
            "You signed a consent form, but it came too late to count. The "
            "form must arrive at least 72 hours before a scheduled "
            "appointment, or at least 3 hours before service if you booked "
            "the same day."
        )
    else:
        why = (
            "No valid written notice and consent was obtained, so nothing "
            "waived your protection."
        )

    return Assessment(
        outcome=Protection.PROTECTED,
        headline="This bill is protected",
        explanation=(
            "An out-of-network provider treated you at an in-network "
            f"facility. {why}"
        ),
        fired_rules=rules,
        estimated_balance_bill=balance,
        cost_sharing_note=COST_SHARING_NOTE,
        next_steps=[
            "Send the provider written notice disputing the balance.",
            "Ask your plan to reprocess at in-network cost sharing.",
            "Keep every letter and note every call.",
            f"Escalate to the {CMS_COMPLAINT['name']} at "
            f"{CMS_COMPLAINT['phone']} if billing continues.",
        ],
    )
