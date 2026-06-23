from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from web3 import Web3

from .config import load_config
from .erc8004.registry_clients import IdentityRegistryClient
from .store.sqlite_store import SqliteIdentityStore
from .tools.identity import _get_identity_status_impl, _register_identity_once_impl
from .tools.registry_status import _get_erc8004_config_impl

app = typer.Typer(no_args_is_help=False, add_completion=False)


def _print(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, sort_keys=True))


def _safe_check(name: str, fn, *, required: bool = True) -> dict:
    try:
        value = fn()
        if isinstance(value, dict):
            return {"name": name, "ok": bool(value.get("ok", True)), **value, "required": required}
        return {"name": name, "ok": bool(value), "value": value, "required": required}
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc), "required": required}


@app.command()
def config() -> None:
    """Print safe ERC-8004 registry config. No secrets."""
    _print(_get_erc8004_config_impl())


@app.command()
def doctor() -> None:
    """Validate live Docker/env/RPC configuration without sending a transaction."""
    cfg = load_config()
    client = IdentityRegistryClient(
        cfg.rpc_url,
        cfg.identity_registry,
        cfg.from_block,
        cfg.event_scan_block_range,
        receipt_poll_seconds=cfg.receipt_poll_seconds,
        receipt_max_polls=cfg.receipt_max_polls,
    )

    checks = [
        {"name": "execution_mode", "ok": True, "value": "live_circle_only", "required": True},
        {"name": "identity_registry_address", "ok": Web3.is_address(cfg.identity_registry), "value": cfg.identity_registry, "required": True},
        {"name": "reputation_registry_address", "ok": Web3.is_address(cfg.reputation_registry), "value": cfg.reputation_registry, "required": True},
        {"name": "validation_registry_address", "ok": Web3.is_address(cfg.validation_registry), "value": cfg.validation_registry, "required": True},
        {"name": "dcw_wallet_address_present", "ok": bool(cfg.dcw_wallet_address), "required": True},
        {"name": "circle_api_key_present", "ok": bool(cfg.circle_api_key), "required": True},
        {"name": "circle_entity_secret_present", "ok": bool(cfg.circle_entity_secret), "required": True},
        {"name": "identity_store_parent_exists", "ok": cfg.identity_store_path.parent.exists() or cfg.identity_store_path.parent == Path('/data'), "value": str(cfg.identity_store_path), "required": True},
        {"name": "circle_state_dir_parent_exists", "ok": cfg.circle_execution_state_dir.parent.exists() or cfg.circle_execution_state_dir.parent == Path('/data'), "value": str(cfg.circle_execution_state_dir), "required": True},
        _safe_check("rpc_chain_id", lambda: {"ok": int(client.w3.eth.chain_id) == cfg.chain_id, "value": int(client.w3.eth.chain_id), "expected": cfg.chain_id}),
        _safe_check("identity_registry_bytecode", lambda: {"ok": client.contract_code_size() > 0, "bytes": client.contract_code_size()}),
        _safe_check("latest_block", lambda: {"ok": client.w3.eth.block_number >= cfg.from_block, "value": int(client.w3.eth.block_number), "from_block": cfg.from_block}),
    ]
    ok = all(bool(c.get("ok")) for c in checks if c.get("required", True))
    _print({"ok": ok, "mode": "live_circle_only", "checks": checks, "sends_transaction": False})
    if not ok:
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Check whether the configured DCW wallet already has an SDK-managed or on-chain ERC-8004 identity."""
    _print(_get_identity_status_impl())


@app.command()
def register(
    agent_key: Optional[str] = typer.Option(None, help="Stable developer-defined agent key."),
    name: Optional[str] = typer.Option(None, help="Agent display name."),
    description: Optional[str] = typer.Option(None, help="Agent description."),
    image: Optional[str] = typer.Option(None, help="Agent image URL."),
) -> None:
    """Register exactly one ERC-8004 identity for the configured Circle DCW wallet."""
    _print(
        _register_identity_once_impl(
            agent_key=agent_key,
            name=name,
            description=description,
            image=image,
        )
    )


@app.command("clear-expired-locks")
def clear_expired_locks() -> None:
    """Clear only expired local registration locks. This never sends a transaction."""
    cfg = load_config()
    store = SqliteIdentityStore(cfg.identity_store_path)
    cleared = store.clear_expired_locks()
    _print({"ok": True, "cleared": cleared, "sends_transaction": False})


@app.command("agent-register")
def agent_register() -> None:
    """Ask the LangChain Deep Agent to register identity once using bounded tools."""
    cfg = load_config()
    from .agent import build_erc8004_deep_agent

    agent = build_erc8004_deep_agent()
    result = agent.invoke(
        {
            "messages": (
                "Register this ERC-8004 agent identity if it does not already exist. "
                f"Use agent_key={cfg.agent_key!r}, name={cfg.agent_name!r}. "
                "Return the structured receipt from the tool."
            )
        }
    )
    _print(result)


if __name__ == "__main__":
    app()
