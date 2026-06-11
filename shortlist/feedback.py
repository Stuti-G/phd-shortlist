from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

OUTCOME_REWARD = {
    "ADMIT": 1.0,
    "INTERVIEW": 0.8,
    "POSITIVE_REPLY": 0.5,
    "OUT_OF_OFFICE": 0.0,
    "NO_REPLY": -0.05,
    "REJECT": -0.2,
    "NOT_RECRUITING": -0.4,
    "BOUNCE": -0.5,       
    "WRONG_PERSON": -1.0,  
}

DATA_ERROR_OUTCOMES = {"WRONG_PERSON", "BOUNCE"}

PRIOR_K = 5.0   


@dataclass
class Priors:
    global_mean: float
    by_supervisor: dict[str, float] = field(default_factory=dict)
    by_inst_area: dict[str, float] = field(default_factory=dict)
    by_area: dict[str, float] = field(default_factory=dict)
    flagged_for_review: list[dict] = field(default_factory=list)

    def score_multiplier(self, supervisor_id: str, institution: str, area: str) -> float:

        layers = [
            self.by_supervisor.get(supervisor_id),
            self.by_inst_area.get(_k(institution, area)),
            self.by_area.get(area),
        ]
        weights = [0.5, 0.3, 0.2]
        num = den = 0.0
        for val, w in zip(layers, weights):
            if val is not None:
                num += w * val
                den += w
        reward = (num / den) if den else self.global_mean
        return round(1.0 + 0.4 * reward, 3)


def _k(institution: str, area: str) -> str:
    return f"{institution}::{area}"


def _shrink(rewards: list[float], global_mean: float) -> float:
    n = len(rewards)
    if n == 0:
        return global_mean
    obs_mean = sum(rewards) / n
    return (n * obs_mean + PRIOR_K * global_mean) / (n + PRIOR_K)


def build_priors(csv_path: str | Path) -> Priors:
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))

    all_rewards: list[float] = []
    sup: dict[str, list[float]] = defaultdict(list)
    inst_area: dict[str, list[float]] = defaultdict(list)
    area: dict[str, list[float]] = defaultdict(list)
    flagged: list[dict] = []

    for r in rows:
        outcome = (r.get("outcome") or "").strip().upper()
        if outcome not in OUTCOME_REWARD:
            continue 
        reward = OUTCOME_REWARD[outcome]
        all_rewards.append(reward)
        sup[r["supervisor_id"]].append(reward)
        inst_area[_k(r.get("institution", ""), r.get("area", ""))].append(reward)
        area[r.get("area", "")].append(reward)

        if outcome in DATA_ERROR_OUTCOMES:
            flagged.append({
                "supervisor_id": r["supervisor_id"],
                "institution": r.get("institution", ""),
                "area": r.get("area", ""),
                "outcome": outcome,
            })

    g = (sum(all_rewards) / len(all_rewards)) if all_rewards else 0.0
    return Priors(
        global_mean=g,
        by_supervisor={k: _shrink(v, g) for k, v in sup.items()},
        by_inst_area={k: _shrink(v, g) for k, v in inst_area.items()},
        by_area={k: _shrink(v, g) for k, v in area.items()},
        flagged_for_review=flagged,
    )


def save_priors(priors: Priors, out_path: str | Path) -> None:
    Path(out_path).write_text(json.dumps(priors.__dict__, indent=2), encoding="utf-8")
