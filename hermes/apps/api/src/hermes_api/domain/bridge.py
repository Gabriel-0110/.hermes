from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BridgeKillSwitchState(BaseModel):
    model_config = ConfigDict(extra="allow")

    active: bool = False
    reason: str | None = None
    operator: str | None = None
    updated_at: str | None = None
