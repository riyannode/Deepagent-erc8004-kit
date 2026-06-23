/**
 * x402 Payment Sidecar for erc8004-deepagent-kit
 *
 * Modes:
 *   pay     — Buy: hit an x402-protected endpoint, handle 402 challenge, sign via DCW, retry
 *   sell    — Sell: verify a payment signature, settle via Gateway
 *   balance — Check Gateway USDC balance for a wallet address
 *
 * Stdin JSON shape:
 *   { mode, ...mode-specific fields }
 *
 * All secrets from env vars (CIRCLE_API_KEY, CIRCLE_ENTITY_SECRET).
 * No raw private keys — uses Circle DCW signTypedData.
 */

import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

import fs from "node:fs";
import path from "node:path";

const TX_HASH_RE = /^0x[a-fA-F0-9]{64}$/;
const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;

// ── Helpers ──────────────────────────────────────────────────────

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { data += chunk; });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function redact(value) {
  let out = String(value || "");
  for (const secret of [process.env.CIRCLE_API_KEY, process.env.CIRCLE_ENTITY_SECRET]) {
    if (secret) out = out.split(secret).join("[redacted]");
  }
  return out;
}

function safeError(err) {
  return redact(err && err.message ? err.message : String(err));
}

function fail(msg, extra = {}) {
  const output = { ok: false, error: msg, ...extra };
  process.stdout.write(JSON.stringify(output));
}

function succeed(data) {
  const output = { ok: true, ...data };
  process.stdout.write(JSON.stringify(output));
}

// ── Gateway Balance ──────────────────────────────────────────────

async function checkGatewayBalance(walletAddress) {
  const GATEWAY_API = process.env.GATEWAY_API_URL || "https://gateway-api-testnet.circle.com";
  const resp = await fetch(`${GATEWAY_API}/v1/balances`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token: "USDC",
      sources: [{ domain: 26, depositor: walletAddress.toLowerCase() }],
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Gateway balance check failed (${resp.status}): ${redact(text)}`);
  }
  const data = await resp.json();
  const raw = data.balances?.[0]?.balance;
  // Gateway returns balance in base units (6 decimals) as string
  const balanceUsdc = raw ? (Number(raw) / 1e6).toFixed(6) : "0.000000";
  const balanceRaw = raw || "0";
  return { balanceUsdc, balanceRaw, depositor: walletAddress };
}

// ── Buyer: Pay for an x402-protected resource ───────────────────

async function payForResource(input) {
  const url = input.url;
  const walletId = input.walletId;
  const maxAmountUsdc = input.maxAmountUsdc || "0.000001";

  if (!url) throw new Error("url is required");
  if (!walletId) throw new Error("walletId is required (Circle DCW wallet ID)");

  // Step 1: Initial request to get 402 challenge
  const initialResp = await fetch(url, {
    method: input.method || "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (initialResp.status !== 402) {
    // No payment required — return the free response
    const body = await initialResp.text();
    return succeed({
      mode: "pay",
      paymentRequired: false,
      httpStatus: initialResp.status,
      body: body.substring(0, 4096),
    });
  }

  // Step 2: Decode 402 challenge
  const paymentRequiredHeader = initialResp.headers.get("payment-required");
  if (!paymentRequiredHeader) {
    throw new Error("Server returned 402 but no PAYMENT-REQUIRED header");
  }

  const challenge = JSON.parse(Buffer.from(paymentRequiredHeader, "base64").toString("utf-8"));
  const accept = challenge.accepts?.[0];
  if (!accept) throw new Error("PAYMENT-REQUIRED has no accepts[] entries");

  // Check amount against max
  const amountAtomic = accept.amount || "1";
  const amountUsdc = (Number(amountAtomic) / 1e6).toFixed(6);
  const maxAtomic = String(Math.floor(Number(maxAmountUsdc) * 1e6));
  if (Number(amountAtomic) > Number(maxAtomic)) {
    throw new Error(`Seller wants ${amountUsdc} USDC but max is ${maxAmountUsdc} USDC`);
  }

  // Step 3: Build EIP-712 signing data for DCW
  const extra = accept.extra || {};
  const now = Math.floor(Date.now() / 1000);
  const validAfter = now - 60;
  const validBefore = now + (accept.maxTimeoutSeconds || 604900);
  const nonce = "0x" + Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");

  const authorization = {
    from: "", // filled after we get wallet address
    to: accept.payTo,
    value: amountAtomic,
    validAfter: String(validAfter),
    validBefore: String(validBefore),
    nonce,
  };

  // Get wallet address from DCW
  const circleClient = require("@circle-fin/developer-controlled-wallets").initiateDeveloperControlledWalletsClient({
    apiKey: process.env.CIRCLE_API_KEY,
    entitySecret: process.env.CIRCLE_ENTITY_SECRET,
  });

  const walletResp = await circleClient.getWallet({ id: walletId });
  const walletAddress = walletResp?.data?.wallet?.address;
  if (!walletAddress) throw new Error(`Could not resolve wallet address for ID: ${walletId}`);
  authorization.from = walletAddress.toLowerCase();

  // Step 4: Sign via DCW signTypedData
  const domain = {
    name: extra.name || "GatewayWalletBatched",
    version: extra.version || "1",
    chainId: 5042002,
    verifyingContract: extra.verifyingContract || "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
  };

  const types = {
    EIP712Domain: [
      { name: "name", type: "string" },
      { name: "version", type: "string" },
      { name: "chainId", type: "uint256" },
      { name: "verifyingContract", type: "address" },
    ],
    TransferWithAuthorization: [
      { name: "from", type: "address" },
      { name: "to", type: "address" },
      { name: "value", type: "uint256" },
      { name: "validAfter", type: "uint256" },
      { name: "validBefore", type: "uint256" },
      { name: "nonce", type: "bytes32" },
    ],
  };

  // DCW signTypedData expects data as JSON string
  const signResult = await circleClient.signTypedData({
    walletId,
    data: JSON.stringify({
      types,
      primaryType: "TransferWithAuthorization",
      domain,
      message: authorization,
    }, (k, v) => typeof v === "bigint" ? v.toString() : v),
  });

  const signature = signResult?.data?.signature || signResult?.data?.signatures?.[0];
  if (!signature) throw new Error("DCW signTypedData did not return a signature");

  // Step 5: Build payment payload
  const paymentPayload = {
    x402Version: challenge.x402Version || 2,
    payload: {
      authorization,
      signature,
    },
    resource: challenge.resource || url,
    accepted: accept,
  };

  // Step 6: Retry with payment signature
  const retryResp = await fetch(url, {
    method: input.method || "GET",
    headers: {
      "Content-Type": "application/json",
      "payment-signature": Buffer.from(JSON.stringify(paymentPayload)).toString("base64"),
    },
  });

  const retryBody = await retryResp.text();
  let retryData;
  try { retryData = JSON.parse(retryBody); } catch { retryData = retryBody; }

  return succeed({
    mode: "pay",
    paymentRequired: true,
    amountUsdc,
    amountAtomic,
    payTo: accept.payTo,
    network: accept.network,
    walletAddress,
    signed: true,
    httpStatus: retryResp.status,
    body: typeof retryData === "string" ? retryData.substring(0, 4096) : retryData,
  });
}

// ── Seller: Verify + settle a payment ───────────────────────────

async function settlePayment(input) {
  const paymentSignatureB64 = input.paymentSignature;
  const payTo = input.payTo;
  const amountAtomic = input.amountAtomic || "1";
  const asset = input.asset || "0x3600000000000000000000000000000000000000";
  const network = input.network || "eip155:5042002";

  if (!paymentSignatureB64) throw new Error("paymentSignature (base64) is required");
  if (!payTo || !ADDRESS_RE.test(payTo)) throw new Error("payTo must be an EVM address");

  // Dynamically import x402-batching
  let BatchFacilitatorClient;
  try {
    const mod = await import("@circle-fin/x402-batching/server");
    BatchFacilitatorClient = mod.BatchFacilitatorClient;
  } catch {
    throw new Error("@circle-fin/x402-batching not installed. Run: npm install @circle-fin/x402-batching");
  }

  const facilitator = new BatchFacilitatorClient({
    url: process.env.GATEWAY_API_URL || "https://gateway-api-testnet.circle.com",
  });

  const paymentPayload = JSON.parse(Buffer.from(paymentSignatureB64, "base64").toString("utf-8"));

  const requirements = {
    scheme: "exact",
    network,
    asset,
    amount: amountAtomic,
    payTo,
    maxTimeoutSeconds: 604900,
    extra: {
      name: "GatewayWalletBatched",
      version: "1",
      verifyingContract: "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
    },
  };

  // Verify
  const verifyResult = await facilitator.verify(paymentPayload, requirements);
  if (!verifyResult?.isValid) {
    return fail(`Payment verification failed: ${verifyResult?.invalidReason || "unknown"}`, {
      verified: false,
      invalidReason: verifyResult?.invalidReason,
    });
  }

  // Settle
  const settleResult = await facilitator.settle(paymentPayload, requirements);
  const settleData = settleResult || {};
  const rawTxHash = settleData.txHash || settleData.transaction?.txHash || null;
  const txHash = rawTxHash && TX_HASH_RE.test(rawTxHash) ? rawTxHash : null;
  const explorerUrl = txHash ? `https://testnet.arcscan.app/tx/${txHash}` : null;

  return succeed({
    mode: "sell",
    verified: true,
    settled: settleData.success !== false,
    payer: settleData.payer || verifyResult.payer || null,
    txHash,
    explorerUrl,
    amountUsdc: (Number(amountAtomic) / 1e6).toFixed(6),
    payTo,
  });
}

// ── Main ─────────────────────────────────────────────────────────

async function main() {
  const raw = await readStdin();
  const input = JSON.parse(raw || "{}");
  const mode = input.mode;

  if (!mode) throw new Error("mode is required: pay | sell | balance");

  switch (mode) {
    case "pay":
      return await payForResource(input);

    case "sell":
      return await settlePayment(input);

    case "balance": {
      const addr = input.walletAddress;
      if (!addr || !ADDRESS_RE.test(addr)) throw new Error("walletAddress must be an EVM address");
      const bal = await checkGatewayBalance(addr);
      return succeed({ mode: "balance", ...bal });
    }

    default:
      throw new Error(`Unknown mode: ${mode}. Use: pay | sell | balance`);
  }
}

main().catch((err) => {
  fail(safeError(err));
  process.exit(1);
});
