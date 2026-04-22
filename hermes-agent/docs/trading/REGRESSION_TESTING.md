# Regression Testing

## Purpose

Regression testing compares replay behavior over time without touching live execution.

The harness supports comparison across:

- model A vs model B
- prompt version A vs prompt version B
- workflow version A vs workflow version B

## Recommended Workflow

1. Build a stable set of replay cases from historical TradingView alerts.
2. Run the baseline configuration and persist replay artifacts.
3. Run the candidate configuration against the same replay cases.
4. Compare replay runs with `backend.evaluation.regression.compare_replay_runs`.
5. Review:
   - decision changes
   - score deltas by rule
   - candidate-better vs baseline-better counts

## What Counts as a Regression

Typical regressions include:

- an expected approval becoming a rejection
- an expected execution becoming no-execution
- poorer forward-return score distribution
- missing risk review evidence
- materially higher latency

## Comparison Output

The regression summary captures:

- shared case count
- decision changes by replay case
- average delta by scoring rule
- number of cases where the candidate is better
- number of cases where the baseline is better
- overall status such as:
  - `candidate_improved`
  - `candidate_regressed`
  - `no_material_change`

## Practical Guidance

- Keep replay cases stable while comparing versions.
- Avoid mixing multiple dimensions in one comparison if attribution matters.
- Start with a small curated case set before scaling to a broader regression suite.
- Treat this v1 as a workflow-quality gate, not a portfolio PnL simulator.
