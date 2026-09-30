"""Worked examples, each hitting a different branch of the rule corpus."""

SAMPLE_SCENARIOS = [
    {
        "id": "er_out_of_network",
        "title": "Emergency room, out-of-network hospital",
        "story": (
            "Ambulance took you to the nearest ER after a fall. The hospital "
            "was not in your network. The bill is $8,420 above what your plan "
            "paid."
        ),
        "scenario": {
            "care_type": "emergency",
            "coverage": "insured",
            "facility_type": "hospital",
            "facility_in_network": False,
            "provider_in_network": False,
            "billed_amount": 8420.50,
            "in_network_cost_share": 1200.00,
        },
    },
    {
        "id": "anesthesia_surprise",
        "title": "In-network surgery, out-of-network anaesthetist",
        "story": (
            "You checked that the hospital and surgeon were in network. The "
            "anaesthetist was not, and billed you $2,150 separately."
        ),
        "scenario": {
            "care_type": "scheduled",
            "coverage": "insured",
            "facility_type": "hospital",
            "facility_in_network": True,
            "provider_in_network": False,
            "specialty": "anesthesiology",
            "billed_amount": 2150.00,
            "in_network_cost_share": 300.00,
        },
    },
    {
        "id": "late_consent",
        "title": "Consent form handed over on the morning of surgery",
        "story": (
            "An out-of-network surgeon at your in-network hospital asked you "
            "to sign a waiver two hours before the operation."
        ),
        "scenario": {
            "care_type": "scheduled",
            "coverage": "insured",
            "facility_type": "hospital",
            "facility_in_network": True,
            "provider_in_network": False,
            "specialty": "surgery",
            "signed_consent": True,
            "consent_hours_before": 2,
            "same_day_scheduled": False,
            "billed_amount": 6800.00,
            "in_network_cost_share": 900.00,
        },
    },
    {
        "id": "ground_ambulance",
        "title": "Ground ambulance ride",
        "story": (
            "A 12-mile ambulance ride produced a $1,900 bill. Your plan paid "
            "$400 and the company is billing you for the rest."
        ),
        "scenario": {
            "care_type": "ground_ambulance",
            "coverage": "insured",
            "state": "TX",
            "billed_amount": 1900.00,
            "in_network_cost_share": 400.00,
        },
    },
    {
        "id": "self_pay_gfe",
        "title": "Self-pay patient billed well above the estimate",
        "story": (
            "You have no insurance. The clinic estimated $1,800 for a "
            "procedure and then billed you $3,450."
        ),
        "scenario": {
            "care_type": "scheduled",
            "coverage": "uninsured_self_pay",
            "gfe_provided": True,
            "gfe_amount": 1800.00,
            "billed_amount": 3450.00,
        },
    },
    {
        "id": "urgent_care",
        "title": "Urgent care clinic, out-of-network doctor",
        "story": (
            "You went to an in-network urgent care clinic but the doctor on "
            "duty was out of network."
        ),
        "scenario": {
            "care_type": "scheduled",
            "coverage": "insured",
            "facility_type": "urgent_care",
            "facility_in_network": True,
            "provider_in_network": False,
            "specialty": "other",
            "billed_amount": 640.00,
            "in_network_cost_share": 75.00,
        },
    },
]
