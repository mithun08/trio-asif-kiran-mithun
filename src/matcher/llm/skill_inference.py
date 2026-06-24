from __future__ import annotations

import dspy

from matcher.llm.extract import _parse_json_list
from matcher.llm.modules import SkillInference
from matcher.models.role import RequiredSkill, Role


def _tap_lm_history(lm: object, task: str) -> None:
    from matcher.observability import telemetry as _tel
    from matcher.observability.cost_table import cost_for

    history = getattr(lm, "history", None)
    if not history:
        return
    last = history[-1]
    usage = getattr(last, "usage", None) or {}
    if isinstance(usage, dict):
        pt = int(usage.get("prompt_tokens", 0))
        ct = int(usage.get("completion_tokens", 0))
    else:
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ct = int(getattr(usage, "completion_tokens", 0) or 0)
    model = str(getattr(lm, "model", "") or "")
    cache = bool(getattr(last, "cache_hit", False) or False)
    _tel.record_llm_call(task, pt + ct, cost_for(model, pt, ct), cache)


def infer_skills_for_role(
    role: Role,
    inference_lm: dspy.LM,
    min_confidence: float = 0.5,
) -> tuple[list[RequiredSkill], float]:
    with dspy.context(lm=inference_lm):
        result = dspy.Predict(SkillInference)(
            role_title=role.title,
            role_description=role.description,
        )
    _tap_lm_history(inference_lm, "skill_inference")

    raw: str = getattr(result, "inferred_skills_json", "[]")
    items = _parse_json_list(raw)

    skills: list[RequiredSkill] = []
    confs: list[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        conf_raw = item.get("confidence", 0.0)
        conf = float(conf_raw) if isinstance(conf_raw, (int, float)) else 0.0
        if name and conf >= min_confidence:
            skills.append(RequiredSkill(name=name, mandatory=True))
            confs.append(conf)

    avg = sum(confs) / len(confs) if confs else 0.0
    return skills, avg
