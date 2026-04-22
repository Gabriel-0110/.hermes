# Trading Graph

## Node Flow

The first trading graph is implemented with `pydantic_graph.Graph` and these nodes:

1. `IngestSignalNode`
2. `MarketResearchNode`
3. `ResearchDecisionNode`
4. `StrategyPlanningNode`
5. `StrategyDecisionNode`
6. `RiskReviewNode`
7. `RiskDecisionNode`
8. `FinalOrchestrationDecisionNode`
9. `RejectTerminalNode`

## Branch Labels

- `reject`: terminate the workflow with a typed `OrchestratorOutput`
- `continue`: move forward to the next planning / review stage
- `execute`: move into final orchestration with an execution-ready route hint

## Research Aggregation

`MarketResearchNode` performs the only parallel fan-out in v1:

- TradingView alert context
- market overview
- macro regime
- event risk
- onchain signal summary
- volatility metrics
- portfolio state

Those calls are executed concurrently with `asyncio.create_task()` and then synthesized into `ResearcherOutput`.

## Local Validation

Run:

```bash
python3 -m backend.workflows.validate
```

Optional live model:

```bash
python3 -m backend.workflows.validate --model openai:gpt-5.2
```

If `--model` is omitted, the runner still exercises `pydantic_ai` output validation through `TestModel`.
