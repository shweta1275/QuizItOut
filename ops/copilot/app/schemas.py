from pydantic import BaseModel, Field


class AlertItem(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None


class AlertPayload(BaseModel):
    """Alertmanager webhook body (only the fields the copilot reads)."""

    alerts: list[AlertItem] = Field(default_factory=list)
