from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.execution import get_execution_clients, reconcile_exchange_balances
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetExchangeBalancesInput(BaseModel):
    venue: str | None = Field(default=None, min_length=2, max_length=32)
    venues: list[str] | None = None
    aggregate: bool = False


def get_exchange_balances(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetExchangeBalancesInput, payload or {})
        clients = get_execution_clients(venue=args.venue, venues=args.venues, configured_only=False)
        configured_clients = [client for client in clients if client.configured]
        if not configured_clients:
            client = clients[0] if clients else get_execution_clients(configured_only=False)[0]
            missing = ", ".join(client.credential_env_names)
            return envelope(
                "get_exchange_balances",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {"error": "provider_not_configured", "detail": f"{client.provider.name} credentials are not configured in the backend environment."},
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )

        if len(configured_clients) == 1 and not args.aggregate and not args.venues:
            balances = configured_clients[0].get_exchange_balances()
            return envelope(
                "get_exchange_balances",
                [provider_ok(configured_clients[0].provider.name)],
                balances.model_dump(mode="json"),
            )

        reconciliation = reconcile_exchange_balances(venue=args.venue, venues=args.venues)
        providers = [provider_ok(client.provider.name) for client in configured_clients]
        return envelope("get_exchange_balances", providers, reconciliation, warnings=reconciliation.get("warnings") or [])

    return run_tool("get_exchange_balances", _run)