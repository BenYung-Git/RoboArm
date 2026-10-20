/**
 * Offline preflight acceptance dump (original tolerances).
 * Usage: node scripts/test_carry_acceptance.mjs
 */
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const demo = JSON.parse(
  readFileSync(join(root, "data/virtual_demo/carry_demo_1.json"), "utf8")
);
const model = JSON.parse(
  readFileSync(join(root, "data/virtual_demo/models/rokae_cr7.json"), "utf8")
);
const kinUrl =
  "file:///" + join(root, "app/static/js/arm_kinematics.js").replace(/\\/g, "/");
const { buildDemoWaypoints } = await import(kinUrl);
const plan = buildDemoWaypoints(demo, model);
const outDir = join(root, "delivery/carry_demo_1");
mkdirSync(outDir, { recursive: true });
const out = {
  ok: plan.ok,
  reason: plan.reason || null,
  phase: plan.phase || null,
  target: plan.target || null,
  detail: plan.detail
    ? {
        posErr: plan.detail.posErr,
        approachErrDeg: plan.detail.approachErrDeg,
        closingErrDeg: plan.detail.closingErrDeg,
      }
    : null,
  motion: demo.motion,
  metrics: plan.metrics || null,
  geometry: plan.geometry || null,
  phases: plan.ok ? plan.planned.map((p) => p.name + ":" + p.type) : [],
};
const path = join(outDir, "preflight_acceptance.json");
writeFileSync(path, JSON.stringify(out, null, 2), "utf8");
console.log(JSON.stringify(out, null, 2));
if (!plan.ok) process.exit(1);
