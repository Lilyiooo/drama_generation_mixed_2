#!/usr/bin/env python3
"""Resume a PG19 eight-field outline review from its retained round-one rewrite."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from drama_local import runtime as context
from drama_local.runtime import atomic_json
from service.drama_by_creativity.eight_field_episode_outline import (
    EIGHT_REVIEW_PROMPT,
    EIGHT_REWRITE_PROMPT,
    FIELDS,
    validate_eight_fields,
)
from service.drama_by_creativity.episode_outline_review import validate_review
from service.drama_by_creativity.realtime_output import save_realtime
from service.drama_by_creativity.stage_episode_planning import _validated_call, make_outline_llm


ALIASES = {
    "core_pattern": "core_plot",
    "character_relationships": "relationship_changes",
    "highlikes": "highlights",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_round_one(value):
    if not isinstance(value, list):
        raise ValueError("Retained round-one rewrite is not an episode array")
    normalized = copy.deepcopy(value)
    changes = []
    for episode in normalized:
        if not isinstance(episode, dict):
            raise ValueError("Retained round-one rewrite contains a non-object episode")
        for source, target in ALIASES.items():
            if source in episode and target not in episode:
                episode[target] = episode.pop(source)
                changes.append({"episode_id": episode.get("episode_id"), "source": source, "target": target})
        if set(episode) != FIELDS:
            raise ValueError(
                f"Episode {episode.get('episode_id')} remains invalid after safe aliases: "
                f"missing={sorted(FIELDS - set(episode))} extra={sorted(set(episode) - FIELDS)}"
            )
    validate_eight_fields(normalized, 1, len(normalized))
    return normalized, changes


async def recover(directory: Path) -> None:
    os.environ["DRAMA_OUTPUT_DIR"] = str(directory)
    attempt = load(directory / "04_stage_plan/attempts/outline_round_01_rewrite_03.json")
    current, changes = normalize_round_one(attempt["result"])
    initial = load(directory / "04_episode_outline_review/before.json")
    first_review = load(directory / "04_episode_outline_review/round_01/review.json")
    background = load(directory / "04_episode_outline_review/background.json")
    validate_eight_fields(initial, 1, len(initial))
    validate_review(first_review, initial)
    total = len(current)
    save_realtime(["04_episode_outline_review", "round_01", "after.json"], current)
    candidates = [{
        "version": 0,
        "score": first_review["total_score"],
        "episodes": copy.deepcopy(initial),
        "review": copy.deepcopy(first_review),
        "outline_path": "round_01/before.json",
        "review_path": "round_01/review.json",
    }]
    status = {
        "status": "running",
        "rounds": 3,
        "completed_rounds": 1,
        "recovery": "retained_round_01_rewrite_03_safe_aliases",
        "normalizations": changes,
    }
    save_realtime(["04_episode_outline_review", "status.json"], status)
    ctx = context.Context()
    for round_id in (2, 3):
        folder = ["04_episode_outline_review", f"round_{round_id:02d}"]
        status.update(current_round=round_id, phase="review")
        save_realtime(["04_episode_outline_review", "status.json"], status)
        save_realtime(folder + ["before.json"], current)
        params = {
            "Total": str(total),
            "Original": json.dumps(current, ensure_ascii=False),
            "Background": json.dumps(background, ensure_ascii=False),
        }
        review = await _validated_call(
            ctx,
            make_outline_llm(EIGHT_REVIEW_PROMPT),
            params,
            f"第{round_id}/3轮全剧问题评审",
            f"outline_round_{round_id:02d}_review",
            lambda value: validate_review(value, current),
        )
        save_realtime(folder + ["review_model_result.json"], review)
        save_realtime(folder + ["review.json"], review)
        candidates.append({
            "version": round_id - 1,
            "score": review["total_score"],
            "episodes": copy.deepcopy(current),
            "review": copy.deepcopy(review),
            "outline_path": f"round_{round_id:02d}/before.json",
            "review_path": f"round_{round_id:02d}/review.json",
        })
        status["phase"] = "rewrite"
        save_realtime(["04_episode_outline_review", "status.json"], status)
        revised = await _validated_call(
            ctx,
            make_outline_llm(EIGHT_REWRITE_PROMPT),
            dict(params, Review=json.dumps(review, ensure_ascii=False)),
            f"第{round_id}/3轮完整大纲重写",
            f"outline_round_{round_id:02d}_rewrite",
            lambda value: validate_eight_fields(value, 1, total),
        )
        save_realtime(folder + ["after.json"], revised)
        current = copy.deepcopy(revised)
        status["completed_rounds"] = round_id
        save_realtime(["04_episode_outline_review", "status.json"], status)

    status["phase"] = "final_review"
    save_realtime(["04_episode_outline_review", "status.json"], status)
    final_params = {
        "Total": str(total),
        "Original": json.dumps(current, ensure_ascii=False),
        "Background": json.dumps(background, ensure_ascii=False),
    }
    final_review = await _validated_call(
        ctx,
        make_outline_llm(EIGHT_REVIEW_PROMPT),
        final_params,
        "第三轮重写结果最终评审与评分",
        "outline_final_review",
        validate_review,
    )
    save_realtime(["04_episode_outline_review", "final_review.json"], final_review)
    candidates.append({
        "version": 3,
        "score": final_review["total_score"],
        "episodes": copy.deepcopy(current),
        "review": copy.deepcopy(final_review),
        "outline_path": "round_03/after.json",
        "review_path": "final_review.json",
    })
    best = max(candidates, key=lambda item: item["score"])
    selection = {
        "selected_version": best["version"],
        "selected_score": best["score"],
        "tie_break": "earliest_version",
        "recovery": "retained_round_01_rewrite_03_safe_aliases",
        "normalizations": changes,
        "candidates": [
            {key: value for key, value in item.items() if key not in ("episodes", "review")}
            for item in candidates
        ],
    }
    selected = best["episodes"]
    save_realtime(["04_episode_outline_review", "selection.json"], selection)
    save_realtime(["04_episode_outline_review", "review.json"], best["review"])
    save_realtime(["04_episode_outline_review", "after.json"], selected)
    plan = load(directory / "04_stage_plan/stage_plan.json")["stages"]
    for index, allocation in enumerate(plan, 1):
        start = allocation["start_episode_id"]
        end = allocation["end_episode_id"]
        save_realtime(
            ["04_episode_outline", f"chunk_{index:02d}_ep{start:02d}-{end:02d}.json"],
            selected[start - 1:end],
        )
    save_realtime(["episode_outlines.json"], selected)
    save_realtime(["04_stage_plan", "completion.json"], {"status": "complete", "episode_count": total})
    status.update(
        status="complete",
        phase="complete",
        selected_version=best["version"],
        selected_score=best["score"],
    )
    save_realtime(["04_episode_outline_review", "status.json"], status)
    atomic_json(directory / "pipeline_result.json", {
        "recovery": selection["recovery"],
        "episode_count": total,
        "selected_version": best["version"],
        "selected_score": best["score"],
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if (directory / "04_stage_plan/completion.json").is_file():
        return
    asyncio.run(recover(directory))


if __name__ == "__main__":
    main()
