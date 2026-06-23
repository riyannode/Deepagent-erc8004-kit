"""MCP tool schemas — lists all available tool names for the Deep Agent."""

TOOL_NAMES = [
    # Identity (always available)
    "get_erc8004_config",
    "get_identity_status",
    "register_identity_once",
    "get_agent_metadata",
    "get_agent_wallet",
    # Reputation (read always, write gated)
    "get_reputation_summary",
    "get_feedback_for_agent",
    "record_reputation_feedback",
    # Validation (read always, write gated)
    "get_validation_status",
    "request_validation",
    "submit_validation_response",
    # x402 Payments (gated by X402_ENABLED)
    "x402_pay",
    "x402_sell_settle",
    "x402_balance",
]
