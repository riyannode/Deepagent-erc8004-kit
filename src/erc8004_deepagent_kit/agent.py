from __future__ import annotations

from deepagents import create_deep_agent

from .config import load_config
from .deepagent.system_prompt import SYSTEM_PROMPT
from .tools.identity import get_agent_metadata, get_agent_wallet, get_identity_status, register_identity_once
from .tools.registry_status import get_erc8004_config
from .tools.reputation import get_feedback_for_agent, get_reputation_summary, record_reputation_feedback
from .tools.validation import get_validation_status, request_validation, submit_validation_response
from .tools.x402 import x402_balance, x402_pay, x402_sell_settle


def build_erc8004_deep_agent(model: str | None = None):
    cfg = load_config()
    tools = [
        get_erc8004_config,
        get_identity_status,
        register_identity_once,
        get_agent_metadata,
        get_agent_wallet,
        get_reputation_summary,
        get_feedback_for_agent,
        get_validation_status,
    ]

    if cfg.enable_validation_writes and cfg.expose_validation_write_tools_to_agent:
        tools.extend([request_validation, submit_validation_response])

    if cfg.enable_reputation_writes and cfg.expose_reputation_write_tools_to_agent:
        tools.append(record_reputation_feedback)

    # x402 payment tools (buyer + seller + balance)
    if cfg.x402_enabled:
        tools.extend([x402_pay, x402_sell_settle, x402_balance])

    return create_deep_agent(
        model=model or cfg.deepagent_model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
