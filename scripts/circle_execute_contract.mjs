import fs from "node:fs";
import path from "node:path";
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";

const TX_HASH_RE = /^0x[a-fA-F0-9]{64}$/;
const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;
const ALLOWED_FEE_LEVELS = new Set(["LOW", "MEDIUM", "HIGH"]);
const TERMINAL_FAILURES = new Set(["FAILED", "CANCELLED", "DENIED"]);

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => { data += chunk; });
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

function requiredString(input, key) {
  if (typeof input[key] !== "string" || input[key].trim() === "") {
    throw new Error(`Missing required string input: ${key}`);
  }
  return input[key].trim();
}

function writeState(stateFile, payload) {
  if (!stateFile) return;
  const safePayload = {
    updatedAt: new Date().toISOString(),
    ...payload,
  };
  fs.mkdirSync(path.dirname(stateFile), { recursive: true });
  fs.writeFileSync(stateFile, JSON.stringify(safePayload, null, 2));
}

async function main() {
  const raw = await readStdin();
  const input = JSON.parse(raw || "{}");
  const stateFile = typeof input.stateFile === "string" && input.stateFile.trim() ? input.stateFile.trim() : null;

  const walletAddress = requiredString(input, "walletAddress");
  const blockchain = requiredString(input, "blockchain");
  const contractAddress = requiredString(input, "contractAddress");
  const abiFunctionSignature = requiredString(input, "abiFunctionSignature");

  if (!ADDRESS_RE.test(walletAddress)) throw new Error("walletAddress must be an EVM address");
  if (!ADDRESS_RE.test(contractAddress)) throw new Error("contractAddress must be an EVM address");
  if (!Array.isArray(input.abiParameters)) throw new Error("abiParameters must be an array");

  const feeLevel = input.feeLevel || "MEDIUM";
  if (!ALLOWED_FEE_LEVELS.has(feeLevel)) throw new Error("feeLevel must be LOW, MEDIUM, or HIGH");

  const pollSeconds = Number(input.pollSeconds || 5);
  const maxPolls = Number(input.maxPolls || 180);
  if (!Number.isFinite(pollSeconds) || pollSeconds < 1 || pollSeconds > 60) throw new Error("pollSeconds out of range");
  if (!Number.isFinite(maxPolls) || maxPolls < 1 || maxPolls > 300) throw new Error("maxPolls out of range");

  if (!process.env.CIRCLE_API_KEY) throw new Error("CIRCLE_API_KEY is required");
  if (!process.env.CIRCLE_ENTITY_SECRET) throw new Error("CIRCLE_ENTITY_SECRET is required");

  writeState(stateFile, {
    phase: "init",
    walletAddress,
    blockchain,
    contractAddress,
    abiFunctionSignature,
    txId: null,
    txHash: null,
    state: null,
  });

  const circleClient = initiateDeveloperControlledWalletsClient({
    apiKey: process.env.CIRCLE_API_KEY,
    entitySecret: process.env.CIRCLE_ENTITY_SECRET,
  });

  const createResult = await circleClient.createContractExecutionTransaction({
    walletAddress,
    blockchain,
    contractAddress,
    abiFunctionSignature,
    abiParameters: input.abiParameters,
    fee: { type: "level", config: { feeLevel } },
  });

  const txId = createResult?.data?.id || createResult?.data?.transaction?.id;
  if (!txId) {
    writeState(stateFile, { phase: "create_failed_no_tx_id", walletAddress, blockchain, contractAddress, abiFunctionSignature });
    throw new Error("Circle did not return a transaction id");
  }

  writeState(stateFile, {
    phase: "created",
    walletAddress,
    blockchain,
    contractAddress,
    abiFunctionSignature,
    txId,
    txHash: null,
    state: "CREATED",
  });

  for (let i = 0; i < maxPolls; i++) {
    await new Promise(resolve => setTimeout(resolve, pollSeconds * 1000));
    const { data } = await circleClient.getTransaction({ id: txId });
    const tx = data?.transaction || data;
    const state = tx?.state;
    const txHash = tx?.txHash || null;

    writeState(stateFile, {
      phase: "polling",
      walletAddress,
      blockchain,
      contractAddress,
      abiFunctionSignature,
      txId,
      txHash,
      state,
      poll: i + 1,
      maxPolls,
    });

    if (state === "COMPLETE") {
      if (!TX_HASH_RE.test(txHash || "")) throw new Error("Circle transaction COMPLETE but txHash is missing or invalid");
      const output = { transactionId: txId, state, txHash };
      writeState(stateFile, { phase: "complete", walletAddress, blockchain, contractAddress, abiFunctionSignature, txId, txHash, state });
      process.stdout.write(JSON.stringify(output));
      return;
    }

    if (TERMINAL_FAILURES.has(state)) {
      writeState(stateFile, { phase: "terminal_failure", walletAddress, blockchain, contractAddress, abiFunctionSignature, txId, txHash, state });
      throw new Error(`Circle transaction terminal failure: ${txId} ${state}`);
    }
  }

  writeState(stateFile, { phase: "timeout", walletAddress, blockchain, contractAddress, abiFunctionSignature, txId, txHash: null, state: "TIMEOUT" });
  throw new Error(`Circle transaction timed out: ${txId}`);
}

main().catch(err => {
  process.stderr.write(safeError(err));
  process.exit(1);
});
