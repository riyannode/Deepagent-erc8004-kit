from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredIdentity:
    chain_id: int
    identity_registry: str
    agent_key: str
    wallet_address: str
    agent_id: str
    agent_uri: str
    tx_hash: str
    source: str
    created_at: str
