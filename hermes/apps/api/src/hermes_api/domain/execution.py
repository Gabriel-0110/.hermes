def execution_capabilities() -> dict[str, object]:
    return {
        "mode": "scaffolded",
        "connectors": ["paper-trading", "exchange-adapter-placeholder"],
        "governance": "required-before-live-execution",
    }
