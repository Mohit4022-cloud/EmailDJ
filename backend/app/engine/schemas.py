from __future__ import annotations

from copy import deepcopy

ALLOWED_STAGE_A_SOURCE_FIELDS = [
    "name",
    "title",
    "company",
    "industry",
    "prospect_notes",
    "research_text",
    "product_summary",
    "icp_description",
    "differentiators",
    "proof_points",
    "do_not_say",
    "company_notes",
    "cta_type",
    "cta_final_line",
]


COMMON_DEFS = {
    "NonEmptyStr": {"type": "string", "minLength": 1},
    "IdStr": {"type": "string", "minLength": 1, "maxLength": 128},
    "ShortEvidenceStr": {"type": "string", "minLength": 1, "maxLength": 200},
    "RiskFlag": {"type": "string", "minLength": 1, "maxLength": 80},
    "SourceField": {
        "type": "string",
        "enum": ALLOWED_STAGE_A_SOURCE_FIELDS,
    },
    "FactKind": {
        "type": "string",
        "enum": ["prospect_context", "seller_context", "seller_proof", "cta"],
    },
    "HookType": {
        "type": "string",
        "enum": ["pain", "priority", "initiative", "tooling", "trigger_event", "other"],
    },
    "ConfidenceLevel": {
        "type": "string",
        "enum": ["low", "medium", "high"],
    },
    "EvidenceStrength": {
        "type": "string",
        "enum": ["weak", "moderate", "strong"],
    },
    "OverreachRisk": {
        "type": "string",
        "enum": ["low", "medium", "high"],
    },
    "RiskLevel": {
        "type": "string",
        "enum": ["low", "medium", "high"],
    },
    "AngleType": {
        "type": "string",
        "enum": [
            "why_you_why_now",
            "problem_led",
            "outcome_led",
            "proof_led",
            "objection_prebunk",
        ],
    },
    "FramingType": {
        "type": "string",
        "enum": [
            "why_you_why_now",
            "why_now",
            "problem_led",
            "outcome_led",
            "proof_led",
            "objection_prebunk",
        ],
    },
    "ProofBasisKind": {
        "type": "string",
        "enum": ["hard_proof", "soft_signal", "capability_statement", "assumption", "none"],
    },
    "IssueType": {
        "type": "string",
        "enum": [
            "credibility",
            "specificity",
            "structure",
            "spam_risk",
            "personalization",
            "length",
            "cta",
            "grammar",
            "tone",
            "clarity",
            "word_count_out_of_band",
            "opener_too_soft_for_preset",
            "proof_density_too_low",
            "too_many_sentences_for_preset",
            "tone_mismatch_for_preset",
            "cta_not_in_expected_form",
            "other",
        ],
    },
    "Severity": {"type": "string", "enum": ["low", "medium", "high"]},
    "IssueCodeStr": {"type": "string", "minLength": 1, "maxLength": 80},
    "TargetSectionStr": {"type": "string", "minLength": 1, "maxLength": 240},
    "WhyItFailsStr": {"type": "string", "minLength": 1, "maxLength": 400},
    "ExpectedEffectStr": {"type": "string", "minLength": 1, "maxLength": 240},
    "ProofBasis": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "kind",
            "source_fact_ids",
            "source_hook_ids",
            "source_fit_hypothesis_id",
            "grounded_span",
            "source_text",
            "proof_gap",
        ],
        "properties": {
            "kind": {"$ref": "#/$defs/ProofBasisKind"},
            "source_fact_ids": {
                "type": "array",
                "items": {"$ref": "#/$defs/IdStr"},
            },
            "source_hook_ids": {
                "type": "array",
                "items": {"$ref": "#/$defs/IdStr"},
            },
            "source_fit_hypothesis_id": {"type": "string", "maxLength": 128},
            "grounded_span": {"type": "string", "maxLength": 240},
            "source_text": {"type": "string", "maxLength": 240},
            "proof_gap": {"type": "boolean"},
        },
    },
    "CtaLock": {
        "type": "object",
        "additionalProperties": False,
        "required": ["final_line", "normalized_final_line"],
        "properties": {
            "final_line": {"$ref": "#/$defs/NonEmptyStr"},
            "normalized_final_line": {"$ref": "#/$defs/NonEmptyStr"},
        },
    },
    "OpenerContract": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "max_words",
            "max_commas",
            "plain_english_required",
            "allow_leading_subordinate_clause",
        ],
        "properties": {
            "max_words": {"type": "integer", "minimum": 1, "maximum": 30},
            "max_commas": {"type": "integer", "minimum": 0, "maximum": 2},
            "plain_english_required": {"type": "boolean"},
            "allow_leading_subordinate_clause": {"type": "boolean"},
        },
    },
    "RewritePatchAction": {
        "type": "string",
        "enum": ["keep", "rewrite", "insert_after", "delete"],
    },
    "RewriteSentenceOperation": {
        "type": "object",
        "additionalProperties": False,
        "required": ["issue_code", "action", "target_sentence_index", "text"],
        "properties": {
            "issue_code": {"$ref": "#/$defs/IssueCodeStr"},
            "action": {"$ref": "#/$defs/RewritePatchAction"},
            "target_sentence_index": {"type": "integer", "minimum": 0, "maximum": 64},
            "text": {"type": "string", "maxLength": 800},
        },
    },
    "Fact": {
        "type": "object",
        "additionalProperties": False,
        "required": ["fact_id", "source_field", "fact_kind", "text"],
        "properties": {
            "fact_id": {"$ref": "#/$defs/IdStr"},
            "source_field": {"$ref": "#/$defs/SourceField"},
            "fact_kind": {"$ref": "#/$defs/FactKind"},
            "text": {"$ref": "#/$defs/NonEmptyStr"},
        },
    },
    "Assumption": {
        "type": "object",
        "additionalProperties": False,
        "required": ["assumption_id", "assumption_kind", "text", "confidence", "confidence_label", "based_on_fact_ids"],
        "properties": {
            "assumption_id": {"$ref": "#/$defs/IdStr"},
            "assumption_kind": {"type": "string", "enum": ["inferred_hypothesis"]},
            "text": {"$ref": "#/$defs/NonEmptyStr"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "confidence_label": {"$ref": "#/$defs/ConfidenceLevel"},
            "based_on_fact_ids": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/IdStr"},
            },
        },
    },
    "Hook": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "hook_id",
            "hook_type",
            "grounded_observation",
            "inferred_relevance",
            "seller_support",
            "hook_text",
            "supported_by_fact_ids",
            "seller_fact_ids",
            "confidence_level",
            "evidence_strength",
            "risk_flags",
        ],
        "properties": {
            "hook_id": {"$ref": "#/$defs/IdStr"},
            "hook_type": {"$ref": "#/$defs/HookType"},
            "grounded_observation": {"$ref": "#/$defs/NonEmptyStr"},
            "inferred_relevance": {"$ref": "#/$defs/NonEmptyStr"},
            "seller_support": {"type": "string", "maxLength": 240},
            "hook_text": {"$ref": "#/$defs/NonEmptyStr"},
            "supported_by_fact_ids": {
                "type": "array",
                "items": {"$ref": "#/$defs/IdStr"},
            },
            "seller_fact_ids": {
                "type": "array",
                "items": {"$ref": "#/$defs/IdStr"},
            },
            "confidence_level": {"$ref": "#/$defs/ConfidenceLevel"},
            "evidence_strength": {"$ref": "#/$defs/EvidenceStrength"},
            "risk_flags": {"type": "array", "items": {"$ref": "#/$defs/RiskFlag"}},
        },
    },
}

MESSAGING_BRIEF_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "version",
        "brief_id",
        "facts_from_input",
        "assumptions",
        "hooks",
        "persona_cues",
        "do_not_say",
        "forbidden_claim_patterns",
        "prohibited_overreach",
        "grounding_policy",
        "brief_quality",
    ],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "brief_id": {"$ref": "#/$defs/IdStr"},
        "facts_from_input": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/Fact"},
        },
        "assumptions": {
            "type": "array",
            "items": {"$ref": "#/$defs/Assumption"},
        },
        "hooks": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/Hook"},
        },
        "hook_lineage": {
            "type": "object",
            "additionalProperties": False,
            "required": ["canonical_hook_ids", "hook_alias_map"],
            "properties": {
                "canonical_hook_ids": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/IdStr"},
                },
                "hook_alias_map": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/IdStr"},
                },
            },
        },
        "persona_cues": {
            "type": "object",
            "additionalProperties": False,
            "required": ["likely_kpis", "likely_initiatives", "day_to_day", "tools_stack", "notes"],
            "properties": {
                "likely_kpis": {"type": "array", "items": {"$ref": "#/$defs/NonEmptyStr"}},
                "likely_initiatives": {"type": "array", "items": {"$ref": "#/$defs/NonEmptyStr"}},
                "day_to_day": {"type": "array", "items": {"$ref": "#/$defs/NonEmptyStr"}},
                "tools_stack": {"type": "array", "items": {"$ref": "#/$defs/NonEmptyStr"}},
                "notes": {"type": "string", "maxLength": 600},
            },
        },
        "do_not_say": {
            "type": "array",
            "items": {"$ref": "#/$defs/NonEmptyStr"},
        },
        "forbidden_claim_patterns": {
            "type": "array",
            "items": {"$ref": "#/$defs/NonEmptyStr"},
        },
        "prohibited_overreach": {
            "type": "array",
            "items": {"$ref": "#/$defs/NonEmptyStr"},
        },
        "grounding_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["no_new_facts", "no_ungrounded_personalization", "allowed_personalization_fact_sources"],
            "properties": {
                "no_new_facts": {"type": "boolean"},
                "no_ungrounded_personalization": {"type": "boolean"},
                "allowed_personalization_fact_sources": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/SourceField"},
                },
            },
        },
        "brief_quality": {
            "type": "object",
            "additionalProperties": False,
            "required": ["quality_notes"],
            "properties": {
                "quality_notes": {"type": "array", "items": {"$ref": "#/$defs/NonEmptyStr"}},
            },
        },
    },
}

MESSAGING_BRIEF_RESPONSE_SCHEMA = deepcopy(MESSAGING_BRIEF_SCHEMA)
MESSAGING_BRIEF_RESPONSE_SCHEMA["properties"] = dict(MESSAGING_BRIEF_RESPONSE_SCHEMA["properties"])
MESSAGING_BRIEF_RESPONSE_SCHEMA["properties"].pop("hook_lineage", None)

FIT_MAP_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "hypotheses"],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "hypotheses": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "fit_hypothesis_id",
                    "rank",
                    "selected_hook_id",
                    "pain",
                    "impact",
                    "value",
                    "proof",
                    "proof_basis",
                    "supporting_fact_ids",
                    "why_now",
                    "confidence",
                    "risk_flags",
                ],
                "properties": {
                    "fit_hypothesis_id": {"$ref": "#/$defs/IdStr"},
                    "rank": {"type": "integer", "minimum": 1, "maximum": 25},
                    "selected_hook_id": {"$ref": "#/$defs/IdStr"},
                    "pain": {"$ref": "#/$defs/NonEmptyStr"},
                    "impact": {"$ref": "#/$defs/NonEmptyStr"},
                    "value": {"$ref": "#/$defs/NonEmptyStr"},
                    "proof": {"$ref": "#/$defs/NonEmptyStr"},
                    "proof_basis": {"$ref": "#/$defs/ProofBasis"},
                    "supporting_fact_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/IdStr"},
                    },
                    "why_now": {"type": "string", "minLength": 1, "maxLength": 240},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "risk_flags": {"type": "array", "items": {"$ref": "#/$defs/RiskFlag"}},
                },
            },
        },
    },
}

ANGLE_SET_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "angles"],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "angles": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "angle_id",
                    "angle_type",
                    "rank",
                    "persona_fit_score",
                    "selected_hook_id",
                    "selected_fit_hypothesis_id",
                    "pain",
                    "impact",
                    "value",
                    "proof",
                    "proof_basis",
                    "primary_pain",
                    "primary_value_motion",
                    "primary_proof_basis",
                    "framing_type",
                    "risk_level",
                    "cta_question_suggestion",
                    "risk_flags",
                ],
                "properties": {
                    "angle_id": {"$ref": "#/$defs/IdStr"},
                    "angle_type": {"$ref": "#/$defs/AngleType"},
                    "rank": {"type": "integer", "minimum": 1, "maximum": 10},
                    "persona_fit_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "selected_hook_id": {"$ref": "#/$defs/IdStr"},
                    "selected_fit_hypothesis_id": {"$ref": "#/$defs/IdStr"},
                    "pain": {"$ref": "#/$defs/NonEmptyStr"},
                    "impact": {"$ref": "#/$defs/NonEmptyStr"},
                    "value": {"$ref": "#/$defs/NonEmptyStr"},
                    "proof": {"$ref": "#/$defs/NonEmptyStr"},
                    "proof_basis": {"$ref": "#/$defs/ProofBasis"},
                    "primary_pain": {"$ref": "#/$defs/NonEmptyStr"},
                    "primary_value_motion": {"$ref": "#/$defs/NonEmptyStr"},
                    "primary_proof_basis": {"$ref": "#/$defs/NonEmptyStr"},
                    "framing_type": {"$ref": "#/$defs/FramingType"},
                    "risk_level": {"$ref": "#/$defs/RiskLevel"},
                    "cta_question_suggestion": {"type": "string", "minLength": 1, "maxLength": 160},
                    "risk_flags": {"type": "array", "items": {"$ref": "#/$defs/RiskFlag"}},
                },
            },
        },
    },
}

MESSAGE_ATOMS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "version",
        "preset_id",
        "selected_angle_id",
        "used_hook_ids",
        "canonical_hook_ids",
        "opener_atom",
        "opener_line",
        "opener_contract",
        "value_atom",
        "proof_atom",
        "proof_basis",
        "cta_atom",
        "cta_intent",
        "required_cta_line",
        "cta_lock",
        "target_word_budget",
        "target_sentence_budget",
    ],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "preset_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "selected_angle_id": {"$ref": "#/$defs/IdStr"},
        "used_hook_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/IdStr"},
        },
        "canonical_hook_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/IdStr"},
        },
        "opener_atom": {"type": "string", "minLength": 1, "maxLength": 220},
        "opener_line": {"type": "string", "minLength": 1, "maxLength": 220},
        "opener_contract": {"$ref": "#/$defs/OpenerContract"},
        "value_atom": {"type": "string", "minLength": 1, "maxLength": 220},
        "proof_atom": {"type": "string", "minLength": 0, "maxLength": 220},
        "proof_basis": {"$ref": "#/$defs/ProofBasis"},
        "cta_atom": {"type": "string", "minLength": 1, "maxLength": 240},
        "cta_intent": {"type": "string", "minLength": 1, "maxLength": 240},
        "required_cta_line": {"type": "string", "minLength": 1, "maxLength": 240},
        "cta_lock": {"$ref": "#/$defs/CtaLock"},
        "target_word_budget": {"type": "integer", "minimum": 1, "maximum": 400},
        "target_sentence_budget": {"type": "integer", "minimum": 1, "maximum": 12},
    },
}

EMAIL_DRAFT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "preset_id", "selected_angle_id", "used_hook_ids", "subject", "body"],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "preset_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "selected_angle_id": {"$ref": "#/$defs/IdStr"},
        "used_hook_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/IdStr"},
        },
        "subject": {"type": "string", "minLength": 1, "maxLength": 70},
        "body": {"type": "string", "minLength": 1, "maxLength": 4000},
    },
}

BATCH_VARIANTS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "variants"],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "variants": {
            "type": "array",
            "minItems": 1,
            "items": {
                "oneOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["preset_id", "selected_angle_id", "used_hook_ids", "subject", "body"],
                        "properties": {
                            "preset_id": {"type": "string", "minLength": 1, "maxLength": 64},
                            "selected_angle_id": {"$ref": "#/$defs/IdStr"},
                            "used_hook_ids": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"$ref": "#/$defs/IdStr"},
                            },
                            "subject": {"type": "string", "minLength": 1, "maxLength": 70},
                            "body": {"type": "string", "minLength": 1, "maxLength": 4000},
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["preset_id", "error"],
                        "properties": {
                            "preset_id": {"type": "string", "minLength": 1, "maxLength": 64},
                            "error": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["code", "message"],
                                "properties": {
                                    "code": {"type": "string", "minLength": 1, "maxLength": 80},
                                    "message": {"type": "string", "minLength": 1, "maxLength": 400},
                                },
                            },
                        },
                    },
                ],
            },
        },
    },
}

QA_REPORT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "issues", "risk_flags", "rewrite_plan", "pass_rewrite_needed"],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "pass_rewrite_needed": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "issue_code",
                    "type",
                    "severity",
                    "offending_span_or_target_section",
                    "evidence_quote",
                    "why_it_fails",
                    "evidence",
                    "fix_instruction",
                    "expected_effect",
                ],
                "properties": {
                    "issue_code": {"$ref": "#/$defs/IssueCodeStr"},
                    "type": {"$ref": "#/$defs/IssueType"},
                    "severity": {"$ref": "#/$defs/Severity"},
                    "offending_span_or_target_section": {"$ref": "#/$defs/TargetSectionStr"},
                    "evidence_quote": {"$ref": "#/$defs/ShortEvidenceStr"},
                    "why_it_fails": {"$ref": "#/$defs/WhyItFailsStr"},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/ShortEvidenceStr"},
                    },
                    "fix_instruction": {"type": "string", "minLength": 1, "maxLength": 600},
                    "expected_effect": {"$ref": "#/$defs/ExpectedEffectStr"},
                },
            },
        },
        "risk_flags": {"type": "array", "items": {"$ref": "#/$defs/RiskFlag"}},
        "rewrite_plan": {
            "type": "array",
            "minItems": 0,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "issue_code",
                    "target",
                    "action",
                    "replacement_guidance",
                    "preserve",
                    "expected_effect",
                ],
                "properties": {
                    "issue_code": {"$ref": "#/$defs/IssueCodeStr"},
                    "target": {"$ref": "#/$defs/TargetSectionStr"},
                    "action": {"type": "string", "minLength": 1, "maxLength": 400},
                    "replacement_guidance": {"type": "string", "minLength": 1, "maxLength": 500},
                    "preserve": {"type": "string", "minLength": 1, "maxLength": 240},
                    "expected_effect": {"$ref": "#/$defs/ExpectedEffectStr"},
                },
            },
        },
    },
}

EMAIL_REWRITE_PATCH_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "version",
        "preset_id",
        "selected_angle_id",
        "used_hook_ids",
        "cta_lock",
        "preserve_sentence_indexes",
        "sentence_operations",
    ],
    "$defs": {**COMMON_DEFS},
    "properties": {
        "version": {"type": "string", "minLength": 1, "maxLength": 32},
        "preset_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "selected_angle_id": {"$ref": "#/$defs/IdStr"},
        "used_hook_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/IdStr"},
        },
        "cta_lock": {"$ref": "#/$defs/CtaLock"},
        "preserve_sentence_indexes": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 64},
        },
        "sentence_operations": {
            "type": "array",
            "items": {"$ref": "#/$defs/RewriteSentenceOperation"},
        },
    },
}

JUDGE_RESULT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "stage",
        "scores",
        "total",
        "pass",
        "hard_fail_triggered",
        "hard_fail_criteria",
        "failures",
        "warnings",
    ],
    "properties": {
        "stage": {
            "type": "string",
            "enum": [
                "CONTEXT_SYNTHESIS",
                "FIT_REASONING",
                "ANGLE_PICKER",
                "ONE_LINER_COMPRESSOR",
                "EMAIL_GENERATION",
                "EMAIL_QA",
                "EMAIL_REWRITE",
            ],
        },
        "scores": {
            "type": "object",
            "additionalProperties": {"type": "integer", "enum": [0, 1]},
        },
        "total": {"type": "integer", "minimum": 0, "maximum": 32},
        "pass": {"type": "boolean"},
        "hard_fail_triggered": {"type": "boolean"},
        "hard_fail_criteria": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 120}},
        "failures": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 600}},
        "warnings": {"type": "array", "items": {"type": "string", "maxLength": 600}},
    },
}

ERROR_RESULT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["ok", "trace_id", "error"],
    "properties": {
        "ok": {"type": "boolean", "enum": [False]},
        "trace_id": {"type": "string", "minLength": 8, "maxLength": 128},
        "error": {
            "type": "object",
            "additionalProperties": False,
            "required": ["code", "message", "stage"],
            "properties": {
                "code": {"type": "string", "minLength": 1, "maxLength": 80},
                "message": {"type": "string", "minLength": 1, "maxLength": 600},
                "stage": {
                    "type": "string",
                    "enum": [
                        "CONTEXT_SYNTHESIS",
                        "FIT_REASONING",
                        "ANGLE_PICKER",
                        "ONE_LINER_COMPRESSOR",
                        "EMAIL_GENERATION",
                        "EMAIL_QA",
                        "EMAIL_REWRITE",
                        "VALIDATION",
                        "TRANSPORT",
                        "UNKNOWN",
                    ],
                },
                "details": {"type": "object"},
            },
        },
    },
}


def response_format(name: str, schema: dict, *, local_schema: dict | None = None) -> dict:
    payload = {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": schema,
            "strict": True,
        },
    }
    if local_schema is not None:
        payload["local_schema"] = local_schema
    return payload


RF_MESSAGING_BRIEF = response_format(
    "MessagingBrief",
    MESSAGING_BRIEF_RESPONSE_SCHEMA,
    local_schema=MESSAGING_BRIEF_SCHEMA,
)
RF_FIT_MAP = response_format("FitMap", FIT_MAP_SCHEMA)
RF_ANGLE_SET = response_format("AngleSet", ANGLE_SET_SCHEMA)
RF_MESSAGE_ATOMS = response_format("MessageAtoms", MESSAGE_ATOMS_SCHEMA)
RF_EMAIL_DRAFT = response_format("EmailDraft", EMAIL_DRAFT_SCHEMA)
RF_EMAIL_REWRITE_PATCH = response_format("EmailRewritePatch", EMAIL_REWRITE_PATCH_SCHEMA)
RF_BATCH_VARIANTS = response_format("BatchVariants", BATCH_VARIANTS_SCHEMA)
RF_QA_REPORT = response_format("QAReport", QA_REPORT_SCHEMA)
RF_JUDGE_RESULT = response_format("JudgeResult", JUDGE_RESULT_SCHEMA)

STAGES = {
    "A": "CONTEXT_SYNTHESIS",
    "B": "FIT_REASONING",
    "B0": "ANGLE_PICKER",
    "C0": "ONE_LINER_COMPRESSOR",
    "C": "EMAIL_GENERATION",
    "D": "EMAIL_QA",
    "E": "EMAIL_REWRITE",
}
