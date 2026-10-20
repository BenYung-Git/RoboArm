/**
 * Node preflight for carry demo (FK/IK path plan, no browser).
 */
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const demo = JSON.parse(
  readFileSync(join(root, "data/virtual_demo/carry_demo_1.json"), "utf8")
);
const model = JSON.parse(
  readFileSync(join(root, "data/virtual_demo/models/rokae_cr7.json"), "utf8")
);

const kinUrl = "file:///" + join(root, "app/static/js/arm_kinematics.js").replace(/\\/g, "/");
const { buildDemoWaypoints, computeTcpPose, gapContactForObject, fingerCenterX } =
  await import(kinUrl);

const plan = buildDemoWaypoints(demo, model);
const summary = {
  ok: plan.ok,
  reason: plan.reason || null,
  phase: plan.phase || null,
  metrics: plan.metrics || null,
  geometry: plan.geometry || null,
  phases: plan.ok ? plan.planned.map((p) => p.name + ":" + p.type) : [],
  gap_contact: gapContactForObject(demo),
  finger_center_at_open: fingerCenterX(demo, demo.gripper.gap_fully_open_m),
  finger_center_at_contact: fingerCenterX(demo, gapContactForObject(demo)),
  derived_areas: {
    table_top_area_m2: demo.derived.table_top_area_m2,
    table_usable_area_m2: demo.derived.table_usable_area_m2,
    object_base_area_m2: demo.derived.object_base_area_m2,
    top_z_m: demo.table.top_z_m,
  },
};

if (plan.ok) {
  const graspStep = plan.planned.find((p) => p.name === "Descend");
  const last = graspStep.jointsSeq[graspStep.jointsSeq.length - 1];
  const tcp = computeTcpPose(model.segments, last, demo.gripper);
  summary.grasp_tcp = {
    position: tcp.position,
    approach: tcp.approach,
    closing: tcp.closing,
  };
}

console.log(JSON.stringify(summary, null, 2));
if (!plan.ok) {
  process.exit(1);
}
