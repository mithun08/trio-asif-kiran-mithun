from __future__ import annotations

import dspy


class ProfileExtraction(dspy.Signature):
    """Extract structured consultant profile fields from raw PDF text."""

    raw_text: str = dspy.InputField()
    skills_json: str = dspy.OutputField(desc="JSON list of {name, years_experience, proficiency}")
    location: str = dspy.OutputField()
    grade: str = dspy.OutputField()


class CandidateExplanation(dspy.Signature):
    """Generate a factual, grounded explanation for a candidate's ranking."""

    role_title: str = dspy.InputField()
    candidate_name: str = dspy.InputField()
    dimension_scores_json: str = dspy.InputField(desc="JSON list of dimension score objects")
    explanation: str = dspy.OutputField(desc="2-3 sentences citing evidence; no inference.")


class SkillAmbiguityResolution(dspy.Signature):
    """Confirm whether a candidate skill is a valid match for a required skill."""

    required_skill: str = dspy.InputField()
    candidate_skill: str = dspy.InputField()
    context: str = dspy.InputField(desc="Any additional context about the role or candidate")
    is_match: bool = dspy.OutputField()
    confidence: float = dspy.OutputField(desc="Confidence score between 0.0 and 1.0")
