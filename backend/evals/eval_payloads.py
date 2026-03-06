from __future__ import annotations

from copy import deepcopy
from typing import Any


def _request(
    *,
    prospect_name: str,
    prospect_title: str,
    prospect_company: str,
    research_text: str,
    offer_lock: str,
    cta_line: str,
    sender_company: str,
    sender_product: str,
    company_notes: str,
    seller_offerings: list[str],
    sender_proof_points: list[str] | None = None,
    preset_id: str = "direct",
    style_profile: dict[str, float] | None = None,
) -> dict[str, Any]:
    style = style_profile or {"formality": 0.1, "orientation": -0.1, "length": -0.3, "assertiveness": 0.2}
    request = {
        "prospect": {
            "name": prospect_name,
            "title": prospect_title,
            "company": prospect_company,
            "company_url": f"https://{prospect_company.lower().replace(' ', '')}.example",
            "linkedin_url": "https://linkedin.com/in/example-prospect",
        },
        "prospect_first_name": prospect_name.split(" ", 1)[0],
        "research_text": research_text,
        "offer_lock": offer_lock,
        "cta_offer_lock": cta_line,
        "cta_type": "question",
        "preset_id": preset_id,
        "response_contract": "email_json_v1",
        "mode": "single",
        "style_profile": style,
        "company_context": {
            "company_name": sender_company,
            "company_url": f"https://{sender_company.lower().replace(' ', '')}.example",
            "current_product": sender_product,
            "seller_offerings": seller_offerings,
            "internal_modules": ["Prospect Enrichment", "Sequence QA"],
            "company_notes": company_notes,
            "cta_offer_lock": cta_line,
            "cta_type": "question",
        },
    }
    if sender_proof_points:
        request["sender_profile_override"] = {
            "company_name": sender_company,
            "proof_points": list(sender_proof_points),
        }
    return request


def _payload(
    payload_id: str,
    payload_type: str,
    description: str,
    expected_behavior: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "payload_id": payload_id,
        "payload_type": payload_type,
        "description": description,
        "expected_behavior": expected_behavior,
        "request": request,
    }


LONG_RESEARCH = " ".join(
    [
        "Astera Grid expanded regional RevOps governance and documented handoff quality standards across SDR, AE, and CS teams."
        for _ in range(60)
    ]
)


PAYLOADS: list[dict[str, Any]] = [
    # TYPE 1: HIGH SIGNAL (5)
    _payload(
        "high_signal_01",
        "high_signal",
        "Clear RevOps initiative plus concrete process metrics.",
        "passes_all_stages",
        _request(
            prospect_name="Jordan Hale",
            prospect_title="VP Revenue Operations",
            prospect_company="Nimbus Forge",
            research_text=(
                "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets, "
                "weekly call QA reviews, and a pipeline consistency objective tied to forecast variance."
            ),
            offer_lock="Outbound Workflow QA",
            cta_line="Open to a quick chat to see if this is relevant?",
            sender_company="Signal Harbor",
            sender_product="Outbound Workflow QA",
            company_notes="Helps RevOps teams tighten outbound execution and forecast reliability.",
            seller_offerings=["Sequence QA scoring", "Handoff health alerts", "Coaching-ready diagnostics"],
        ),
    ),
    _payload(
        "high_signal_02",
        "high_signal",
        "Growth leader with explicit conversion and pipeline consistency goals.",
        "passes_all_stages",
        _request(
            prospect_name="Elena Price",
            prospect_title="Head of Growth",
            prospect_company="Marble Reach",
            research_text=(
                "Marble Reach reported inconsistent outbound messaging across segments and set a Q1 initiative "
                "to standardize first-touch quality for conversion lift."
            ),
            offer_lock="Messaging Consistency Analytics",
            cta_line="Would it be useful to compare notes on tightening first-touch quality this quarter?",
            sender_company="Signal Harbor",
            sender_product="Messaging Consistency Analytics",
            company_notes="Surfaces sequence-level drift and gives managers concrete fixes.",
            seller_offerings=["Messaging variance tracking", "Persona-level quality maps", "Reply-quality diagnostics"],
        ),
    ),
    _payload(
        "high_signal_03",
        "high_signal",
        "Enterprise demand gen team with named workflow rollout.",
        "passes_all_stages",
        _request(
            prospect_name="Mara Singh",
            prospect_title="VP Demand Generation",
            prospect_company="Northline Bio",
            research_text=(
                "Northline Bio rolled out a cross-team outbound workflow standard after seeing handoff rework. "
                "Leadership emphasized measurable execution consistency before scaling volume."
            ),
            offer_lock="Pipeline Hygiene QA",
            cta_line="Open to a 15-minute working session on execution consistency next week?",
            sender_company="Signal Harbor",
            sender_product="Pipeline Hygiene QA",
            company_notes="Supports outbound leaders with measurable quality controls.",
            seller_offerings=["Sequence QA checks", "Forecast-risk flags", "Execution playbook scoring"],
        ),
    ),
    _payload(
        "high_signal_04",
        "high_signal",
        "RevOps director with explicit initiative timing and proof-rich context.",
        "passes_all_stages",
        _request(
            prospect_name="Owen Kim",
            prospect_title="Director of Revenue Operations",
            prospect_company="Cobalt Transit",
            research_text=(
                "Cobalt Transit centralized outbound governance in February 2026 and added monthly diagnostics for "
                "handoff delay and sequence-level message quality."
            ),
            offer_lock="Revenue Workflow Diagnostics",
            cta_line="Would a quick teardown of your current diagnostics framework be helpful?",
            sender_company="Signal Harbor",
            sender_product="Revenue Workflow Diagnostics",
            company_notes="Provides RevOps teams with high-signal quality diagnostics and handoff risk controls.",
            seller_offerings=["Diagnostics scorecards", "Handoff latency alerts", "Quality drift snapshots"],
        ),
    ),
    _payload(
        "high_signal_05",
        "high_signal",
        "Mid-market GTM operations owner with concrete pain and proof points.",
        "passes_all_stages",
        _request(
            prospect_name="Talia Brooks",
            prospect_title="Senior Manager, GTM Operations",
            prospect_company="Harborlight Cloud",
            research_text=(
                "Harborlight Cloud found inconsistent discovery messaging across outbound reps and launched a formal "
                "GTM operations audit to reduce meeting quality variance."
            ),
            offer_lock="Outbound QA Studio",
            cta_line="Open to a short call to compare how you are auditing outbound quality today?",
            sender_company="Signal Harbor",
            sender_product="Outbound QA Studio",
            company_notes="Improves consistency and coaching velocity for GTM ops teams.",
            seller_offerings=["Call-quality benchmarking", "Rep-level drift visibility", "Coaching recommendation engine"],
        ),
    ),
    _payload(
        "seller_proof_rich_01",
        "seller_proof_rich",
        "Grounded RevOps program plus explicit seller proof override for the earned-strong path.",
        "passes_all_stages",
        _request(
            prospect_name="Naomi Voss",
            prospect_title="VP Revenue Operations",
            prospect_company="Pillar Circuit",
            research_text=(
                "Pillar Circuit launched a February 2026 revenue workflow audit covering handoff latency, "
                "message consistency, and manager QA review cadence."
            ),
            offer_lock="Revenue Workflow Diagnostics",
            cta_line="Would a quick comparison of workflow QA approaches be useful?",
            sender_company="Signal Harbor",
            sender_product="Revenue Workflow Diagnostics",
            company_notes="Supports RevOps teams with measurable workflow QA controls and coaching visibility.",
            seller_offerings=["Diagnostics scorecards", "Handoff latency alerts", "Coaching-ready QA reviews"],
            sender_proof_points=[
                "A SaaS RevOps team reduced handoff delays by 18% within six weeks after adding sequence QA reviews.",
                "Another operations team cut manager QA review time by 27% after standardizing workflow diagnostics.",
            ],
        ),
    ),

    # TYPE 2: MEDIUM SIGNAL (5)
    _payload(
        "medium_signal_01",
        "medium_signal",
        "Some role context plus one initiative hint.",
        "proof_gap_expected",
        _request(
            prospect_name="Irene Fox",
            prospect_title="Revenue Enablement Lead",
            prospect_company="Slate Orbit",
            research_text="Slate Orbit is exploring tighter outbound process consistency for new reps.",
            offer_lock="Enablement QA Layer",
            cta_line="Would it be helpful to share a quick framework for outbound consistency checks?",
            sender_company="Signal Harbor",
            sender_product="Enablement QA Layer",
            company_notes="Helps enablement leaders keep outbound messaging consistent.",
            seller_offerings=["Ramp-quality checks", "Manager review dashboards"],
        ),
    ),
    _payload(
        "medium_signal_02",
        "medium_signal",
        "Prospect has role fit but sparse concrete facts.",
        "proof_gap_expected",
        _request(
            prospect_name="Dane Miller",
            prospect_title="Head of Pipeline Operations",
            prospect_company="Nova Claims",
            research_text="Nova Claims has been discussing pipeline quality and outbound process discipline.",
            offer_lock="Pipeline QA Controls",
            cta_line="Open to a quick comparison of your current pipeline QA approach?",
            sender_company="Signal Harbor",
            sender_product="Pipeline QA Controls",
            company_notes="Pipeline-quality tooling for operations teams.",
            seller_offerings=["Handoff checks", "Sequence drift alerts"],
        ),
    ),
    _payload(
        "medium_signal_03",
        "medium_signal",
        "Single research clue with moderate ICP alignment.",
        "proof_gap_expected",
        _request(
            prospect_name="Ava Lin",
            prospect_title="Director, Demand Ops",
            prospect_company="Ridgewell Systems",
            research_text="Ridgewell Systems is revisiting outbound workflows to improve forecast confidence.",
            offer_lock="Forecast Reliability QA",
            cta_line="Would a short discussion on forecast reliability controls be useful?",
            sender_company="Signal Harbor",
            sender_product="Forecast Reliability QA",
            company_notes="Improves consistency signals that affect forecast confidence.",
            seller_offerings=["Forecast-risk indicators", "Outbound quality scoring"],
        ),
    ),
    _payload(
        "medium_signal_04",
        "medium_signal",
        "Reasonable fit with minimal hard proof context.",
        "proof_gap_expected",
        _request(
            prospect_name="Noah Reed",
            prospect_title="VP Sales Operations",
            prospect_company="Arcline Pay",
            research_text="Arcline Pay leadership mentioned tightening sales process execution this year.",
            offer_lock="Sales Ops QA Engine",
            cta_line="Could a brief exchange on sales process QA be relevant right now?",
            sender_company="Signal Harbor",
            sender_product="Sales Ops QA Engine",
            company_notes="Supports sales ops teams with execution-quality controls.",
            seller_offerings=["Execution quality scorecards", "Rep consistency diagnostics"],
        ),
    ),
    _payload(
        "medium_signal_05",
        "medium_signal",
        "Prospect and context are plausible but not deeply evidenced.",
        "proof_gap_expected",
        _request(
            prospect_name="Leah Carter",
            prospect_title="Revenue Intelligence Manager",
            prospect_company="Cloudvine Labs",
            research_text="Cloudvine Labs is reviewing outbound messaging consistency in Q2 planning.",
            offer_lock="Revenue Intelligence QA",
            cta_line="Open to a quick conversation on consistency diagnostics for your outbound team?",
            sender_company="Signal Harbor",
            sender_product="Revenue Intelligence QA",
            company_notes="Operational QA for revenue intelligence teams.",
            seller_offerings=["Consistency trend dashboards", "Handoff QA alerts"],
        ),
    ),

    # TYPE 3: THIN INPUT (5)
    _payload(
        "thin_input_01",
        "thin_input",
        "No substantive research and sparse company notes.",
        "fails_at_stage_CONTEXT_SYNTHESIS",
        _request(
            prospect_name="Alex Quinn",
            prospect_title="VP Sales",
            prospect_company="Plainfield Tech",
            research_text="No verifiable external research provided.",
            offer_lock="Outbound QA Toolkit",
            cta_line="Open to a quick chat to see if this is relevant?",
            sender_company="Signal Harbor",
            sender_product="Outbound QA Toolkit",
            company_notes="",
            seller_offerings=[""],
        ),
    ),
    _payload(
        "thin_input_02",
        "thin_input",
        "Minimal role context with no clear trigger.",
        "proof_gap_expected",
        _request(
            prospect_name="Mina Tate",
            prospect_title="Head of Sales",
            prospect_company="Basin Note",
            research_text="Limited public context.",
            offer_lock="Messaging QA",
            cta_line="Would it make sense to share a short outbound QA checklist?",
            sender_company="Signal Harbor",
            sender_product="Messaging QA",
            company_notes="General support for sales teams.",
            seller_offerings=["QA checks"],
        ),
    ),
    _payload(
        "thin_input_03",
        "thin_input",
        "Generic input designed to force low signal behavior.",
        "proof_gap_expected",
        _request(
            prospect_name="Ben Doyle",
            prospect_title="GTM Director",
            prospect_company="Keystone Ridge",
            research_text="No specific research available for this account.",
            offer_lock="GTM QA",
            cta_line="Open to a brief conversation on outbound quality basics?",
            sender_company="Signal Harbor",
            sender_product="GTM QA",
            company_notes="Limited sender context.",
            seller_offerings=["Outbound reviews"],
        ),
    ),
    _payload(
        "thin_input_04",
        "thin_input",
        "Sparse payload with weak evidence density.",
        "proof_gap_expected",
        _request(
            prospect_name="Ria Stone",
            prospect_title="Revenue Programs Lead",
            prospect_company="Signal Moss",
            research_text="Unknown",
            offer_lock="Revenue Program QA",
            cta_line="Could a quick quality baseline discussion be useful?",
            sender_company="Signal Harbor",
            sender_product="Revenue Program QA",
            company_notes="",
            seller_offerings=["Program QA"],
        ),
    ),
    _payload(
        "thin_input_05",
        "thin_input",
        "Very little context by design for fail-closed pressure test.",
        "fails_at_stage_CONTEXT_SYNTHESIS",
        _request(
            prospect_name="Kai Moreno",
            prospect_title="RevOps Manager",
            prospect_company="Lumen Pier",
            research_text="No research.",
            offer_lock="RevOps QA",
            cta_line="Open to a quick chat to see if this is relevant?",
            sender_company="Signal Harbor",
            sender_product="RevOps QA",
            company_notes="",
            seller_offerings=[""],
        ),
    ),

    # TYPE 4: EDGE CASES (5)
    _payload(
        "edge_case_01",
        "edge_case",
        "Vague prospect notes that look factual but are not grounded.",
        "passes_all_stages",
        _request(
            prospect_name="Priya Wells",
            prospect_title="VP Revenue Strategy",
            prospect_company="Veridian Air",
            research_text="They care about efficiency and want better outcomes.",
            offer_lock="Revenue Strategy QA",
            cta_line="Open to discussing one practical way to validate messaging quality?",
            sender_company="Signal Harbor",
            sender_product="Revenue Strategy QA",
            company_notes="Avoid generic claims and keep strict grounding.",
            seller_offerings=["Grounding checks", "Signal attribution diagnostics"],
        ),
    ),
    _payload(
        "edge_case_02",
        "edge_case",
        "Proof points intentionally resemble feature descriptions.",
        "passes_all_stages",
        _request(
            prospect_name="Hugo Park",
            prospect_title="Director, Sales Excellence",
            prospect_company="Kelvin Path",
            research_text="Kelvin Path is improving outbound quality controls this quarter.",
            offer_lock="Sales Excellence QA",
            cta_line="Would a short review of your proof strategy be helpful?",
            sender_company="Signal Harbor",
            sender_product="Sales Excellence QA",
            company_notes="Proof points should be outcome-oriented, not feature-only.",
            seller_offerings=["Scoring workflow", "Process dashboard", "QA platform modules"],
        ),
    ),
    _payload(
        "edge_case_03",
        "edge_case",
        "Research references a different company to test attribution discipline.",
        "passes_all_stages",
        _request(
            prospect_name="Nadia Cole",
            prospect_title="Head of Revenue Operations",
            prospect_company="Altura Stone",
            research_text=(
                "Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs. "
                "(This is intentionally for another company.)"
            ),
            offer_lock="Attribution-Safe QA",
            cta_line="Would you be open to a quick attribution-safety walkthrough?",
            sender_company="Signal Harbor",
            sender_product="Attribution-Safe QA",
            company_notes="Strictly reject facts not attributable to this prospect/company.",
            seller_offerings=["Attribution guards", "Evidence lineage checks"],
        ),
    ),
    _payload(
        "edge_case_04",
        "edge_case",
        "CTA lock includes special characters.",
        "passes_all_stages",
        _request(
            prospect_name="Simon Hart",
            prospect_title="VP Commercial Operations",
            prospect_company="Trident Harbor",
            research_text="Trident Harbor is tightening handoff quality metrics across teams.",
            offer_lock="Commercial Ops QA",
            cta_line="Open to a 12-minute sync next Tue/Wed @ 10:30?",
            sender_company="Signal Harbor",
            sender_product="Commercial Ops QA",
            company_notes="CTA must be preserved exactly, including punctuation and symbols.",
            seller_offerings=["CTA lock enforcement", "Final-line validation"],
        ),
    ),
    _payload(
        "edge_case_05",
        "edge_case",
        "Very long research text to stress extraction quality.",
        "passes_all_stages",
        _request(
            prospect_name="Wes Nolan",
            prospect_title="VP GTM Operations",
            prospect_company="Astera Grid",
            research_text=LONG_RESEARCH,
            offer_lock="High-Volume Context QA",
            cta_line="Would a quick pass on high-volume context handling be useful?",
            sender_company="Signal Harbor",
            sender_product="High-Volume Context QA",
            company_notes="Maintain factual containment under long-context inputs.",
            seller_offerings=["Long-context signal extraction", "Context compression QA"],
        ),
    ),

    # TYPE 5: DIVERSE PERSONAS (5)
    _payload(
        "diverse_persona_01",
        "diverse_persona",
        "VP Sales at 50-person SaaS startup.",
        "passes_all_stages",
        _request(
            prospect_name="Clara Moss",
            prospect_title="VP Sales",
            prospect_company="Fleetbeam",
            research_text="Fleetbeam is standardizing outbound handoff expectations as it scales from SMB to mid-market.",
            offer_lock="Startup Sales QA",
            cta_line="Open to a quick comparison of outbound QA approaches for scaling teams?",
            sender_company="Signal Harbor",
            sender_product="Startup Sales QA",
            company_notes="Small-team sales leaders need simple, high-leverage controls.",
            seller_offerings=["Lightweight QA scorecards", "Rep-ready coaching cues"],
        ),
    ),
    _payload(
        "diverse_persona_02",
        "diverse_persona",
        "RevOps Director at 500-person fintech.",
        "passes_all_stages",
        _request(
            prospect_name="Jared Lin",
            prospect_title="Director of RevOps",
            prospect_company="Mercury Tally",
            research_text="Mercury Tally is aligning outbound process metrics with forecast governance in 2026 planning.",
            offer_lock="Fintech RevOps QA",
            cta_line="Would a short conversation on forecast-safe outbound QA be useful?",
            sender_company="Signal Harbor",
            sender_product="Fintech RevOps QA",
            company_notes="Mid-sized fintech teams need governance-friendly outbound consistency.",
            seller_offerings=["Governance controls", "Forecast-aligned QA indicators"],
        ),
    ),
    _payload(
        "diverse_persona_03",
        "diverse_persona",
        "CMO at enterprise healthcare company.",
        "passes_all_stages",
        _request(
            prospect_name="Renee Patel",
            prospect_title="Chief Marketing Officer",
            prospect_company="Healmark Systems",
            research_text="Healmark Systems is tightening campaign-to-outbound continuity to improve enterprise pipeline confidence.",
            offer_lock="Marketing-to-Sales QA",
            cta_line="Would it be useful to share a framework for campaign-to-outbound quality continuity?",
            sender_company="Signal Harbor",
            sender_product="Marketing-to-Sales QA",
            company_notes="CMOs need signal that messaging quality supports pipeline trust.",
            seller_offerings=["Continuity scoring", "Message quality observability"],
        ),
    ),
    _payload(
        "diverse_persona_04",
        "diverse_persona",
        "SDR Manager at mid-market logistics firm.",
        "passes_all_stages",
        _request(
            prospect_name="Devon Hall",
            prospect_title="SDR Manager",
            prospect_company="Portline Logistics",
            research_text="Portline Logistics is revising SDR playbooks after inconsistent first-touch quality.",
            offer_lock="SDR Playbook QA",
            cta_line="Open to a quick exchange on improving SDR first-touch quality?",
            sender_company="Signal Harbor",
            sender_product="SDR Playbook QA",
            company_notes="SDR managers need practical controls with low adoption overhead.",
            seller_offerings=["Playbook QA checks", "First-touch diagnostics"],
        ),
    ),
    _payload(
        "diverse_persona_05",
        "diverse_persona",
        "Head of Growth at early-stage marketplace.",
        "passes_all_stages",
        _request(
            prospect_name="Imani Rowe",
            prospect_title="Head of Growth",
            prospect_company="Parcel Loop",
            research_text="Parcel Loop is tuning outbound messaging for new vertical experiments this quarter.",
            offer_lock="Growth Experiment QA",
            cta_line="Would it help to compare how growth teams QA outbound experiments?",
            sender_company="Signal Harbor",
            sender_product="Growth Experiment QA",
            company_notes="Growth teams need fast feedback loops without losing message quality.",
            seller_offerings=["Experiment-safe messaging QA", "Rapid iteration diagnostics"],
        ),
    ),

    # TYPE 6: EMAILDJ SELLING ITSELF (5)
    _payload(
        "emaildj_01",
        "emaildj",
        "EmailDJ pitching a RevOps leader with strong timing context.",
        "passes_all_stages",
        _request(
            prospect_name="Jordan Lee",
            prospect_title="VP Revenue Operations",
            prospect_company="Nimbus Health",
            research_text=(
                "Nimbus Health expanded RevOps ownership in January 2026 to improve pipeline hygiene, "
                "handoff SLAs, and forecasting consistency."
            ),
            offer_lock="EmailDJ",
            cta_line="Open to a quick chat to see if this is relevant?",
            sender_company="EmailDJ",
            sender_product="EmailDJ",
            company_notes="EmailDJ helps SDR teams generate grounded outbound drafts with strict CTA lock and quality controls.",
            seller_offerings=["Stage-based draft QA", "Grounding validators", "CTA lock enforcement"],
        ),
    ),
    _payload(
        "emaildj_02",
        "emaildj",
        "EmailDJ targeting a sales ops buyer persona.",
        "passes_all_stages",
        _request(
            prospect_name="Alina Boyd",
            prospect_title="VP Sales Operations",
            prospect_company="Vector Source",
            research_text="Vector Source is auditing outbound handoff quality after uneven meeting outcomes.",
            offer_lock="EmailDJ",
            cta_line="Would a short walkthrough of grounded outbound QA be useful?",
            sender_company="EmailDJ",
            sender_product="EmailDJ",
            company_notes="EmailDJ prevents generic copy drift and keeps outreach tied to source facts.",
            seller_offerings=["Source-attributed messaging", "Prompt-stage validators", "Sequence QA traces"],
        ),
    ),
    _payload(
        "emaildj_03",
        "emaildj",
        "EmailDJ for enablement leader with medium-signal context.",
        "proof_gap_expected",
        _request(
            prospect_name="Gabe Ellis",
            prospect_title="Head of Sales Enablement",
            prospect_company="Lattice Harbor",
            research_text="Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
            offer_lock="EmailDJ",
            cta_line="Open to comparing enablement-focused outbound QA guardrails?",
            sender_company="EmailDJ",
            sender_product="EmailDJ",
            company_notes="EmailDJ translates sparse context into constrained atoms before drafting.",
            seller_offerings=["Message atom constraints", "Enablement-safe draft checks"],
        ),
    ),
    _payload(
        "emaildj_04",
        "emaildj",
        "EmailDJ for SDR manager with explicit quality pain.",
        "passes_all_stages",
        _request(
            prospect_name="Tara Nguyen",
            prospect_title="SDR Manager",
            prospect_company="Raven Pilot",
            research_text="Raven Pilot reported inconsistent opener quality across SDR pods and wants tighter coaching loops.",
            offer_lock="EmailDJ",
            cta_line="Would a quick review of opener quality controls be worth 15 minutes?",
            sender_company="EmailDJ",
            sender_product="EmailDJ",
            company_notes="EmailDJ helps SDR managers scale quality without template drift.",
            seller_offerings=["Opener quality scoring", "Rep-level guidance traces", "Rewrite guardrails"],
        ),
    ),
    _payload(
        "emaildj_05",
        "emaildj",
        "EmailDJ thin-input calibration case.",
        "fails_at_stage_CONTEXT_SYNTHESIS",
        _request(
            prospect_name="Miles Chen",
            prospect_title="Director, Revenue Programs",
            prospect_company="Beacon Trail",
            research_text="No verifiable research available.",
            offer_lock="EmailDJ",
            cta_line="Open to a quick chat to see if this is relevant?",
            sender_company="EmailDJ",
            sender_product="EmailDJ",
            company_notes="",
            seller_offerings=[""],
        ),
    ),
]


def get_all_payloads() -> list[dict[str, Any]]:
    return deepcopy(PAYLOADS)


def get_payload(payload_id: str) -> dict[str, Any] | None:
    needle = str(payload_id or "").strip()
    for payload in PAYLOADS:
        if payload["payload_id"] == needle:
            return deepcopy(payload)
    return None


def get_payloads_by_type(type_name: str) -> list[dict[str, Any]]:
    wanted = str(type_name or "").strip().lower()
    return [deepcopy(item) for item in PAYLOADS if str(item.get("payload_type") or "").lower() == wanted]
