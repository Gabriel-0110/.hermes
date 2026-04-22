"""Scoring helpers for replay outcomes."""

from __future__ import annotations

from typing import Any

from .models import EvaluationRuleConfig, EvaluationScoreRecord, ReplayCase, ReplayResultRecord


def _bool_score(passed: bool) -> float:
    return 1.0 if passed else 0.0


def _safe_get_forward_return(case: ReplayCase) -> float | None:
    value = case.expected_outcome.get("forward_return")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_replay_result(
    *,
    replay_run_id: str,
    replay_case: ReplayCase,
    replay_result: ReplayResultRecord,
    rules: EvaluationRuleConfig,
) -> list[EvaluationScoreRecord]:
    scores: list[EvaluationScoreRecord] = []
    expected_decision = rules.approved_vs_rejected_expected
    actual_decision = (replay_result.decision or "").lower()

    if expected_decision is not None:
        passed = actual_decision == expected_decision.lower()
        scores.append(
            EvaluationScoreRecord(
                replay_run_id=replay_run_id,
                replay_result_id=replay_result.id,
                replay_case_id=replay_case.id,
                rule_name="approved_vs_rejected",
                metric_name="decision_match",
                value=_bool_score(passed),
                passed=passed,
                detail=f"expected={expected_decision} actual={actual_decision or 'unknown'}",
            )
        )

    if rules.execution_expected is not None:
        passed = replay_result.should_execute is rules.execution_expected
        scores.append(
            EvaluationScoreRecord(
                replay_run_id=replay_run_id,
                replay_result_id=replay_result.id,
                replay_case_id=replay_case.id,
                rule_name="execution_vs_no_execution",
                metric_name="execution_match",
                value=_bool_score(passed),
                passed=passed,
                detail=f"expected_execute={rules.execution_expected} actual_execute={replay_result.should_execute}",
            )
        )

    forward_return = _safe_get_forward_return(replay_case)
    if forward_return is not None:
        passed = True if rules.min_forward_return is None else forward_return >= rules.min_forward_return
        scores.append(
            EvaluationScoreRecord(
                replay_run_id=replay_run_id,
                replay_result_id=replay_result.id,
                replay_case_id=replay_case.id,
                rule_name="forward_return",
                metric_name="forward_return",
                value=forward_return,
                passed=passed,
                detail=(
                    f"horizon={rules.forward_return_horizon_bars} "
                    f"min_required={rules.min_forward_return} actual={forward_return}"
                ),
                metadata={"horizon_bars": rules.forward_return_horizon_bars},
            )
        )

    if rules.require_risk_compliance:
        risk_output = replay_result.state.get("risk_output") or {}
        approved = bool(risk_output.get("approved"))
        blocking_reasons = risk_output.get("blocking_reasons") or []
        passed = approved or bool(blocking_reasons)
        scores.append(
            EvaluationScoreRecord(
                replay_run_id=replay_run_id,
                replay_result_id=replay_result.id,
                replay_case_id=replay_case.id,
                rule_name="risk_compliance",
                metric_name="risk_review_present",
                value=_bool_score(passed),
                passed=passed,
                detail=f"approved={approved} blocking_reasons={len(blocking_reasons)}",
            )
        )

    if rules.max_latency_ms is not None and replay_result.latency_ms is not None:
        passed = replay_result.latency_ms <= rules.max_latency_ms
        scores.append(
            EvaluationScoreRecord(
                replay_run_id=replay_run_id,
                replay_result_id=replay_result.id,
                replay_case_id=replay_case.id,
                rule_name="latency",
                metric_name="latency_ms",
                value=float(replay_result.latency_ms),
                passed=passed,
                detail=f"max_latency_ms={rules.max_latency_ms} actual={replay_result.latency_ms}",
            )
        )

    return scores


def summarize_scores(scores: list[EvaluationScoreRecord]) -> dict[str, Any]:
    if not scores:
        return {"score_count": 0, "pass_rate": None, "metrics": {}}
    metrics: dict[str, Any] = {}
    for score in scores:
        metrics.setdefault(score.rule_name, []).append(score.value)
    pass_rate = sum(1 for score in scores if score.passed) / len(scores)
    return {
        "score_count": len(scores),
        "pass_rate": round(pass_rate, 4),
        "metrics": {name: values[-1] if len(values) == 1 else values for name, values in metrics.items()},
    }
