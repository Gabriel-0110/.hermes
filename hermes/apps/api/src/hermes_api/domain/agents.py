def list_agent_capabilities() -> list[dict[str, str]]:
    return [
        {
            "name": "orchestrator_trader",
            "role": "Primary coordinator for proposals and routing.",
        },
        {
            "name": "market_research",
            "role": "Builds market context and catalyst summaries.",
        },
        {
            "name": "portfolio_monitor",
            "role": "Tracks exposure, PnL, and portfolio drift.",
        },
        {
            "name": "risk_manager",
            "role": "Applies veto-capable risk policy checks.",
        },
        {
            "name": "strategy",
            "role": "Holds strategy templates and future backtesting hooks.",
        },
    ]
