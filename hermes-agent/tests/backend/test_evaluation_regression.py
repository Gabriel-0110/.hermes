from __future__ import annotations

from backend.evaluation import ComparisonDimension, compare_replay_runs
from backend.evaluation.models import EvaluationScoreRecord, ReplayResultRecord


def test_compare_replay_runs_reports_candidate_improvement() -> None:
    comparison = compare_replay_runs(
        baseline_replay_run_id="run_a",
        candidate_replay_run_id="run_b",
        comparison_type=ComparisonDimension.MODEL,
        baseline_results=[
            ReplayResultRecord(
                replay_run_id="run_a",
                replay_case_id="case_1",
                decision="reject",
                status="rejected",
            )
        ],
        candidate_results=[
            ReplayResultRecord(
                replay_run_id="run_b",
                replay_case_id="case_1",
                decision="execute",
                status="approved",
            )
        ],
        baseline_scores=[
            EvaluationScoreRecord(
                replay_run_id="run_a",
                replay_result_id="result_a",
                replay_case_id="case_1",
                rule_name="approved_vs_rejected",
                metric_name="decision_match",
                value=0.0,
                passed=False,
            )
        ],
        candidate_scores=[
            EvaluationScoreRecord(
                replay_run_id="run_b",
                replay_result_id="result_b",
                replay_case_id="case_1",
                rule_name="approved_vs_rejected",
                metric_name="decision_match",
                value=1.0,
                passed=True,
            )
        ],
        baseline_label="model-a",
        candidate_label="model-b",
    )

    assert comparison.status == "candidate_improved"
    assert comparison.summary["candidate_better_cases"] == 1
    assert comparison.summary["decision_changes"][0]["candidate_decision"] == "execute"
