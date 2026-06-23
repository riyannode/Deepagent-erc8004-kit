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
    # x402 Batching (gated by X402_ENABLED + X402_EXPOSE_BATCH_*)
    "x402_batch_pay",
    "x402_batch_sell_settle",
    "x402_batch_balance",
    # x402 Nanopayment Standalone (gated by X402_ENABLED + X402_EXPOSE_NANO_*)
    "x402_nano_pay",
    "x402_nano_sell_settle",
    "x402_nano_balance",
]
