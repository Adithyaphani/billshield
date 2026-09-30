# BillShield

**Check whether a medical bill is legal under the federal No Surprises Act — and get the letter to dispute it.**

Category: `#social-good` (Health) · Lane: `#community`

Live app: `https://chen-includes-toilet-values.trycloudflare.com`

---

## The problem

The No Surprises Act took effect in January 2022. It bans balance billing
outright in a defined set of situations: emergency care, out-of-network
clinicians working inside in-network facilities, and air ambulance transport.
For uninsured and self-pay patients it also creates a dispute right when a
bill lands $400 or more above the written estimate.

The protections are real. The awareness is not. People receive a bill that
federal law says they do not owe, assume the number on the page is the number
they owe, and pay it — or let it go to collections.

The gap is not legal, it is informational. That is a software problem.

## What it does

Answer a short branching questionnaire about a bill. BillShield returns:

- **A determination** — protected, outside federal law, waived, or disputable.
- **The rules that produced it**, each with its statutory citation, so the
  reasoning can be checked rather than trusted.
- **The counterfactual** — the one fact that would have flipped the answer.
- **The amount in question**, computed from what was billed against the lawful
  in-network cost share.
- **A dispute letter as a PDF**, written to match that determination and
  citing the same provisions.

## Why the decision path has no model in it

Every determination comes from a fixed rule corpus in
[`app/rules/corpus.py`](app/rules/corpus.py), evaluated by pure functions in
[`app/rules/engine.py`](app/rules/engine.py). There is no inference anywhere
in the decision path.

That is the core design commitment. Someone deciding whether to pay a
four-figure bill needs to see *why*. A generated paragraph that sounds
confident is worse than useless here — it is the same failure mode that got
them the bill. So `GET /api/v1/rules` returns the entire corpus, and every
assessment names the rule IDs that fired. If BillShield is wrong, it is wrong
in a way you can point at.

It also means identical facts always yield an identical answer. There is a
test for exactly that (`test_same_scenario_is_deterministic`).

The same principle governs what it does when it doesn't know. A typo'd
specialty, an unrecognised facility, or a signed waiver with no timing given
produce a rejection or a request for the missing fact — never a confident
guess. Silent guessing was a real bug found in review, and the regression
tests pin it shut.

## Scope, honestly stated

BillShield covers **federal** law. It does not know your state's statutes, it
cannot see your paperwork, and it is not legal advice. The interface says so
rather than burying it.

The most useful thing it tells many users is where the law *stops*. Ground
ambulance is the single most common surprise bill in the United States and
Congress left it out of the Act entirely. BillShield says so plainly, names it
as a statutory gap, and points to state law instead of pretending to help.

## Design

The interface is built as a billing document rather than a dashboard, because
that is the world the user is already in — statements, explanations of
benefits, carbon-copy claim forms, stamps.

- **Ground** is cool grey form stock with white document panels and blue-black
  document ink.
- **Type** is the IBM Plex superfamily: Serif for verdicts, which read as legal
  determinations; Sans for interface; Mono for citations and currency, where
  it is semantic rather than decorative.
- **The hero** is a rendered specimen statement with the unlawful line stamped,
  instead of a headline and a row of statistics.
- **The form** is a numbered claim intake with ruled underline fields. The
  numbering earns its place because the intake genuinely is a sequence.
- **The result** is a determination notice with a stamped outcome seal. That
  stamp is the one loud element; everything around it stays quiet.

Responsive to phone width, visible keyboard focus, and `prefers-reduced-motion`
respected.

## API

| Method | Route | Purpose |
|---|---|---|
| `GET`  | `/api/v1/health`    | Health check (App Runner probes this) |
| `POST` | `/api/v1/assess`    | Evaluate a bill scenario |
| `GET`  | `/api/v1/rules`     | Full rule corpus with citations |
| `GET`  | `/api/v1/scenarios` | Worked examples |
| `GET`  | `/api/v1/stats`     | Aggregate counts (see caveat below) |
| `POST` | `/api/v1/letter`    | Generate dispute letter (PDF) |

Interactive documentation at `/docs`.

```bash
curl -X POST https://<your-url>/api/v1/assess \
  -H 'Content-Type: application/json' \
  -d '{"care_type":"scheduled","facility_type":"hospital",
       "facility_in_network":true,"provider_in_network":false,
       "specialty":"anesthesiology","billed_amount":2150,
       "in_network_cost_share":300}'
```

Returns `protected`, with `IN_NETWORK_FACILITY` and `ANCILLARY_NO_WAIVER`
fired and an amount in question of `1850.00`.

## Frontend/backend contract

The browser builds its request by hand in `static/app.js` and its form by hand
in `static/index.html`. Nothing in the type system connects those to the
pydantic schema, so a rename on either side would silently drop a field and
change a verdict.

[`tests/test_contract.py`](tests/test_contract.py) closes that gap. It reads
the actual static files and checks them against the live schema and the live
API:

- every `name=` on a form control exists on `BillScenario`
- every key `app.js` assigns onto the request object exists on the schema
- every endpoint `app.js` calls exists on the router
- the `care_type` and `coverage` options rendered in HTML match the `Literal`
  types exactly
- the dropdown vocabularies are served by the backend, never hardcoded in the
  frontend
- every sample case round-trips through the real API and produces a real PDF
- every field the renderer reads is present on every response
- `app.js` has a display label for every member of the `Protection` enum

These were verified to fail by deliberately introducing three kinds of drift
(a camelCase field rename in the JS, a renamed form field in the HTML, and a
renamed backend route) and confirming each one breaks the suite. The first
attempt at the JS check did *not* catch a camelCase rename — its pattern was
lowercase-only — which is why the verification step exists at all.

## Architecture

```
Browser (vanilla JS, no build step)
   |  fetch() -> /api/v1/*
FastAPI (Python 3.11)
   |-- rules/corpus.py    statutory rules + citations
   |-- rules/engine.py    deterministic evaluation
   |-- letter.py          ReportLab PDF generation
   +-- static/            frontend, served by the same process
   |
Docker -> Amazon ECR -> AWS App Runner (public HTTPS)
```

One container, one service. App Runner terminates TLS and provides the public
URL; the health check path keeps deployments honest.

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.api:app --reload --port 8080
# http://localhost:8080
```

## Tests

```bash
python -m pytest tests/ -q
```

62 tests in two suites:

- **`test_engine.py`** — every statutory branch, the consent timing windows
  (72 hours normally, 3 hours same-day), every ancillary specialty's
  resistance to waiver, the $400 threshold at its boundary, balance
  arithmetic, determinism, and regressions for four bugs found in review.
- **`test_contract.py`** — the frontend/backend alignment described above.

## Deploying

```bash
./deploy/ship.sh us-east-1
```

Creates the ECR repository, builds and pushes the image, creates the IAM role
App Runner needs, creates or updates the service, waits for `RUNNING`, and
prints the live URL.

## Known limitations

Worth stating rather than discovering later:

- **`/api/v1/stats` is per-instance and in-memory.** It resets on redeploy and
  would report inconsistent numbers if App Runner scales past one instance.
  It is not surfaced in the UI for that reason. Backing it with DynamoDB is
  the fix.
- **No rate limiting.** Fine for a demo, not for sustained public traffic.
- **No structured logging or tracing.** CloudWatch gets stdout only.
- **Federal law only.** The ground ambulance state list is a small hardcoded
  set, not a maintained state-law database.

---

## Development process

<!--
  TODO before submitting — the hackathon requires you to show your process
  and document the agent/AWS connection. Fill in:

  1. Screenshot of your coding agent connected to the AWS console.
  2. Which agent, and what it actually did vs. what you decided.
  3. The live App Runner URL, pasted at the top of this README.
  4. The result of checking the rule corpus against the actual CFR text.
-->

**Agent used:** _<fill in>_
**Connection proof:** _<screenshot path>_

**Division of labour.** The agent scaffolded the FastAPI service, the
deterministic engine, the PDF generation, the interface and the deployment
script. The statutory content was reviewed against the source regulations
before shipping — an agent is a reasonable way to draft a rule corpus and a
poor way to be sure it is right, so every citation in `corpus.py` was checked
by hand.

**What review actually found.** Probing the first build surfaced four real
defects, one of them a shipping blocker: an unescaped ampersand in a hospital
name crashed the PDF endpoint with a 500, so any patient at "Barnes & Jewish"
would have hit a dead end. Two others were worse in kind than in severity — a
typo'd specialty and an unknown facility type both produced confident
verdicts from input the engine did not understand, which directly contradicts
the project's whole premise. All four are fixed and pinned by regression
tests.

The first interface was also rebuilt. It was a generic dark dashboard that
could have belonged to any product; the current one is drawn from the
document world the user is already in.

**Verification before deploy.** Tests were written alongside the engine rather
than after it, and run green before the API was built on top. Endpoints were
exercised end to end locally, including real PDF byte output, before any AWS
resources were created. The contract tests were themselves verified by
deliberately breaking the frontend three ways.

---

## Licence

MIT.

## Disclaimer

General information about federal law, not legal advice. Verify the citations
and consult a qualified professional before acting on a significant bill.
Free federal help: No Surprises Help Desk, 1-800-985-3059.
