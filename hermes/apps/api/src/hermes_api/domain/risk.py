def risk_posture() -> dict[str, object]:
    return {
        "default_mode": "human-reviewed",
        "policy_engine": "placeholder",
        "kill_switch": "not-implemented",
        "notes": "Risk manager should remain authoritative over execution approval.",
    }
