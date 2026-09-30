"""FastAPI application: assessment, rule transparency, letter generation."""

import os
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.letter import build_letter
from app.models import Assessment, BillScenario, LetterRequest
from app.rules.corpus import (
    ANCILLARY_SPECIALTIES,
    CMS_COMPLAINT,
    COVERED_FACILITIES,
    NON_COVERED_FACILITIES,
    RULES,
    WAIVABLE_SPECIALTIES,
)
from app.rules.engine import assess
from app.scenarios import SAMPLE_SCENARIOS

app = FastAPI(
    title="BillShield API",
    description=(
        "Checks a medical bill against the federal No Surprises Act and "
        "returns a determination with its statutory reasoning."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# In-process counters. Nothing identifying is stored: only the outcome
# label and the care type, so the landing page can show usage.
_counts: Counter = Counter()


@app.get("/api/v1/health")
def health():
    """Health check for the App Runner load balancer."""
    return {"status": "ok", "rules_loaded": len(RULES)}


@app.post("/api/v1/assess", response_model=Assessment)
def run_assessment(scenario: BillScenario):
    """Evaluate one bill scenario."""
    result = assess(scenario)
    _counts[result.outcome.value] += 1
    _counts["total"] += 1
    return result


@app.get("/api/v1/rules")
def list_rules():
    """The full rule corpus, so determinations can be checked."""
    return {
        "rules": [
            {
                "id": r.id,
                "title": r.title,
                "citation": r.citation,
                "summary": r.summary,
                "outcome": r.outcome.value,
            }
            for r in RULES.values()
        ],
        "covered_facilities": COVERED_FACILITIES,
        "non_covered_facilities": NON_COVERED_FACILITIES,
        "ancillary_specialties": ANCILLARY_SPECIALTIES,
        "waivable_specialties": WAIVABLE_SPECIALTIES,
        "help": CMS_COMPLAINT,
    }


@app.get("/api/v1/scenarios")
def list_scenarios():
    """Worked examples that exercise different branches of the corpus."""
    return {"scenarios": SAMPLE_SCENARIOS}


@app.get("/api/v1/stats")
def stats():
    """Anonymous aggregate counts for this instance."""
    return {
        "total_assessments": _counts.get("total", 0),
        "by_outcome": {
            k: v for k, v in _counts.items() if k != "total"
        },
    }


@app.post("/api/v1/letter")
def generate_letter(req: LetterRequest):
    """Produce a dispute letter PDF for the given scenario."""
    result = assess(req.scenario)

    if result.outcome.value == "needs_info":
        raise HTTPException(
            status_code=400,
            detail="Complete the assessment before generating a letter.",
        )

    try:
        pdf = build_letter(req, result)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Could not build letter: {exc}"
        ) from exc

    safe = "".join(
        c for c in req.patient_name if c.isalnum() or c in " -_"
    ).strip().replace(" ", "_") or "dispute"

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe}_dispute.pdf"'
        },
    )


# Static frontend, mounted last so it does not shadow the API routes.
_static = Path(__file__).parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
