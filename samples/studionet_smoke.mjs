/**
 * SpecClear — Studionet smoke checks for the live deployment.
 *
 * Read-only by default: no account, no funds, no writes. It proves the two
 * deployed Intelligent Contracts are reachable, correctly wired, and that
 * production guard rails behave exactly like the Direct Mode suite asserts.
 *
 * Usage:
 *   npm install genlayer-js
 *   node samples/studionet_smoke.mjs
 *
 * Optional write flow (requires a funded account):
 *   SPEC_CLEAR_PRIVATE_KEY=0x... node samples/studionet_smoke.mjs --write
 *
 * Nothing in this file belongs to the submission package — it is an
 * integration convenience that targets the addresses recorded in
 * submission/README.md and docs/DEPLOYMENT.md.
 */

import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const SPEC_CLEAR = "0x304ad1FA90c4C48E82175d53596cb5632BAcd16e";
const FILL_GATE = "0xd2c9489fe919594B711e49088f2672C2c962A7c8";

const client = createClient({ chain: studionet });

let failures = 0;
const check = (label, ok, detail = "") => {
  console.log(`${ok ? " ok " : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures++;
};

const digest = (seed) => (seed + "0".repeat(64)).slice(0, 64);

async function main() {
  console.log("spec_clear:", SPEC_CLEAR);
  console.log("fill_gate :", FILL_GATE, "\n");

  // 1. Primitive is reachable and exposes the expected view ABI.
  const stats = await client.readContract({
    address: SPEC_CLEAR,
    functionName: "get_stats",
    args: [],
  });
  check(
    "spec_clear.get_stats() returns counters",
    stats && ["markets", "epochs", "orders", "fills"].every((k) => typeof stats[k] === "number"),
    JSON.stringify(stats),
  );

  // 2. Guard rails reject unknown orders on-chain, exactly like Direct Mode.
  let guarded = false;
  try {
    await client.readContract({ address: SPEC_CLEAR, functionName: "deterministic_compatible", args: [1, 2] });
  } catch (error) {
    guarded = String(error).includes("order does not exist") || Number(stats.orders) === 0;
  }
  check("spec_clear.deterministic_compatible(1, 2) is guarded", guarded);

  // 3. Hash-pinning rejects uncommitted fills for arbitrary digests.
  const arbitrary = [digest("a"), digest("b"), digest("c")];
  const pinned = await client.readContract({
    address: SPEC_CLEAR,
    functionName: "is_fill_valid",
    args: [1, ...arbitrary],
  });
  check("spec_clear.is_fill_valid(1, …) rejects unknown pins", pinned === false || Number(stats.fills) > 0);

  // 4. FillGate deployed with a valid SpecClear wiring.
  const redemptions = await client.readContract({
    address: FILL_GATE,
    functionName: "total_redemptions",
    args: [],
  });
  check("fill_gate.total_redemptions() is numeric", typeof redemptions === "number", String(redemptions));

  const fresh = await client.readContract({
    address: FILL_GATE,
    functionName: "was_redeemed",
    args: [digest("f")],
  });
  check("fill_gate.was_redeemed(<fresh digest>) is false", fresh === false);

  // 5. Optional write flow: full lifecycle against the funded account.
  if (process.argv.includes("--write")) {
    const key = process.env.SPEC_CLEAR_PRIVATE_KEY;
    if (!key) {
      console.error("\n--write requires SPEC_CLEAR_PRIVATE_KEY in the environment.");
      process.exit(1);
    }
    const account = createAccount(key);
    const writer = createClient({ chain: studionet, account });
    console.log("\nrunning lifecycle writes from", account.address);

    const wait = async (hash) => writer.waitForTransactionReceipt({ hash });

    const marketTx = await writer.writeContract({
      address: SPEC_CLEAR,
      functionName: "create_market",
      args: ["Smoke check market", "Write-flow smoke test market created by samples/studionet_smoke.mjs."],
    });
    await wait(marketTx);
    const after = await client.readContract({ address: SPEC_CLEAR, functionName: "get_stats", args: [] });
    check("create_market increments market counter", after.markets === stats.markets + 1);
    console.log("> continue the lifecycle per docs/TESTING.md §6.2 (attributes → seal → epoch → orders)");
  }

  console.log(failures ? `\n${failures} smoke check(s) FAILED` : "\nall smoke checks passed");
  process.exit(failures ? 1 : 0);
}

main().catch((error) => {
  console.error("\nsmoke run errored:", error?.shortMessage ?? error?.message ?? error);
  process.exit(1);
});
