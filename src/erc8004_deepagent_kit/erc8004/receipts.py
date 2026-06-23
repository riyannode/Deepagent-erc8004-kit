from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class IdentityReceipt:
    status: str
    source: str
    chain_id: int
    identity_registry: str
    agent_id: str | None
    wallet_address: str
    agent_uri: str | None
    tx_hash: str | None
    explorer_url: str | None = None
    duplicate_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
