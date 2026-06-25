from __future__ import annotations

from typing import Any


def build_faithfulness_test_cases(
    candidates: list[Any],
    consultants: list[Any],
) -> list[Any]:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        return []

    cases = []
    for sc in candidates:
        if not sc.explanation:
            continue
        dim_texts = [f"{d.name}: {d.raw_score:.1f}" for d in sc.dimensions]
        context = " | ".join(dim_texts)
        cases.append(
            LLMTestCase(
                input=context,
                actual_output=sc.explanation,
                expected_output="",
                context=[context],
            )
        )
    return cases
