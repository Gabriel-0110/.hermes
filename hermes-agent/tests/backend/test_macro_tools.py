from __future__ import annotations

from backend.integrations import FredClient
from backend.tools.get_event_risk_macro_context import get_event_risk_macro_context
from backend.tools.get_macro_observations import get_macro_observations
from backend.tools.get_macro_regime_summary import get_macro_regime_summary
from backend.tools.get_macro_series import get_macro_series


def test_get_macro_series_fails_safely_without_credentials(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    payload = get_macro_series({"series_id": "UNRATE"})

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "provider_not_configured"


def test_get_macro_series_and_observations_are_normalized(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-fred-key")

    def fake_request(self, method, path, **kwargs):
        if path == "/series":
            return {
                "seriess": [
                    {
                        "id": "UNRATE",
                        "title": "Unemployment Rate",
                        "frequency": "Monthly",
                        "units": "Percent",
                        "seasonal_adjustment": "Seasonally Adjusted",
                        "popularity": 95,
                        "observation_start": "1948-01-01",
                        "observation_end": "2026-03-01",
                        "last_updated": "2026-04-03 07:36:05-05",
                        "notes": "Test note",
                    }
                ]
            }
        if path == "/series/observations":
            return {
                "observations": [
                    {"date": "2026-03-01", "value": "4.2", "realtime_start": "2026-04-15", "realtime_end": "2026-04-15"},
                    {"date": "2026-02-01", "value": ".", "realtime_start": "2026-04-15", "realtime_end": "2026-04-15"},
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(FredClient, "request", fake_request)

    series_payload = get_macro_series({"series_id": "UNRATE"})
    observations_payload = get_macro_observations({"series_id": "UNRATE", "limit": 2})

    assert series_payload["meta"]["ok"] is True
    assert series_payload["data"]["results"][0]["series_id"] == "UNRATE"
    assert observations_payload["data"]["series"]["title"] == "Unemployment Rate"
    assert observations_payload["data"]["observations"][0]["value"] == 4.2
    assert observations_payload["data"]["observations"][1]["value"] is None


def test_macro_regime_tools_build_synthesized_context(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-fred-key")

    metadata = {
        "UNRATE": {"id": "UNRATE", "title": "Unemployment Rate", "units": "Percent", "frequency": "Monthly", "seasonal_adjustment": "Seasonally Adjusted"},
        "SOFR180DAYAVG": {"id": "SOFR180DAYAVG", "title": "180-Day Average SOFR", "units": "Percent", "frequency": "Daily", "seasonal_adjustment": "Not Seasonally Adjusted"},
        "INDPRO": {"id": "INDPRO", "title": "Industrial Production: Total Index", "units": "Index 2017=100", "frequency": "Monthly", "seasonal_adjustment": "Seasonally Adjusted"},
    }
    observations = {
        "UNRATE": [{"date": "2026-03-01", "value": "4.0"}, {"date": "2026-02-01", "value": "4.1"}],
        "SOFR180DAYAVG": [{"date": "2026-04-15", "value": "4.3"}, {"date": "2026-04-14", "value": "4.4"}],
        "INDPRO": [{"date": "2026-03-01", "value": "103.0"}, {"date": "2026-02-01", "value": "102.6"}],
    }

    def fake_request(self, method, path, **kwargs):
        params = kwargs["params"]
        if path == "/series":
            return {"seriess": [metadata[params["series_id"]]]}
        if path == "/series/observations":
            return {"observations": observations[params["series_id"]]}
        raise AssertionError(path)

    monkeypatch.setattr(FredClient, "request", fake_request)

    summary = get_macro_regime_summary({})
    context = get_event_risk_macro_context({"event": "CPI release"})

    assert summary["meta"]["ok"] is True
    assert summary["data"]["risk_bias"] == "risk_on"
    assert len(summary["data"]["indicators"]) == 3
    assert context["meta"]["ok"] is True
    assert context["data"]["event"] == "CPI release"
    assert context["data"]["risk_bias"] == "risk_on"
