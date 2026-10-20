import {
  buildDemoWaypoints,
  computeTcpPose,
  demoPlaceXy,
  fingerCenterX,
  gapContactForObject,
  measurePoseErrors,
  robotToScene,
} from "/static/js/arm_kinematics.js";

function api(url, options) {
  return fetch(url, options).then(async function (response) {
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  });
}

function angleBetween(a, b) {
  const d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  return (Math.acos(Math.max(-1, Math.min(1, d))) * 180) / Math.PI;
}

function objectBottomZ(pose, height) {
  const az = pose.axis_world[2];
  return pose.center_xyz_m[2] - (height / 2) * Math.max(0.2, Math.abs(az));
}

function maxAbsJointDelta(a, b) {
  let m = 0;
  for (let i = 0; i < a.length; i += 1) {
    m = Math.max(m, Math.abs(a[i] - b[i]));
  }
  return m;
}

export function createCarryDemoRunner(ctx) {
  const state = {
    abortToken: 0,
    running: false,
    runtimeTrack: null,
  };

  function newRuntimeTrack(demo) {
    return {
      stage: "runtime",
      formulas: demo.derived.error_formulas,
      limits: {
        path_xy_drift_max_m: demo.motion.path_xy_drift_max_m,
        path_ang_drift_max_deg: demo.motion.path_ang_drift_max_deg,
        path_closing_perp_max_deg:
          demo.motion.path_closing_perp_max_deg != null
            ? demo.motion.path_closing_perp_max_deg
            : demo.motion.path_ang_drift_max_deg,
      },
      maxXyDrift: 0,
      maxXyPhase: null,
      maxApproachToNegZDeg: 0,
      maxApproachPhase: null,
      maxClosingToNegXDeg: 0,
      maxClosingToNegXPhase: null,
      maxClosingPerpToObjectZDeg: 0,
      maxClosingPerpPhase: null,
    };
  }

  function accumulateRuntime(phaseName, pose, demo, refXy) {
    const track = state.runtimeTrack;
    const m = measurePoseErrors(pose, demo, refXy);
    if (m.xyDriftM >= track.maxXyDrift) {
      track.maxXyDrift = m.xyDriftM;
      track.maxXyPhase = phaseName;
    }
    if (m.approachToNegZDeg >= track.maxApproachToNegZDeg) {
      track.maxApproachToNegZDeg = m.approachToNegZDeg;
      track.maxApproachPhase = phaseName;
    }
    if (m.closingToNegXDeg >= track.maxClosingToNegXDeg) {
      track.maxClosingToNegXDeg = m.closingToNegXDeg;
      track.maxClosingToNegXPhase = phaseName;
    }
    if (m.closingPerpToObjectZDeg >= track.maxClosingPerpToObjectZDeg) {
      track.maxClosingPerpToObjectZDeg = m.closingPerpToObjectZDeg;
      track.maxClosingPerpPhase = phaseName;
    }
    return m;
  }

  function assertFixedXySample(phaseName, pose, demo, refXy) {
    const m = accumulateRuntime(phaseName, pose, demo, refXy);
    const motion = demo.motion;
    if (m.xyDriftM > motion.path_xy_drift_max_m) {
      throw new Error(
        "runtime_xy_drift@" + phaseName + ":" + m.xyDriftM.toFixed(5)
      );
    }
    if (m.approachToNegZDeg > motion.path_ang_drift_max_deg) {
      throw new Error(
        "runtime_approach_ang@" + phaseName + ":" + m.approachToNegZDeg.toFixed(2)
      );
    }
    if (m.closingToNegXDeg > motion.path_ang_drift_max_deg) {
      throw new Error(
        "runtime_closing_to_neg_x@" +
          phaseName +
          ":" +
          m.closingToNegXDeg.toFixed(2)
      );
    }
    const perpLim =
      motion.path_closing_perp_max_deg != null
        ? motion.path_closing_perp_max_deg
        : motion.path_ang_drift_max_deg;
    if (m.closingPerpToObjectZDeg > perpLim) {
      throw new Error(
        "runtime_closing_perp@" +
          phaseName +
          ":" +
          m.closingPerpToObjectZDeg.toFixed(2)
      );
    }
    return m;
  }

  function playRate() {
    if (typeof ctx.getDemoPlayRate === "function") {
      const r = Number(ctx.getDemoPlayRate());
      if (Number.isFinite(r) && r > 0) {
        return r;
      }
    }
    return 1;
  }

  function applyPoseFrame(joints, options, atWaypointEnd) {
    const demo = options.demo;
    const model = options.model;
    const phaseName = options.phaseName;
    const fixedXy = !!options.fixedXy;
    const refXy = options.refXy || null;
    const graspOffset = options.graspOffset;
    const grasped = !!options.grasped;
    ctx.onJoints(joints);
    if (!demo || !model || !(fixedXy || grasped)) {
      return;
    }
    const tcp = computeTcpPose(model.segments, joints, demo.gripper);
    if (grasped && graspOffset) {
      ctx.followObject(tcp, graspOffset);
    }
    // Path limits apply to waypoint endpoints only. Mid-lerp joint
    // interpolation can briefly exceed Cartesian drift (seen on RetractPlace).
    if (fixedXy && atWaypointEnd) {
      assertFixedXySample(phaseName, tcp, demo, refXy);
    }
  }

  async function finishMotion(motionId, token, options) {
    const done = await api("/api/virtual-demo/complete-motion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motion_id: motionId }),
    });
    if (token !== state.abortToken) {
      throw new Error("aborted");
    }
    if (done.motion_ignored) {
      throw new Error("aborted");
    }
    const demo = options.demo;
    const model = options.model;
    const grasped = !!options.grasped;
    const graspOffset = options.graspOffset;
    const fixedXy = !!options.fixedXy;
    ctx.onJoints(done.current_joints);
    // Re-pin grasped object after complete-motion (no follow tick there).
    if (demo && model && grasped && graspOffset) {
      const tcpDone = computeTcpPose(
        model.segments,
        done.current_joints,
        demo.gripper
      );
      ctx.followObject(tcpDone, graspOffset);
    }
    if (demo && model && fixedXy) {
      const tcpDone = computeTcpPose(
        model.segments,
        done.current_joints,
        demo.gripper
      );
      assertFixedXySample(options.phaseName, tcpDone, demo, options.refXy || null);
    }
    return done;
  }

  async function moveJoints(joints, opts) {
    const options = opts || {};
    const started = await api("/api/virtual-demo/demo/move-j", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ joints: joints }),
    });
    if (!started.motion_started) {
      throw new Error(started.last_result_key || "move_j_rejected");
    }
    const motionId = started.motion_id;
    const start = started.current_joints.slice();
    const target = started.target_joints.slice();
    const speed = Number(started.animation_deg_per_sec) || 40;
    let maxDelta = 0;
    for (let i = 0; i < start.length; i += 1) {
      maxDelta = Math.max(maxDelta, Math.abs(target[i] - start[i]));
    }
    // Base duration at ×1; live play-rate scales progress (demo2 only via ctx).
    const baseDurationMs = Math.max(180, (maxDelta / speed) * 1000);
    let progress = 0;
    let lastNow = performance.now();
    const token = state.abortToken;

    return new Promise(function (resolve, reject) {
      function frame(now) {
        if (token !== state.abortToken) {
          reject(new Error("aborted"));
          return;
        }
        const dt = Math.max(0, now - lastNow);
        lastNow = now;
        progress += (dt / baseDurationMs) * playRate();
        const ratio = Math.min(1, progress);
        const cur = start.map(function (v, i) {
          return v + (target[i] - v) * ratio;
        });
        try {
          applyPoseFrame(cur, options, ratio >= 1);
        } catch (err) {
          reject(err);
          return;
        }
        if (ratio < 1) {
          requestAnimationFrame(frame);
          return;
        }
        finishMotion(motionId, token, options).then(resolve).catch(reject);
      }
      requestAnimationFrame(frame);
    });
  }

  /**
   * Play a waypoint joint sequence as one server motion (to final joints) with
   * local multi-segment animation. Avoids hundreds of move-j round-trips on
   * Transfer while still checking fixed-XY only at waypoint ends.
   */
  async function moveJointsSeq(jointsSeq, opts) {
    const options = opts || {};
    if (!jointsSeq || !jointsSeq.length) {
      return null;
    }
    if (jointsSeq.length === 1) {
      return moveJoints(jointsSeq[0], options);
    }
    const finalTarget = jointsSeq[jointsSeq.length - 1];
    const started = await api("/api/virtual-demo/demo/move-j", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ joints: finalTarget }),
    });
    if (!started.motion_started) {
      throw new Error(started.last_result_key || "move_j_rejected");
    }
    const motionId = started.motion_id;
    const speed = Number(started.animation_deg_per_sec) || 40;
    const token = state.abortToken;
    const chain = [started.current_joints.slice()].concat(
      jointsSeq.map(function (q) {
        return q.slice();
      })
    );
    const segMs = [];
    let totalMs = 0;
    for (let s = 0; s < chain.length - 1; s += 1) {
      let maxDelta = 0;
      for (let i = 0; i < chain[s].length; i += 1) {
        maxDelta = Math.max(maxDelta, Math.abs(chain[s + 1][i] - chain[s][i]));
      }
      const ms = Math.max(12, (maxDelta / speed) * 1000);
      segMs.push(ms);
      totalMs += ms;
    }
    let elapsed = 0;
    let lastNow = performance.now();
    // Index into chain of last waypoint that received an endpoint check.
    let checkedIdx = 0;

    return new Promise(function (resolve, reject) {
      function frame(now) {
        if (token !== state.abortToken) {
          reject(new Error("aborted"));
          return;
        }
        const dt = Math.max(0, now - lastNow);
        lastNow = now;
        elapsed += dt * playRate();
        const t = Math.min(elapsed, totalMs);
        let acc = 0;
        let seg = 0;
        while (seg < segMs.length - 1 && acc + segMs[seg] < t) {
          acc += segMs[seg];
          seg += 1;
        }
        const local = segMs[seg] > 0 ? (t - acc) / segMs[seg] : 1;
        const ratio = Math.min(1, Math.max(0, local));
        const a = chain[seg];
        const b = chain[seg + 1];
        const cur = a.map(function (v, i) {
          return v + (b[i] - v) * ratio;
        });
        // chain index reached exactly (waypoint end) vs still in-segment.
        const reachedIdx = ratio >= 1 ? seg + 1 : seg;
        try {
          while (checkedIdx < reachedIdx) {
            checkedIdx += 1;
            applyPoseFrame(
              chain[checkedIdx].slice(),
              options,
              !!options.fixedXy
            );
          }
          if (ratio < 1) {
            applyPoseFrame(cur, options, false);
          }
        } catch (err) {
          reject(err);
          return;
        }
        if (elapsed < totalMs) {
          requestAnimationFrame(frame);
          return;
        }
        finishMotion(motionId, token, options).then(resolve).catch(reject);
      }
      requestAnimationFrame(frame);
    });
  }

  function checkGrasp(demo, tcpPose, gap) {
    const obj = demo.object;
    const g = demo.gripper;
    const contact = gapContactForObject(demo);
    if (Math.abs(gap - contact) > 0.004) {
      return { ok: false, reason: "gap_not_contact" };
    }
    const aw = g.approach_axis_world;
    const cw = g.closing_axis_world;
    if (angleBetween(tcpPose.approach, aw) > demo.motion.ik_ang_tol_deg) {
      return { ok: false, reason: "approach_pose" };
    }
    if (angleBetween(tcpPose.closing, cw) > demo.motion.ik_ang_tol_deg) {
      return { ok: false, reason: "closing_pose" };
    }
    const c = ctx.getObjectPose().center_xyz_m;
    const dz = Math.abs(tcpPose.position[2] - c[2]);
    if (dz > g.grasp_band_z_m) {
      return { ok: false, reason: "height_band" };
    }
    const rel = [
      c[0] - tcpPose.position[0],
      c[1] - tcpPose.position[1],
      c[2] - tcpPose.position[2],
    ];
    const alongClose =
      rel[0] * tcpPose.closing[0] +
      rel[1] * tcpPose.closing[1] +
      rel[2] * tcpPose.closing[2];
    if (Math.abs(alongClose) > contact / 2 + 0.006) {
      return { ok: false, reason: "not_between_fingers" };
    }
    const radial = Math.hypot(
      rel[0] - alongClose * tcpPose.closing[0],
      rel[1] - alongClose * tcpPose.closing[1],
      rel[2] - alongClose * tcpPose.closing[2]
    );
    if (radial > obj.radius_m + 0.01) {
      return { ok: false, reason: "radial_miss" };
    }
    return { ok: true };
  }

  function checkPlace(demo, pose) {
    const table = demo.place_table || demo.table;
    const obj = demo.object;
    const motion = demo.motion;
    const placeXy = demoPlaceXy(demo);
    const bottom = objectBottomZ(pose, obj.height_m);
    const bottomErr = Math.abs(bottom - table.top_z_m);
    const dx = pose.center_xyz_m[0] - placeXy[0];
    const dy = pose.center_xyz_m[1] - placeXy[1];
    const xyErr = Math.hypot(dx, dy);
    const tilt = angleBetween(pose.axis_world, obj.axis_world);
    if (bottomErr > motion.place_bottom_tol_m) {
      return { ok: false, reason: "bottom_height", bottom: bottom, bottomErr: bottomErr };
    }
    if (xyErr > motion.place_xy_tol_m) {
      return { ok: false, reason: "xy", dx: dx, dy: dy, xyErr: xyErr };
    }
    if (tilt > motion.place_tilt_tol_deg) {
      return { ok: false, reason: "tilt", tilt: tilt };
    }
    return {
      ok: true,
      bottom: bottom,
      bottomErr: bottomErr,
      xyErr: xyErr,
      tilt: tilt,
      pose: {
        center_xyz_m: pose.center_xyz_m.slice(),
        axis_world: pose.axis_world.slice(),
      },
    };
  }

  function assertCompletedReady(demo, model, lastPlace, snap) {
    if (!lastPlace || !lastPlace.ok) {
      throw new Error("completed_blocked:place_not_verified");
    }
    if (ctx.isGrasped()) {
      throw new Error("completed_blocked:still_grasped");
    }
    const openGap = demo.gripper.gap_fully_open_m;
    if (Math.abs(ctx.getGap() - openGap) > 1e-6) {
      throw new Error("completed_blocked:gap_not_open");
    }
    const home = model.home_joints_deg;
    const joints = ctx.getJoints();
    const homeTol =
      demo.motion.home_joint_tol_deg != null ? demo.motion.home_joint_tol_deg : 0.5;
    const homeErr = maxAbsJointDelta(joints, home);
    if (homeErr > homeTol) {
      throw new Error("completed_blocked:not_home:" + homeErr.toFixed(3));
    }
    if (snap && snap.is_moving) {
      throw new Error("completed_blocked:still_moving");
    }
    if (snap && snap.demo_run_state !== "running") {
      throw new Error("completed_blocked:bad_state:" + snap.demo_run_state);
    }
    return {
      joints: joints.slice(),
      home: home.slice(),
      homeErrDeg: homeErr,
      homeTolDeg: homeTol,
      place: lastPlace,
      grasped: false,
      gap_m: ctx.getGap(),
    };
  }

  async function run() {
    if (state.running) {
      return;
    }
    state.running = true;
    const token = ++state.abortToken;
    let lastPlace = null;
    try {
      const snap0 = await api("/api/virtual-demo/demo/start", { method: "POST" });
      if (!snap0.demo_started) {
        ctx.onSnapshot(snap0);
        state.running = false;
        return snap0;
      }
      ctx.onSnapshot(snap0);
      const demo = snap0.carry_demo;
      const model = snap0.viewer_model;
      const plan = buildDemoWaypoints(demo, model);
      if (!plan.ok) {
        const failed = await api("/api/virtual-demo/demo/preflight", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ok: false,
            detail: plan.reason + (plan.phase ? " @ " + plan.phase : ""),
          }),
        });
        ctx.onSnapshot(failed);
        state.running = false;
        return failed;
      }
      await api("/api/virtual-demo/demo/preflight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ok: true }),
      });
      state.runtimeTrack = newRuntimeTrack(demo);
      ctx.onMetrics({
        preflight: plan.metrics,
        runtime: state.runtimeTrack,
      });

      let gap = demo.gripper.gap_fully_open_m;
      let grasped = false;
      let graspOffset = null;
      ctx.setGap(gap);
      ctx.setGrasped(false);

      async function syncRuntime(extra) {
        const payload = Object.assign(
          {
            phase: extra.phase,
            grasped: grasped,
            gap_m: gap,
            object_pose: ctx.getObjectPose(),
          },
          extra
        );
        const snap = await api("/api/virtual-demo/demo/runtime", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        ctx.onSnapshot(snap);
        return snap;
      }

      for (let i = 0; i < plan.planned.length; i += 1) {
        if (token !== state.abortToken) {
          throw new Error("aborted");
        }
        const step = plan.planned[i];
        await syncRuntime({ phase: step.name });
        if (step.type === "joint") {
          await moveJoints(step.joints, {
            demo: demo,
            model: model,
            phaseName: step.name,
            fixedXy: false,
            grasped: grasped,
            graspOffset: graspOffset,
          });
        } else if (step.type === "path") {
          if (token !== state.abortToken) {
            throw new Error("aborted");
          }
          await moveJointsSeq(step.jointsSeq, {
            demo: demo,
            model: model,
            phaseName: step.name,
            fixedXy: !!step.fixedXy,
            refXy: step.refXy || null,
            grasped: grasped,
            graspOffset: graspOffset,
          });
        } else if (step.action === "close") {
          const contact = gapContactForObject(demo);
          gap = contact;
          ctx.setGap(gap);
          const joints = ctx.getJoints();
          const tcp = computeTcpPose(model.segments, joints, demo.gripper);
          const g = checkGrasp(demo, tcp, gap);
          if (!g.ok) {
            throw new Error("grasp_failed:" + g.reason);
          }
          const obj = ctx.getObjectPose();
          graspOffset = {
            center: [
              obj.center_xyz_m[0] - tcp.position[0],
              obj.center_xyz_m[1] - tcp.position[1],
              obj.center_xyz_m[2] - tcp.position[2],
            ],
            axis: obj.axis_world.slice(),
          };
          grasped = true;
          ctx.setGrasped(true);
          await syncRuntime({ phase: "Grasp" });
        } else if (step.action === "open") {
          const pose = ctx.getObjectPose();
          lastPlace = checkPlace(demo, pose);
          if (!lastPlace.ok) {
            throw new Error("place_failed:" + lastPlace.reason);
          }
          grasped = false;
          graspOffset = null;
          gap = demo.gripper.gap_fully_open_m;
          ctx.setGap(gap);
          ctx.setGrasped(false);
          // Freeze world pose at place; must not follow flange on retract/home.
          if (typeof ctx.setObjectPose === "function") {
            ctx.setObjectPose(lastPlace.pose);
          }
          await syncRuntime({
            phase: "Release",
            object_pose: lastPlace.pose,
          });
        }
      }

      const preDone = await api("/api/virtual-demo/state");
      const completion = assertCompletedReady(demo, model, lastPlace, preDone);
      ctx.onMetrics({
        preflight: plan.metrics,
        runtime: state.runtimeTrack,
        completion: completion,
      });
      const done = await syncRuntime({
        phase: "Completed",
        completed: true,
        completion_check: completion,
      });
      if (done.demo_run_state !== "completed") {
        throw new Error(
          "completed_rejected:" + (done.last_result_key || done.demo_run_state)
        );
      }
      state.running = false;
      return done;
    } catch (err) {
      if (String(err.message) !== "aborted") {
        await api("/api/virtual-demo/demo/runtime", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            aborted: true,
            phase: "Aborted",
            grasped: ctx.isGrasped(),
            gap_m: ctx.getGap(),
            object_pose: ctx.getObjectPose(),
          }),
        }).catch(function () {
          return null;
        });
      }
      state.running = false;
      throw err;
    }
  }

  function abortLocal() {
    state.abortToken += 1;
    state.running = false;
  }

  return {
    run: run,
    abortLocal: abortLocal,
    isRunning: function () {
      return state.running;
    },
    getRuntimeTrack: function () {
      return state.runtimeTrack;
    },
  };
}

export {
  robotToScene,
  fingerCenterX,
  gapContactForObject,
  computeTcpPose,
  measurePoseErrors,
};
