from __future__ import annotations

import re

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON", "ORGANIZATION"]
_LANGUAGE = "en"
_NLP_CONFIG = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}
_EMAIL_PATTERN = r"[\w.+\-]+@[\w\-]+\.[a-zA-Z][\w.]*[a-zA-Z0-9]"

_analyzer: AnalyzerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is not None:
        return _analyzer

    provider = NlpEngineProvider(nlp_configuration=_NLP_CONFIG)
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
    email_recognizer = PatternRecognizer(
        supported_entity="EMAIL_ADDRESS",
        patterns=[Pattern("email_broad", _EMAIL_PATTERN, 0.9)],
    )
    analyzer.registry.add_recognizer(email_recognizer)
    _analyzer = analyzer
    return _analyzer


def _build_token(entity_type: str, index: int) -> str:
    return f"<{entity_type}_{index}>"


def scrub_text(text: str) -> tuple[str, dict[str, str]]:
    if not text:
        return text, {}

    analyzer = _get_analyzer()
    results = analyzer.analyze(text=text, entities=_ENTITIES, language=_LANGUAGE)

    if not results:
        return text, {}

    sorted_results = sorted(results, key=lambda r: r.start)

    counters: dict[str, int] = {}
    assignments: list[tuple[int, int, str]] = []
    token_map: dict[str, str] = {}

    for result in sorted_results:
        entity_type = result.entity_type
        current_index = counters.get(entity_type, 0)
        counters[entity_type] = current_index + 1
        token = _build_token(entity_type, current_index)
        original_value = text[result.start : result.end]
        token_map[token] = original_value
        assignments.append((result.start, result.end, token))

    scrubbed = text
    for start, end, token in reversed(assignments):
        scrubbed = scrubbed[:start] + token + scrubbed[end:]

    return scrubbed, token_map


def rehydrate_text(scrubbed_text: str, token_map: dict[str, str]) -> str:
    result = scrubbed_text
    for token, original_value in token_map.items():
        result = result.replace(token, original_value)
    return result


_RESIDUAL_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.ASCII)
_RESIDUAL_PHONE = re.compile(r"(?<!\w)(\+?\d[\d\s\-().]{7,}\d)(?!\w)")


def assert_no_residual_pii(text: str) -> None:
    if _RESIDUAL_EMAIL.search(text):
        raise ValueError("Post-scrub residual email pattern detected")
    if _RESIDUAL_PHONE.search(text):
        raise ValueError("Post-scrub residual phone pattern detected")
