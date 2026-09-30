"""
Frontend/backend contract.

The browser builds its request by hand in static/app.js and its form by hand
in static/index.html. Nothing in the type system connects those to the
pydantic schema, so a rename on either side would silently drop a field and
change a verdict. These tests close that gap: they read the actual static
files and check them against the live schema and the live API.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.models import BillScenario, LetterRequest
from app.rules.corpus import (
    ANCILLARY_SPECIALTIES,
    COVERED_FACILITIES,
    NON_COVERED_FACILITIES,
    WAIVABLE_SPECIALTIES,
)
from app.scenarios import SAMPLE_SCENARIOS

STATIC = Path(__file__).parent.parent / "static"
HTML = (STATIC / "index.html").read_text()
JS = (STATIC / "app.js").read_text()

client = TestClient(app)


def form_field_names() -> set[str]:
    """Every name= attribute on an actual form control.

    Scoped to <input> and <select> so <meta name="viewport"> and friends
    don't get mistaken for posted fields.
    """
    controls = re.findall(r"<(?:input|select)\b[^>]*>", HTML)
    names = set()
    for tag in controls:
        m = re.search(r'name="([a-z_]+)"', tag)
        if m:
            names.add(m.group(1))
    return names


# --- Schema alignment ------------------------------------------------------

def test_every_form_field_exists_on_the_schema():
    known = set(BillScenario.model_fields)
    unknown = form_field_names() - known
    assert not unknown, (
        f"index.html posts field(s) the backend does not accept: {unknown}"
    )


def test_every_scenario_field_the_js_sets_exists_on_the_schema():
    """Catches keys assigned onto the request object in collect()."""
    assigned = set(re.findall(r"^\s*s\.([A-Za-z_][A-Za-z0-9_]*)\s*=", JS, re.M))
    unknown = assigned - set(BillScenario.model_fields)
    assert not unknown, f"app.js sends unknown field(s): {unknown}"


def test_letter_request_fields_match_the_js_payload():
    sent = set(re.findall(r"^\s*([a-z_]+):\s*[$\w]", JS, re.M))
    letter_fields = set(LetterRequest.model_fields)
    used = sent & letter_fields
    assert {"patient_name", "provider_name"} <= used
    assert not (used - letter_fields)


# --- Endpoint alignment ----------------------------------------------------

def test_every_endpoint_the_js_calls_actually_exists():
    called = set(re.findall(r"\$\{API\}/([a-z]+)", JS))
    routes = {r.path for r in app.routes}
    for name in called:
        assert f"/api/v1/{name}" in routes, f"app.js calls missing /{name}"


def test_api_prefix_matches_the_backend():
    declared = re.search(r"const API\s*=\s*'([^']+)'", JS).group(1)
    assert declared == "/api/v1"


# --- Vocabulary alignment --------------------------------------------------

def test_dropdown_vocabularies_come_from_the_backend():
    """The frontend must not hardcode its own copy of these lists."""
    payload = client.get("/api/v1/rules").json()
    assert set(payload["covered_facilities"]) == set(COVERED_FACILITIES)
    assert set(payload["non_covered_facilities"]) == set(NON_COVERED_FACILITIES)
    assert set(payload["ancillary_specialties"]) == set(ANCILLARY_SPECIALTIES)
    assert set(payload["waivable_specialties"]) == set(WAIVABLE_SPECIALTIES)


def test_care_type_options_match_the_literal():
    rendered = set(re.findall(r'name="care_type" value="([a-z_]+)"', HTML))
    allowed = set(
        BillScenario.model_fields["care_type"].annotation.__args__
    )
    assert rendered == allowed


def test_coverage_options_match_the_literal():
    rendered = set(re.findall(r'name="coverage" value="([a-z_]+)"', HTML))
    allowed = set(BillScenario.model_fields["coverage"].annotation.__args__)
    assert rendered == allowed


# --- Every sample case round-trips through the real API -------------------

@pytest.mark.parametrize("case", SAMPLE_SCENARIOS, ids=lambda c: c["id"])
def test_sample_case_is_accepted_and_answered(case):
    res = client.post("/api/v1/assess", json=case["scenario"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outcome"] != "needs_info", (
        f"sample case '{case['id']}' should be complete enough to answer"
    )
    assert body["headline"] and body["explanation"]


@pytest.mark.parametrize("case", SAMPLE_SCENARIOS, ids=lambda c: c["id"])
def test_sample_case_produces_a_letter(case):
    res = client.post("/api/v1/letter", json={
        "scenario": case["scenario"],
        "patient_name": "Test Patient",
        "provider_name": "Example Health & Co <Main>",
    })
    assert res.status_code == 200, res.text
    assert res.content.startswith(b"%PDF")


# --- Response shape the renderer depends on -------------------------------

def test_assessment_always_carries_the_keys_the_renderer_reads():
    needed = {
        "outcome", "headline", "explanation", "fired_rules",
        "counterfactuals", "estimated_balance_bill", "cost_sharing_note",
        "next_steps", "deadline_days", "missing_facts", "state_note",
    }
    for case in SAMPLE_SCENARIOS:
        body = client.post("/api/v1/assess", json=case["scenario"]).json()
        assert needed <= set(body), f"missing {needed - set(body)}"


def test_outcome_labels_in_js_cover_every_possible_outcome():
    labelled = set(re.findall(r"^\s+([a-z_]+):\s*'", JS, re.M))
    from app.rules.corpus import Protection
    for p in Protection:
        assert p.value in labelled, f"app.js has no label for '{p.value}'"


# --- Static assets are actually served ------------------------------------

@pytest.mark.parametrize("path,kind", [
    ("/", "text/html"),
    ("/styles.css", "text/css"),
    ("/app.js", "javascript"),
])
def test_static_asset_is_served(path, kind):
    res = client.get(path)
    assert res.status_code == 200
    assert kind in res.headers["content-type"]


def test_health_endpoint_reports_the_corpus():
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["rules_loaded"] > 0
