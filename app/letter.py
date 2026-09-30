"""Generates a dispute letter as a PDF, tailored to the determination."""

import io
from datetime import date, timedelta
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.models import Assessment, LetterRequest
from app.rules.corpus import CMS_COMPLAINT, PPDR_DEADLINE_DAYS, Protection


def _body_for(a: Assessment, req: LetterRequest) -> list[str]:
    """Letter body paragraphs matched to the outcome."""
    citations = ", ".join(r.citation for r in a.fired_rules) or "the No Surprises Act"

    if a.outcome == Protection.GFE_DISPUTE:
        deadline = (date.today() + timedelta(days=PPDR_DEADLINE_DAYS)).strftime(
            "%d %B %Y"
        )
        return [
            "I am writing about the bill referenced above. I am a self-pay "
            "patient and I am disputing the amount billed.",
            "Federal regulations require that I receive a written Good Faith "
            "Estimate before scheduled care, and they give me the right to "
            "dispute a final bill that exceeds that estimate by $400 or more. "
            f"The relevant authority is {citations}.",
            "I am asking you to review this account and provide a fully "
            "itemised bill together with a copy of the Good Faith Estimate "
            "issued to me. I intend to initiate Patient-Provider Dispute "
            f"Resolution, for which my deadline is {deadline}.",
            "Please confirm in writing that this account will not be referred "
            "to collections while the dispute is pending.",
        ]

    if a.outcome == Protection.WAIVED:
        return [
            "I am writing about the bill referenced above and requesting "
            "documentation before I pay any balance-billed amount.",
            "You appear to be relying on a signed notice and consent form to "
            "balance bill me. Federal rules set specific requirements for "
            "that form, including the timing of delivery, the use of the "
            "standard federal notice, identification of the provider, and a "
            "good-faith estimate of cost.",
            "Please provide a copy of the signed form together with evidence "
            "of the date and time it was given to me. If any requirement was "
            "not met, the waiver is not effective and the balance billed is "
            "not owed.",
        ]

    # Protected outcomes.
    amount = (
        f" of ${a.estimated_balance_bill:,.2f}"
        if a.estimated_balance_bill
        else ""
    )
    return [
        "I am writing to dispute the balance billed on the account "
        f"referenced above. I believe the charge{amount} is prohibited by "
        "federal law.",
        f"{a.explanation} The relevant authority is {citations}.",
        "Under these provisions I am responsible only for the in-network "
        "cost sharing for this service, and that amount must be applied to "
        "my in-network deductible and out-of-pocket maximum. I am not "
        "responsible for any amount above it.",
        "I am asking you to correct this account, withdraw the balance "
        "billed, and confirm the correction in writing. Please do not refer "
        "this account to collections while it is disputed.",
        "If this is not resolved I will file a complaint with the "
        f"{CMS_COMPLAINT['name']} at {CMS_COMPLAINT['phone']} and with my "
        "state insurance department.",
    ]


def build_letter(req: LetterRequest, assessment: Assessment) -> bytes:
    """Render the dispute letter to PDF bytes.

    ReportLab parses paragraph text as mini-XML, so every field that came
    from the user is escaped first. An unescaped ampersand or angle bracket
    in a hospital name would otherwise abort the parse.
    """
    patient = escape(req.patient_name)
    provider = escape(req.provider_name)
    account = escape(req.account_number) if req.account_number else None
    svc_date = escape(req.service_date) if req.service_date else None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=1 * inch, rightMargin=1 * inch,
        topMargin=1 * inch, bottomMargin=1 * inch,
        title="Medical bill dispute letter",
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["Normal"], fontSize=10.5, leading=15,
        alignment=TA_JUSTIFY, spaceAfter=10,
    )
    meta = ParagraphStyle(
        "meta", parent=styles["Normal"], fontSize=10.5, leading=14,
    )
    head = ParagraphStyle(
        "head", parent=styles["Normal"], fontSize=11.5, leading=16,
        spaceAfter=14, fontName="Helvetica-Bold",
    )

    flow = [
        Paragraph(date.today().strftime("%d %B %Y"), meta),
        Spacer(1, 18),
        Paragraph(provider, meta),
        Paragraph("Billing Department", meta),
        Spacer(1, 18),
    ]

    ref = []
    if req.account_number:
        ref.append(f"Account: {account}")
    if req.service_date:
        ref.append(f"Date of service: {svc_date}")
    ref.append(f"Patient: {patient}")
    flow.append(Paragraph(" &nbsp;|&nbsp; ".join(ref), meta))
    flow.append(Spacer(1, 18))

    flow.append(Paragraph("Re: Dispute of balance billed", head))
    flow.append(Paragraph("To whom it may concern,", body))

    for para in _body_for(assessment, req):
        flow.append(Paragraph(escape(para), body))

    flow.append(Spacer(1, 10))
    flow.append(Paragraph("I look forward to your written response.", body))
    flow.append(Spacer(1, 22))
    flow.append(Paragraph("Sincerely,", meta))
    flow.append(Spacer(1, 30))
    flow.append(Paragraph(patient, meta))

    flow.append(Spacer(1, 26))
    flow.append(Paragraph(
        "<font size=8 color='#666666'>Prepared with BillShield. This letter "
        "is general information, not legal advice. Review it before sending "
        "and adjust anything that does not match your situation.</font>",
        meta,
    ))

    doc.build(flow)
    return buf.getvalue()
