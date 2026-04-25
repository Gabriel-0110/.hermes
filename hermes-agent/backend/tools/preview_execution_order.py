from __future__ import annotations

from backend.integrations.execution import VenueExecutionClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate
from backend.tools.place_order import PlaceOrderInput


def preview_execution_order(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(PlaceOrderInput, payload or {})
        selected_venue = (args.venue or (args.venues[0] if args.venues else "bitmart")).strip().lower()
        warnings: list[str] = []
        if args.venues and not args.venue:
            warnings.append(
                "Preview mode uses the first requested venue; smart venue selection is not applied during dry-run payload generation."
            )

        client = VenueExecutionClient(selected_venue)
        if not client.configured:
            missing = ", ".join(client.credential_env_names)
            return envelope(
                "preview_execution_order",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {
                    "error": "provider_not_configured",
                    "detail": f"{client.provider.name} credentials are not configured in the backend environment.",
                },
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )

        preview = client.preview_order_request(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            amount=args.amount,
            price=args.price,
            stop_loss_price=args.stop_loss_price,
            take_profit_price=args.take_profit_price,
            leverage=args.leverage,
            margin_mode=args.margin_mode,
            client_order_id=args.client_order_id,
            time_in_force=args.time_in_force,
            post_only=args.post_only,
            reduce_only=args.reduce_only,
            position_side=args.position_side,
        )
        return envelope(
            "preview_execution_order",
            [provider_ok(client.provider.name)],
            {
                "exchange": client.provider.name,
                "venue": selected_venue,
                "routing": {
                    "mode": "preview",
                    "selected_venue": selected_venue,
                },
                "preview": preview,
            },
            warnings=warnings,
        )

    return run_tool("preview_execution_order", _run)