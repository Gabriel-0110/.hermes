"""Regression comparison utilities for replay runs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import ComparisonDimension, EvaluationScoreRecord, RegressionComparisonRecord, ReplayResultRecord


def _index_scores(scores: list[EvaluationScoreRecord]) -> dict[tuple[str, str], EvaluationScoreRecord]:
    return {(score.replay_case_id, score.rule_name): score for score in scores}


def compare_replay_runs(
    *,
    baseline_replay_run_id: str,
    candidate_replay_run_id: str,
    comparison_type: ComparisonDimension,
    baseline_results: list[ReplayResultRecord],
    candidate_results: list[ReplayResultRecord],
    baseline_scores: list[EvaluationScoreRecord],
    candidate_scores: list[EvaluationScoreRecord],
    baseline_label: str | None = None,
    candidate_label: str | None = None,
) -> RegressionComparisonRecord:
    baseline_result_map = {result.replay_case_id: result for result in baseline_results}
    candidate_result_map = {result.replay_case_id: result for result in candidate_results}
    shared_case_ids = sorted(set(baseline_result_map) & set(candidate_result_map))

    baseline_score_map = _index_scores(baseline_scores)
    candidate_score_map = _index_scores(candidate_scores)

    decision_changes = []
    score_deltas: dict[str, list[float]] = defaultdict(list)
    candidate_better = 0
    baseline_better = 0

    for case_id in shared_case_ids:
        baseline_result = baseline_result_map[case_id]
        candidate_result = candidate_result_map[case_id]
        if baseline_result.decision != candidate_result.decision:
            decision_changes.append(
                {
                    "replay_case_id": case_id,
                    "baseline_decision": baseline_result.decision,
                    "candidate_decision": candidate_result.decision,
                }
            )

        rules = {rule_name for candidate_case_id, rule_name in baseline_score_map if candidate_case_id == case_id}
        rules |= {rule_name for candidate_case_id, rule_name in candidate_score_map if candidate_case_id == case_id}
        baseline_case_total = 0.0
        candidate_case_total = 0.0
        for rule_name in sorted(rules):
            base = baseline_score_map.get((case_id, rule_name))
            cand = candidate_score_map.get((case_id, rule_name))
            if base is None or cand is None:
                continue
            delta = cand.value - base.value
            score_deltas[rule_name].append(delta)
            baseline_case_total += base.value
            candidate_case_total += cand.value

        if candidate_case_total > baseline_case_total:
            candidate_better += 1
        elif baseline_case_total > candidate_case_total:
            baseline_better += 1

    avg_delta_by_rule = {
        rule_name: round(sum(deltas) / len(deltas), 6)
        for rule_name, deltas in score_deltas.items()
        if deltas
    }
    summary: dict[str, Any] = {
        "shared_case_count": len(shared_case_ids),
        "decision_changes": decision_changes,
        "candidate_better_cases": candidate_better,
        "baseline_better_cases": baseline_better,
        "avg_delta_by_rule": avg_delta_by_rule,
    }
    status = "candidate_improved" if candidate_better > baseline_better else "candidate_regressed" if baseline_better > candidate_better else "no_material_change"

    return RegressionComparisonRecord(
        baseline_replay_run_id=baseline_replay_run_id,
        candidate_replay_run_id=candidate_replay_run_id,
        comparison_type=comparison_type,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        status=status,
        summary=summary,
    )
