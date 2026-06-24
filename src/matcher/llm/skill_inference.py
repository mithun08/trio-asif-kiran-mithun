from __future__ import annotations

import dspy

from matcher.llm.extract import _parse_json_list
from matcher.llm.modules import SkillInference
from matcher.models.role import RequiredSkill, Role


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
