from __future__ import annotations

from matcher.models.output import RunOutput


def render_json(output: RunOutput) -> str:
    return output.model_dump_json(indent=2)
