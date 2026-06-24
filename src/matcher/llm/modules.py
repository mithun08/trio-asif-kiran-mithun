from __future__ import annotations

import dspy


class ProfileExtraction(dspy.Signature):
    """Extract structured consultant profile fields from raw PDF text."""

    raw_text: str = dspy.InputField()
    skills_json: str = dspy.OutputField(desc="JSON list of {name, years_experience, proficiency}")
    location: str = dspy.OutputField()
    grade: str = dspy.OutputField()
    evidence_spans: str = dspy.OutputField(
        desc="JSON list of verbatim substrings from raw_text supporting the extractions"
    )


class CandidateExplanation(dspy.Signature):
    """Generate a factual, grounded explanation for a candidate's ranking."""

    role_title: str = dspy.InputField()
    candidate_name: str = dspy.InputField()
    dimension_scores_json: str = dspy.InputField(desc="JSON list of dimension score objects")
    why_not_higher_context: str = dspy.InputField(
        desc="Dimension gaps vs the candidate ranked above; empty string for rank 1"
    )
    explanation: str = dspy.OutputField(desc="2-3 sentences citing evidence; no inference.")
    why_not_higher: str = dspy.OutputField(
        desc="1-2 sentences on why this candidate did not rank higher; empty for rank 1"
    )


class FeedbackSignalExtraction(dspy.Signature):
    """Extract structured feedback signals from a consultant feedback text."""

    feedback_text: str = dspy.InputField()
    sentiment: str = dspy.OutputField(desc="One of: positive, neutral, negative")
    strengths: str = dspy.OutputField(desc="JSON list of strength observations")
    concerns: str = dspy.OutputField(desc="JSON list of concerns or gaps")
    client_keep_signal: str = dspy.OutputField(desc="true or false")
    domain_depth: str = dspy.OutputField(desc="true or false")
    evidence_spans: str = dspy.OutputField(
        desc="JSON list of verbatim substrings from feedback_text supporting the signals"
    )


class AdaptabilitySignalExtraction(dspy.Signature):
    """Extract adaptability signals from combined profile and feedback text."""

    combined_text: str = dspy.InputField()
    tech_transitions: str = dspy.OutputField(
        desc="Integer count of distinct technology-era transitions"
    )
    learning_speed_mentions: str = dspy.OutputField(desc="true or false")
    cross_domain: str = dspy.OutputField(
        desc="Integer count of distinct industry domains worked in"
    )
    upskilling: str = dspy.OutputField(desc="true or false")
    evidence_spans: str = dspy.OutputField(
        desc="JSON list of verbatim substrings from combined_text supporting the signals"
    )


class PerformanceTrendExtraction(dspy.Signature):
    """Infer the consultant's performance trend from combined feedback and profile text."""

    combined_text: str = dspy.InputField()
    trend: str = dspy.OutputField(desc="One of: improving, stable, declining, unknown")
    evidence_spans: str = dspy.OutputField(
        desc="JSON list of verbatim substrings from combined_text indicating the trend"
    )


class SkillInference(dspy.Signature):
    """Infer likely required skills for a role from its title and description."""

    role_title: str = dspy.InputField()
    role_description: str = dspy.InputField()
    inferred_skills_json: str = dspy.OutputField(
        desc='JSON list of {"name": str, "confidence": float 0-1}'
    )
