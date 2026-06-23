from __future__ import annotations

from langchain_core.tools import tool

from ..config import load_config


def _get_erc8004_config_impl() -> dict:
    cfg = load_config()
    return {
        "network_profile": cfg.network_profile,
        "chain_id": cfg.chain_id,
        "blockchain": cfg.blockchain,
        "rpc_url": cfg.rpc_url,
        "explorer_url": cfg.explorer_url,
        "identity_registry": cfg.identity_registry,
        "reputation_registry": cfg.reputation_registry,
        "validation_registry": cfg.validation_registry,
        "from_block": cfg.from_block,
        "event_scan_block_range": cfg.event_scan_block_range,
        "execution_mode": "live_circle_only",
        "verify_chain_id": cfg.verify_chain_id,
        "identity_store_path": str(cfg.identity_store_path),
        "writes": {
            "identity_registration": True,
            "reputation": cfg.enable_reputation_writes,
            "validation": cfg.enable_validation_writes,
        },
    }


@tool
def get_erc8004_config() -> dict:
    """Return safe ERC-8004 network and registry configuration. Does not reveal secrets."""
    return _get_erc8004_config_impl()
