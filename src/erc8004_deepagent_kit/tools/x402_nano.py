"""x402 Nanopayment Standalone tools — 1 request = 1 payment authorization.

Simpler than batching. Designed for single paid API calls, demos, lightweight endpoints.
Same security policy: host allowlist, budget limits, env-only wallet.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from langchain_core.tools import tool

from ..config import load_config
from ..x402.ledger import X402Ledger
from ..x402.policy import assert_amount_allowed, assert_challenge_valid, assert_url_allowed

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

# Seller input validation limits
_MAX_PAYMENT_SIGNATURE_BYTES = 8192
_MAX_REQUEST_ID_LEN = 128
_MAX_RESOURCE_LEN = 2048
_MAX_JSON_BODY_BYTES = 64 * 1024  # 64KB
_SEND_BODY_METHODS = {"POST", "PUT", "PATCH"}


def _canonical_json(obj: object) -> str:
    """Canonical JSON: sorted keys, compact, no whitespace. Matches JS canonicalize()."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _body_hash(json_body: dict | None) -> str:
    """SHA-256 hash (16 hex chars) of canonical JSON body. Empty string if no body."""
    if json_body is None:
        return ""
    return hashlib.sha256(_canonical_json(json_body).encode()).hexdigest()[:16]


def _validate_json_body(json_body: dict | None, method: str) -> dict | None:
    """Validate json_body for buyer tools. Returns cleaned body or None."""
    if json_body is None:
        return None
    if not isinstance(json_body, dict):
        raise ValueError("json_body must be a dict")
    if method.upper() not in _SEND_BODY_METHODS:
        return None  # ignore body for GET/HEAD
    try:
        serialized = _canonical_json(json_body)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"json_body is not JSON serializable: {exc}") from exc
    if len(serialized.encode()) > _MAX_JSON_BODY_BYTES:
        raise ValueError(f"json_body exceeds {_MAX_JSON_BODY_BYTES} bytes when serialized")
    return json_body


def _validate_seller_inputs(payment_signature: str, resource: str, request_id: str) -> None:
    """Validate seller tool inputs before passing to sidecar."""
    if not payment_signature or not isinstance(payment_signature, str):
        raise ValueError("payment_signature must be a non-empty string")
    if len(payment_signature) > _MAX_PAYMENT_SIGNATURE_BYTES:
        raise ValueError(f"payment_signature too large ({len(payment_signature)} > {_MAX_PAYMENT_SIGNATURE_BYTES})")
    import base64
    try:
        base64.b64decode(payment_signature, validate=True)
    except Exception:
        raise ValueError("payment_signature must be valid base64")

    if not resource or not isinstance(resource, str):
        raise ValueError("resource must be a non-empty string")
    if len(resource) > _MAX_RESOURCE_LEN:
        raise ValueError(f"resource too large ({len(resource)} > {_MAX_RESOURCE_LEN})")
    if not resource.startswith(("http://", "https://")):
        raise ValueError("resource must be a valid URL")

    if not request_id or not isinstance(request_id, str):
        raise ValueError("request_id must be a non-empty string")
    if len(request_id) > _MAX_REQUEST_ID_LEN:
        raise ValueError(f"request_id too large ({len(request_id)} > {_MAX_REQUEST_ID_LEN})")


def _extract_amount_from_payment_payload(payment_signature: str) -> str | None:
    """Extract amount from base64-encoded x402 payment payload."""
    import base64
    try:
        decoded = base64.b64decode(payment_signature)
        payload = json.loads(decoded)
        value = (payload.get("payload") or {}).get("authorization", {}).get("value")
        if value is not None:
            return str(value)
        accepted = payload.get("accepted") or payload.get("payload", {}).get("accepted")
        if accepted and "amount" in accepted:
            return str(accepted["amount"])
    except Exception:
        pass
    return None


def _redact(text: str) -> str:
    """Strip known secrets from error messages."""
    cfg = load_config()
    s = text
    for secret in [cfg.circle_api_key, cfg.circle_entity_secret]:
        if secret:
            s = s.replace(secret, "[redacted]")
    return s


def _sidecar() -> Path:
    p = Path(os.getenv("SDK_PROJECT_ROOT", "/app")) / "scripts" / "x402_nano.mjs"
    if not p.exists():
        raise RuntimeError(f"x402 nano sidecar not found: {p}")
    return p


def _run(payload: dict, timeout: int = 120) -> dict:
    script = _sidecar()
    cfg = load_config()
    if not cfg.circle_api_key or not cfg.circle_entity_secret:
        raise RuntimeError("CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET required")

    try:
        proc = subprocess.run(
            ["node", str(script)],
            input=json.dumps(payload), text=True, capture_output=True,
            cwd=str(script.parent.parent), check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"x402 nano sidecar timed out after {timeout}s")
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"x402 nano sidecar failed: {_redact(proc.stderr[:500])}")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"x402 nano sidecar returned non-JSON: {proc.stdout[:200]}") from e
    if not result.get("ok"):
        raise RuntimeError(f"x402 nano failed: {result.get('error', 'unknown')}")
    return result


@tool
def x402_nano_pay(url: str, method: str = "GET", json_body: dict | None = None) -> dict:
    """Buyer: one HTTP request, one payment authorization.

    Uses configured buyer wallet only. Enforces same budget policy.

    Args:
        url: The endpoint URL to pay for.
        method: HTTP method (GET, POST, PUT, PATCH, HEAD). Default GET.
        json_body: Optional JSON body for POST/PUT/PATCH requests.
                   Must be JSON serializable. Max 64KB serialized.
                   Ignored for GET/HEAD.
    """
    cfg = load_config()
    assert_url_allowed(url)

    # Validate json_body
    validated_body = _validate_json_body(json_body, method)

    buyer_wallet_id = cfg.x402_default_buyer_wallet_id
    if not buyer_wallet_id:
        raise RuntimeError("X402_DEFAULT_BUYER_WALLET_ID not configured")

    ledger = X402Ledger()
    agent_key = cfg.agent_key

    # Compute body hash for request_id
    body_hash = _body_hash(json_body)

    host = urlparse(url).hostname or ""
    request_id = hashlib.sha256(f"nano:{url}:{method}:{body_hash}:{agent_key}".encode()).hexdigest()[:16]

    # Phase 1: prefetch the 402 challenge (no signing yet)
    prefetch_payload = {"mode": "prefetch", "url": url, "method": method}
    if validated_body is not None:
        prefetch_payload["jsonBody"] = validated_body
    prefetch_result = _run(prefetch_payload)

    if not prefetch_result.get("paymentRequired"):
        return prefetch_result

    challenge = prefetch_result.get("challenge")
    if not challenge:
        raise RuntimeError("x402: prefetch returned no challenge")

    # Phase 2: validate challenge in Python BEFORE any signing
    accept = assert_challenge_valid(challenge, url)

    # F9: Reject challenge if amount is missing (don't default to max)
    amount_atomic = accept.get("amount")
    if not amount_atomic:
        raise PermissionError("x402: challenge missing amount field — refusing to default to max")
    assert_amount_allowed(str(amount_atomic))

    # F4: Atomic check+insert to prevent race condition
    ledger = X402Ledger()
    row_id = ledger.check_limits_and_insert_pending(
        mode="nano", agent_key=agent_key, wallet_id=buyer_wallet_id,
        host=host, resource=url, request_id=request_id,
        amount_atomic=str(amount_atomic),
    )

    try:
        # Phase 3: sign and retry with pre-validated challenge
        pay_payload = {
            "mode": "pay", "url": url, "walletId": buyer_wallet_id,
            "maxAmountUsdc": cfg.x402_max_per_request_usdc, "method": method,
            "challenge": challenge,
        }
        if validated_body is not None:
            pay_payload["jsonBody"] = validated_body
        result = _run(pay_payload)
        ledger.update_status(row_id, "success")
        result["ledger_row_id"] = row_id
        result["request_id"] = request_id
        return result
    except Exception:
        ledger.update_status(row_id, "failed")
        raise


@tool
def x402_nano_sell_settle(payment_signature: str, resource: str, request_id: str) -> dict:
    """Seller: verify/settle one standalone nanopayment. Idempotent."""
    cfg = load_config()
    pay_to = cfg.x402_default_seller_wallet_address
    if not pay_to:
        raise RuntimeError("X402_DEFAULT_SELLER_WALLET_ADDRESS not configured")
    # F13: Validate seller wallet is a proper EVM address
    if not ADDRESS_RE.match(pay_to):
        raise ValueError(f"X402_DEFAULT_SELLER_WALLET_ADDRESS is not a valid EVM address: {pay_to!r}")

    # Validate inputs before passing to sidecar
    _validate_seller_inputs(payment_signature, resource, request_id)

    # Extract actual amount from payment payload — fail closed if missing
    extracted_amount = _extract_amount_from_payment_payload(payment_signature)
    if not extracted_amount:
        raise ValueError("payment_signature missing authorization value/accepted amount — cannot determine payment amount")
    if not extracted_amount.isdigit() or int(extracted_amount) <= 0:
        raise ValueError(f"invalid amount_atomic in payment payload: {extracted_amount!r}")
    amount_atomic = extracted_amount

    ledger = X402Ledger()
    # F10: Use full payment signature hash (not truncated)
    payment_hash = hashlib.sha256(
            f"nano_sell:{payment_signature}:{pay_to}:{resource}:{request_id}".encode()
        ).hexdigest()
    existing = ledger.check_already_settled(payment_hash)
    if existing in ("success", "already_settled"):
        return {"ok": True, "mode": "nano_sell", "status": "already_settled", "payment_hash": payment_hash}

    row_id = ledger.insert_pending(
        mode="nano_sell", agent_key="seller", wallet_id="seller",
        host=urlparse(resource).hostname or "", resource=resource,
        request_id=request_id, amount_atomic=amount_atomic,
    )

    try:
        result = _run({
            "mode": "sell", "paymentSignature": payment_signature,
            "payTo": pay_to, "amountAtomic": amount_atomic, "resource": resource,
        })
        tx_hash = result.get("txHash")
        ledger.update_status(row_id, "success", tx_hash=tx_hash)
        result["ledger_row_id"] = row_id
        result["payment_hash"] = payment_hash
        return result
    except Exception:
        ledger.update_status(row_id, "failed")
        raise


@tool
def x402_nano_balance(wallet_address: str) -> dict:
    """Gateway balance read."""
    if not ADDRESS_RE.match(wallet_address):
        raise ValueError(f"Invalid address: {wallet_address}")
    return _run({"mode": "balance", "walletAddress": wallet_address})
