# erc8004-deepagent-kit

Docker-first standalone SDK/plugin for building a LangChain Deep Agent that can register exactly one ERC-8004 identity through a configured Circle Developer-Controlled Wallet, then expose ERC-8004 reputation and validation read tools. ERC-8183 and x402 are included only as disabled future plugin stubs.

This package intentionally does not use project-specific branding. It is intended as a global developer kit for the Arc ecosystem and Circle DCW flows.

## Live-only safety model

This build is live-only. There is no offline executor and no fake transaction path.

The Deep Agent never receives raw wallet access. The LLM sees bounded tools only. Contract writes are enforced by `wallet/policy.py`.

Default Deep Agent tools:

```txt
get_erc8004_config
get_identity_status
register_identity_once
get_agent_metadata
get_agent_wallet
get_reputation_summary
get_feedback_for_agent
get_validation_status
```

The only default write-capable tool is:

```txt
register_identity_once
```

The kit blocks duplicate registration by:

1. SQLite unique indexes.
2. Wallet/agent-key binding checks.
3. Registration lock with TTL.
4. On-chain scan for prior ERC-721 mint/registration by configured wallet.
5. Tx receipt parsing from the exact Circle-returned tx hash.
6. Fail-closed duplicate detection if more than one on-chain identity is detected for the same wallet.
7. Circle execution state file under `/data/circle_executions` for recovery after ambiguous Circle/API timeout.

This SDK cannot prevent a wallet from calling the ERC-8004 registry directly outside this SDK. It prevents duplicate registration through this SDK and detects existing on-chain registrations when the configured RPC/from-block can see them.

## Official references

- LangChain Deep Agents: https://github.com/langchain-ai/deepagents
- ERC-8004 EIP: https://eips.ethereum.org/EIPS/eip-8004
- Arc ERC-8004 + Circle DCW quickstart: https://docs.arc.io/arc/tutorials/register-your-first-ai-agent
- Circle Developer-Controlled Wallets SDK is used through the Node sidecar in `scripts/circle_execute_contract.mjs`.

## Docker live quickstart

```bash
unzip erc8004-deepagent-kit.live-production.zip
cd erc8004-deepagent-kit
cp .env.example .env
mkdir -p data
```

Edit `.env`:

```env
CIRCLE_API_KEY=...
CIRCLE_ENTITY_SECRET=...
DCW_WALLET_ADDRESS=0xYourCircleDcwWallet
AGENT_KEY=my-agent
AGENT_NAME=My ERC-8004 Agent
AGENT_DESCRIPTION=My global ERC-8004 agent
AGENT_IMAGE=https://example.com/agent.png
AGENT_SERVICES_JSON=[]
```

Build:

```bash
docker compose build
```

Preflight. This sends no transaction:

```bash
docker compose run --rm erc8004-live doctor
```

Check current identity state. This sends no transaction:

```bash
docker compose run --rm erc8004-live status
```

Register once. This can send a real Circle DCW contract execution transaction:

```bash
docker compose run --rm erc8004-live register
```

Run again to prove idempotency:

```bash
docker compose run --rm erc8004-live register
```

The second command must return `already_registered`, `already_registered_onchain`, or `blocked_duplicate_onchain_identities`. It must not create another Circle transaction.

## Optional Deep Agent mode

Direct CLI commands do not need an LLM. To route through the LangChain Deep Agent harness:

```bash
docker compose run --rm erc8004-live agent-register
```

Set an LLM key first:

```env
DEEPAGENT_MODEL=anthropic:claude-sonnet-4-6
ANTHROPIC_API_KEY=...
```

## Production verification checklist

For live readiness, verify all of these:

```txt
1. docker compose build succeeds.
2. doctor returns ok=true.
3. doctor verifies chain_id=5042002.
4. doctor verifies bytecode exists at IdentityRegistry.
5. status works with the configured DCW wallet.
6. first register returns status=registered and a real tx_hash.
7. ArcScan tx target is the configured IdentityRegistry.
8. tx method is register(string).
9. tx emits ERC-721 Transfer mint to the DCW wallet in that same tx hash.
10. SQLite contains exactly one identity row for the wallet.
11. second register returns already_registered or already_registered_onchain.
12. second register does not submit a new Circle transaction.
13. If Circle/API times out, inspect /data/circle_executions before retrying.
```

## Commands

```bash
erc8004-deepagent config
erc8004-deepagent doctor
erc8004-deepagent status
erc8004-deepagent register
erc8004-deepagent clear-expired-locks
erc8004-deepagent agent-register
```

## Environment notes

`ERC8004_FROM_BLOCK` defaults to `41752050` to avoid expensive scans from block zero on Arc Testnet. Override it if you deploy another registry or need older history.

`CIRCLE_EXECUTION_STATE_DIR=/data/circle_executions` stores non-secret Circle execution metadata: transaction id, txHash if available, and state. This helps recover from ambiguous API timeout without immediately submitting a duplicate registration.

## x402 Payment Tools

When `X402_ENABLED=true`, the Deep Agent gets three x402 payment tools:

```bash
# Buyer: pay for an x402-protected resource
x402_pay(url, wallet_id, max_amount_usdc="0.000001")

# Seller: verify + settle an incoming x402 payment
x402_sell_settle(payment_signature, pay_to, amount_atomic="1")

# Balance: check Gateway USDC balance
x402_balance(wallet_address)
```

The buyer tool handles the full 402 challenge-response flow:
1. Hits the endpoint (no payment)
2. Decodes the 402 `PAYMENT-REQUIRED` challenge
3. Signs via Circle DCW `signTypedData` (no raw private keys)
4. Retries with the `payment-signature` header

Default max payment: **$0.000001 USDC** (smallest economic unit on Arc).

### x402 Environment Variables

```bash
X402_ENABLED=true                              # Enable x402 tools
X402_DEFAULT_BUYER_WALLET_ID=<dcw-wallet-id>   # Circle DCW wallet ID for buyer
X402_DEFAULT_SELLER_WALLET_ADDRESS=0x...        # EVM address for seller
X402_DEFAULT_MAX_AMOUNT_USDC=0.000001           # Max per-request payment
X402_GATEWAY_API_URL=https://gateway-api-testnet.circle.com
```

### Customizing for Your Use Case

This SDK is designed for developers to customize. Examples:

```python
# Override max amount for higher-value endpoints
result = x402_pay.invoke({
    "url": "https://api.example.com/premium",
    "wallet_id": "your-dcw-wallet-id",
    "max_amount_usdc": "0.01",  # $0.01 max
})

# Check if wallet has enough Gateway balance before paying
balance = x402_balance.invoke({"wallet_address": "0x..."})

# Seller: verify a payment you received
result = x402_sell_settle.invoke({
    "payment_signature": "<base64 from PAYMENT-SIGNATURE header>",
    "pay_to": "0xYourSellerAddress",
    "amount_atomic": "1",  # $0.000001
})
```

## Disabled future plugins

ERC-8183 exists only as a placeholder:

```txt
plugins/erc8183
```
