from __future__ import annotations

from backend.strategies.chronos_scoring import get_chronos_alignment_score


def test_chronos_alignment_score_uses_cache(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'chronos_cache.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    calls: list[dict[str, object]] = []

    def fake_projection(payload: dict) -> dict:
        calls.append(payload)
        return {
            "meta": {"ok": True, "warnings": [], "providers": [{"provider": "amazon_chronos_2", "ok": True}]},
            "data": {
                "symbol": payload["symbol"],
                "interval": payload["interval"],
                "history_points": 120,
                "last_close": 100.0,
                "horizon": payload["horizon"],
                "forecast_model": "amazon_chronos_2",
                "final_low": 99.0,
                "final_median": 105.0,
                "final_high": 110.0,
                "scenarios": [{"step": payload["horizon"], "low": 99.0, "median": 105.0, "high": 110.0}],
            },
        }

    monkeypatch.setattr("backend.strategies.chronos_scoring.get_forecast_projection", fake_projection)

    first = get_chronos_alignment_score("BTCUSDT", "long", interval="4h", horizon=6, database_url=database_url)
    second = get_chronos_alignment_score("BTCUSDT", "long", interval="4h", horizon=6, database_url=database_url)
    short_bias = get_chronos_alignment_score("BTCUSDT", "short", interval="4h", horizon=6, database_url=database_url)

    assert len(calls) == 1
    assert first.cached is False
    assert second.cached is True
    assert first.score > 0.5
    assert second.score == first.score
    assert short_bias.score < 0.5
