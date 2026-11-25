"""Trusted identity context supplied by the authenticated application boundary."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TrustedUserContext(BaseModel):
    """Validated context returned by the Backend's authenticated ``/auth/me`` flow."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    id: UUID
    email: str
    full_name: str
    org_id: UUID
    customer_id: UUID | None
    role: str
    permissions: tuple[str, ...]
    authorized_kb_tiers: tuple[str, ...]
