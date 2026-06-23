# Production audit notes

This live-only package removes all fake execution paths. It is designed for Circle DCW + Arc Testnet live verification only.

## Hardened items

1. No offline executor path.
2. No fake tx hash path.
3. No raw wallet, raw calldata, transfer, approve, or generic contract execution tool is exposed to the Deep Agent.
4. Only `register_identity_once` is write-capable by default.
5. Reputation and validation writes are gated and not exposed to the Deep Agent unless explicitly enabled by two env flags.
6. `doctor` validates live env, RPC chain id, and IdentityRegistry bytecode without sending a transaction.
7. `register_identity_once` checks local SQLite, on-chain prior mint events, and a local lock before sending a transaction.
8. The SDK parses the ERC-721 mint event from the exact Circle-returned tx hash.
9. If Circle/API execution becomes ambiguous, the local lock is intentionally kept until TTL and non-secret execution state is written under `/data/circle_executions`.
10. If more than one on-chain identity is detected for the configured wallet, the SDK returns `blocked_duplicate_onchain_identities` and does not submit a transaction.

## Remaining limits

1. This SDK cannot prevent direct contract calls made outside this SDK.
2. SQLite locking protects only processes sharing the same `/data` volume. Multi-host production should replace it with Postgres or Redis advisory locks.
3. ERC-8004 is still a Draft EIP; registry ABI/address changes require explicit update.
4. Live production confidence requires successful Docker build, Circle DCW execution, and ArcScan receipt verification in the target environment.
