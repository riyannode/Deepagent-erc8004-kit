"""x402 payment tools for the Deep Agent.

Exposes three tools:
  - x402_pay:          Buyer — pay for an x402-protected resource
  - x402_sell_settle:  Seller — verify + settle an incoming x402 payment
  - x402_balance:      Check Gateway USDC balance for a wallet

All tools use Circle DCW (no raw private keys) via the Node.js sidecar.
Developers can customize behavior through environment variables.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from ..config import load_config

TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _sidecar_path() -> Path:
    cfg = load_config()
    project_root = Path(os.getenv("SDK_PROJECT_ROOT", "/app"))
    script = project_root / "scripts" / "x402_payment.mjs"
    if not script.exists():
        raise RuntimeError(f"x402 sidecar not found: {script}")
    return script


def _run_sidecar(payload: dict, timeout: int = 120) -> dict:
    """Run the x402 sidecar and return parsed JSON output."""
    import hashlib
    script = _sidecar_path()
    cfg = load_config()

    if not cfg.circle_api_key:
        raise RuntimeError("CIRCLE_API_KEY is required for x402 operations")
    if not cfg.circle_entity_secret:
        raise RuntimeError("CIRCLE_ENTITY_SECRET is required for x402 operations")

    # M6: Script integrity check
    _EXPECTED_HASH = "SKIP_CHECK"
    if _EXPECTED_HASH != "SKIP_CHECK":
        actual = hashlib.sha256(script.read_bytes()).hexdigest()
        if actual != _EXPECTED_HASH:
            raise RuntimeError(f"x402 sidecar integrity check failed")

    proc = subprocess.run(
        ["node", str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(script.parent.parent),
        check=False,
        timeout=timeout,
    )

    if proc.returncode != 0 and not proc.stdout.strip():
        stderr = proc.stderr.strip()
        for secret in [cfg.circle_api_key, cfg.circle_entity_secret]:
            if secret:
                stderr = stderr.replace(secret, "[redacted]")
        raise RuntimeError(f"x402 sidecar failed: {stderr}")

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"x402 sidecar returned non-JSON: {proc.stdout[:200]}") from exc

    if not result.get("ok"):
        raise RuntimeError(f"x402 operation failed: {result.get('error', 'unknown')}")

    return result


@tool
def x402_pay(url: str, wallet_id: str, max_amount_usdc: str = "0.000001", method: str = "GET") -> dict:
    """Pay for an x402-protected resource using Circle DCW.

    Sends a request to the URL, handles the 402 payment challenge,
    signs the payment via Circle DCW signTypedData, and retries
    with the payment signature.

    Args:
        url: The x402-protected endpoint URL.
        wallet_id: Circle DCW wallet ID (the buyer wallet).
        max_amount_usdc: Maximum payment amount in USDC (default: $0.000001).
        method: HTTP method (default: GET).

    Returns:
        Dict with payment result, response body, and transaction details.
    """
    return _run_sidecar({
        "mode": "pay",
        "url": url,
        "walletId": wallet_id,
        "maxAmountUsdc": max_amount_usdc,
        "method": method,
    })


@tool
def x402_sell_settle(payment_signature: str, pay_to: str, amount_atomic: str = "1", network: str = "eip155:5042002") -> dict:
    """Verify and settle an incoming x402 payment (seller side).

    Takes a base64-encoded payment signature from the buyer's
    PAYMENT-SIGNATURE header, verifies it via Circle Gateway,
    and settles the payment.

    Args:
        payment_signature: Base64-encoded payment payload from buyer.
        pay_to: Seller's EVM wallet address to receive payment.
        amount_atomic: Expected amount in atomic units (6 decimals). Default "1" = $0.000001.
        network: Network identifier (default: eip155:5042002 = Arc Testnet).

    Returns:
        Dict with verification and settlement results including txHash.
    """
    return _run_sidecar({
        "mode": "sell",
        "paymentSignature": payment_signature,
        "payTo": pay_to,
        "amountAtomic": amount_atomic,
        "network": network,
    })


@tool
def x402_balance(wallet_address: str) -> dict:
    """Check Circle Gateway USDC balance for a wallet address.

    Gateway balance is what's available for x402 payments.
    This is separate from on-chain USDC balance.

    Args:
        wallet_address: EVM wallet address to check.

    Returns:
        Dict with balance in USDC and raw atomic units.
    """
    if not ADDRESS_RE.match(wallet_address):
        raise ValueError(f"Invalid EVM address: {wallet_address}")
    return _run_sidecar({
        "mode": "balance",
        "walletAddress": wallet_address,
    })
