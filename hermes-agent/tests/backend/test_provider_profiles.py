from backend.integrations.provider_profiles import PROVIDER_PROFILES


def test_provider_profiles_cover_requested_integrations():
    assert {
        "coingecko",
        "coinmarketcap",
        "twelvedata",
        "fred",
        "cryptopanic",
        "newsapi",
        "etherscan",
        "lunarcrush",
        "nansen",
        "bitmart",
        "defillama",
    }.issubset(set(PROVIDER_PROFILES))


def test_bitmart_provider_profile_matches_execution_surface():
    profile = PROVIDER_PROFILES["bitmart"]

    assert profile.name == "BITMART"
    assert profile.category == "execution"
    assert profile.env_var == "BITMART_API_KEY"
    assert profile.internal_tools == [
        "get_exchange_balances",
        "get_open_orders",
        "place_order",
        "cancel_order",
        "get_order_history",
        "get_trade_history",
        "get_execution_status",
    ]
    assert profile.benefiting_agents == ["orchestrator_trader", "portfolio_monitor", "risk_manager"]


def test_provider_profiles_expose_backend_only_env_vars():
    for profile in PROVIDER_PROFILES.values():
        if profile.auth_method != "No auth (free public API)":
            assert profile.env_var
            assert profile.env_var == profile.env_var.upper()
        assert profile.internal_tools
        assert profile.benefiting_agents


def test_defillama_provider_profile_matches_defi_surface():
    profile = PROVIDER_PROFILES["defillama"]

    assert profile.name == "DEFILLAMA"
    assert profile.category == "defi intelligence"
    assert profile.auth_method == "No auth (free public API)"
    assert profile.env_var == ""
    assert profile.internal_tools == [
        "get_defi_protocols",
        "get_defi_protocol_details",
        "get_defi_chain_overview",
        "get_defi_yields",
        "get_defi_dex_overview",
        "get_defi_fees_overview",
        "get_defi_open_interest",
        "get_defi_regime_summary",
    ]
    assert profile.benefiting_agents == ["market_researcher", "risk_manager", "strategy_agent"]
