/**
 * Schematic arm FK/IK in z_up_robot frame.
 * Pivot chain order matches virtual_demo_3d.js: T(offset) * R(joint_axis, deg).
 */

function mul(a, b) {
  const o = [
    [0, 0, 0, 0],
    [0, 0, 0, 0],
    [0, 0, 0, 0],
    [0, 0, 0, 0],
  ];
  for (let i = 0; i < 4; i += 1) {
    for (let j = 0; j < 4; j += 1) {
      o[i][j] =
        a[i][0] * b[0][j] +
        a[i][1] * b[1][j] +
        a[i][2] * b[2][j] +
        a[i][3] * b[3][j];
    }
  }
  return o;
}

function ident() {
  return [
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1],
  ];
}

function trans(x, y, z) {
  const m = ident();
  m[0][3] = x;
  m[1][3] = y;
  m[2][3] = z;
  return m;
}

function rotAxis(axis, rad) {
  const n = Math.hypot(axis[0], axis[1], axis[2]) || 1;
  const ax = axis[0] / n;
  const ay = axis[1] / n;
  const az = axis[2] / n;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const C = 1 - c;
  return [
    [c + ax * ax * C, ax * ay * C - az * s, ax * az * C + ay * s, 0],
    [ay * ax * C + az * s, c + ay * ay * C, ay * az * C - ax * s, 0],
    [az * ax * C - ay * s, az * ay * C + ax * s, c + az * az * C, 0],
    [0, 0, 0, 1],
  ];
}

function transformPoint(m, p) {
  return [
    m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
    m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
    m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3],
  ];
}

function transformDir(m, d) {
  return [
    m[0][0] * d[0] + m[0][1] * d[1] + m[0][2] * d[2],
    m[1][0] * d[0] + m[1][1] * d[1] + m[1][2] * d[2],
    m[2][0] * d[0] + m[2][1] * d[1] + m[2][2] * d[2],
  ];
}

/** Robot z-up -> Three.js scene (armRoot.rotation.x = -PI/2). */
export function robotToScene(p) {
  return [p[0], p[2], -p[1]];
}

export function sceneToRobot(p) {
  return [p[0], -p[2], p[1]];
}

export function computeFlangeMatrix(segments, jointsDeg) {
  let m = ident();
  let ji = 0;
  for (let i = 0; i < segments.length; i += 1) {
    const seg = segments[i];
    const off = seg.offset || [0, 0, 0];
    m = mul(m, trans(off[0], off[1], off[2]));
    if (seg.joint_axis) {
      const rad = ((Number(jointsDeg[ji]) || 0) * Math.PI) / 180;
      m = mul(m, rotAxis(seg.joint_axis, rad));
      ji += 1;
    }
  }
  return m;
}

export function computeTcpPose(segments, jointsDeg, gripper) {
  const m = computeFlangeMatrix(segments, jointsDeg);
  const off = gripper.tcp_offset_xyz_m;
  const position = transformPoint(m, off);
  const approachTcp = gripper.approach_axis_tcp || [0, 0, 1];
  const closingTcp = gripper.closing_axis_tcp || [1, 0, 0];
  const approach = transformDir(m, approachTcp);
  const closing = transformDir(m, closingTcp);
  const n = (v) => {
    const L = Math.hypot(v[0], v[1], v[2]) || 1;
    return [v[0] / L, v[1] / L, v[2] / L];
  };
  return {
    position,
    approach: n(approach),
    closing: n(closing),
    matrix: m,
  };
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function angleBetween(a, b) {
  const d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  return (Math.acos(Math.max(-1, Math.min(1, d))) * 180) / Math.PI;
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(v) {
  const L = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / L, v[1] / L, v[2] / L];
}

/** Degrees: how far closing is from being perpendicular to object Z. */
export function closingPerpToObjectZErrDeg(closing, objectAxis) {
  const ang = angleBetween(normalize(closing), normalize(objectAxis));
  return Math.abs(90 - ang);
}

export function measurePoseErrors(pose, demo, refXy) {
  const xy = refXy || demo.object.center_xy_m;
  const aw = demo.gripper.approach_axis_world;
  const cw = demo.gripper.closing_axis_world;
  const objAxis = demo.object.axis_world;
  return {
    xyDriftM: Math.hypot(pose.position[0] - xy[0], pose.position[1] - xy[1]),
    approachToNegZDeg: angleBetween(pose.approach, aw),
    closingToNegXDeg: angleBetween(pose.closing, cw),
    closingPerpToObjectZDeg: closingPerpToObjectZErrDeg(pose.closing, objAxis),
  };
}

/** Place target XY: place_xy_m / place_table / else initial object XY (demo1 in-place). */
export function demoPlaceXy(demo) {
  if (demo.object && demo.object.place_xy_m) {
    return demo.object.place_xy_m;
  }
  if (demo.place_table && demo.place_table.center_xy_m) {
    return demo.place_table.center_xy_m;
  }
  if (demo.derived && demo.derived.object_target_xy_m) {
    return demo.derived.object_target_xy_m;
  }
  return demo.object.center_xy_m;
}

export function demoPickXy(demo) {
  if (demo.pick_table && demo.pick_table.center_xy_m) {
    return demo.pick_table.center_xy_m;
  }
  return demo.object.center_xy_m;
}

/**
 * Orientation error as angular velocity-like vector (radians) that participates
 * in the IK task (not only seed / post-check).
 * Built from approach→aw and closing→cw frame alignment.
 */
function orientationTaskError(pose, aw, cw) {
  const zc = pose.approach;
  const xc = pose.closing;
  let yc = cross(zc, xc);
  yc = normalize(yc);
  const xd = normalize(cw);
  const zd = normalize(aw);
  let yd = cross(zd, xd);
  yd = normalize(yd);
  // ω ≈ 0.5 Σ (current_axis × desired_axis)
  const w = [0, 0, 0];
  const pairs = [
    [xc, xd],
    [yc, yd],
    [zc, zd],
  ];
  for (let i = 0; i < pairs.length; i += 1) {
    const c = cross(pairs[i][0], pairs[i][1]);
    w[0] += 0.5 * c[0];
    w[1] += 0.5 * c[1];
    w[2] += 0.5 * c[2];
  }
  return w;
}

function collectOrientedSeeds(segments, limits, gripper) {
  const seeds = [];
  const aw = gripper.approach_axis_world;
  const cw = gripper.closing_axis_world;
  // Include yaw samples so −X / ±Y workspace (front–back carry) can seed IK.
  const j1Samples = [-180, -135, -90, -45, 0, 45, 90, 135, 180];
  for (let i1 = 0; i1 < j1Samples.length; i1 += 1) {
    const j1 = clamp(j1Samples[i1], limits[0][0], limits[0][1]);
    for (let j2 = -120; j2 <= 120; j2 += 20) {
      for (let j3 = -150; j3 <= 150; j3 += 20) {
        for (let j4 = -120; j4 <= 120; j4 += 40) {
          for (let j5 = -120; j5 <= 120; j5 += 20) {
            const q = [
              j1,
              clamp(j2, limits[1][0], limits[1][1]),
              clamp(j3, limits[2][0], limits[2][1]),
              clamp(j4, limits[3][0], limits[3][1]),
              clamp(j5, limits[4][0], limits[4][1]),
              0,
            ];
            const pose = computeTcpPose(segments, q, gripper);
            if (angleBetween(pose.approach, aw) > 18) {
              continue;
            }
            if (angleBetween(pose.closing, cw) > 28) {
              continue;
            }
            if (pose.position[0] < -0.55 || pose.position[0] > 0.55) {
              continue;
            }
            if (Math.abs(pose.position[1]) > 0.45) {
              continue;
            }
            if (pose.position[2] < 0.1 || pose.position[2] > 0.55) {
              continue;
            }
            seeds.push(q);
          }
        }
      }
    }
  }
  return seeds;
}

function solveLinear6(A, b) {
  const M = [];
  for (let r = 0; r < 6; r += 1) {
    M[r] = A[r].slice();
    M[r].push(b[r]);
  }
  for (let i = 0; i < 6; i += 1) {
    let piv = i;
    for (let r = i + 1; r < 6; r += 1) {
      if (Math.abs(M[r][i]) > Math.abs(M[piv][i])) {
        piv = r;
      }
    }
    const tmp = M[i];
    M[i] = M[piv];
    M[piv] = tmp;
    if (Math.abs(M[i][i]) < 1e-12) {
      continue;
    }
    const f = M[i][i];
    for (let c = i; c < 7; c += 1) {
      M[i][c] /= f;
    }
    for (let r = 0; r < 6; r += 1) {
      if (r === i) {
        continue;
      }
      const g = M[r][i];
      for (let c = i; c < 7; c += 1) {
        M[r][c] -= g * M[i][c];
      }
    }
  }
  return [M[0][6], M[1][6], M[2][6], M[3][6], M[4][6], M[5][6]];
}

export function solveIk(
  segments,
  limits,
  seed,
  targetPos,
  gripper,
  options
) {
  const opts = options || {};
  const posTol = opts.posTol != null ? opts.posTol : 0.004;
  const angTol = opts.angTol != null ? opts.angTol : 18;
  const maxIter = opts.maxIter != null ? opts.maxIter : 220;
  const oriWeightBase = opts.oriWeight != null ? opts.oriWeight : 0.12;
  const aw = gripper.approach_axis_world;
  const cw = gripper.closing_axis_world;
  let q = seed.map(Number);
  let best = null;
  for (let it = 0; it < maxIter; it += 1) {
    const pose = computeTcpPose(segments, q, gripper);
    const posD = Math.hypot(
      targetPos[0] - pose.position[0],
      targetPos[1] - pose.position[1],
      targetPos[2] - pose.position[2]
    );
    const angA = angleBetween(pose.approach, aw);
    const angC = angleBetween(pose.closing, cw);
    const score = posD + 0.002 * (angA + angC);
    if (!best || score < best.score) {
      best = {
        score: score,
        joints: q.slice(),
        posErr: posD,
        approachErrDeg: angA,
        closingErrDeg: angC,
        pose: pose,
      };
    }
    if (posD <= posTol && angA <= angTol && angC <= angTol) {
      return {
        ok: true,
        joints: q,
        posErr: posD,
        approachErrDeg: angA,
        closingErrDeg: angC,
        pose,
      };
    }
    // Once orientation is inside tolerance, emphasize position refinement.
    const oriOk = angA <= angTol && angC <= angTol;
    const oriWeight = oriOk ? oriWeightBase * 0.25 : oriWeightBase;
    const wErr = orientationTaskError(pose, aw, cw);
    const err = [
      targetPos[0] - pose.position[0],
      targetPos[1] - pose.position[1],
      targetPos[2] - pose.position[2],
      oriWeight * wErr[0],
      oriWeight * wErr[1],
      oriWeight * wErr[2],
    ];
    const eps = oriOk && posD < 0.01 ? 0.2 : 0.35;
    const J = [
      [0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0],
      [0, 0, 0, 0, 0, 0],
    ];
    for (let j = 0; j < 6; j += 1) {
      const q2 = q.slice();
      q2[j] += eps;
      const pose2 = computeTcpPose(segments, q2, gripper);
      const w2 = orientationTaskError(pose2, aw, cw);
      J[0][j] = (pose2.position[0] - pose.position[0]) / eps;
      J[1][j] = (pose2.position[1] - pose.position[1]) / eps;
      J[2][j] = (pose2.position[2] - pose.position[2]) / eps;
      J[3][j] = (oriWeight * (w2[0] - wErr[0])) / eps;
      J[4][j] = (oriWeight * (w2[1] - wErr[1])) / eps;
      J[5][j] = (oriWeight * (w2[2] - wErr[2])) / eps;
    }
    // DLS: dq = J^T (J J^T + λI)^{-1} err
    const l2 = oriOk && posD < 0.01 ? 0.0004 : 0.002;
    const A = [];
    for (let r = 0; r < 6; r += 1) {
      A[r] = [];
      for (let c = 0; c < 6; c += 1) {
        let s = r === c ? l2 : 0;
        for (let j = 0; j < 6; j += 1) {
          s += J[r][j] * J[c][j];
        }
        A[r][c] = s;
      }
    }
    const y = solveLinear6(A, err);
    let scale = oriOk && posD < 0.01 ? 0.85 : 1;
    const dq = [0, 0, 0, 0, 0, 0];
    for (let j = 0; j < 6; j += 1) {
      let s = 0;
      for (let r = 0; r < 6; r += 1) {
        s += J[r][j] * y[r];
      }
      dq[j] = s;
      if (Math.abs(dq[j]) > 4) {
        scale = Math.min(scale, 4 / Math.abs(dq[j]));
      }
    }
    const qNext = q.slice();
    for (let j = 0; j < 6; j += 1) {
      qNext[j] = clamp(q[j] + scale * dq[j], limits[j][0], limits[j][1]);
    }
    const poseNext = computeTcpPose(segments, qNext, gripper);
    const angA2 = angleBetween(poseNext.approach, aw);
    const angC2 = angleBetween(poseNext.closing, cw);
    if (angA2 > angTol + 5 || angC2 > angTol + 5) {
      for (let j = 0; j < 6; j += 1) {
        q[j] = clamp(0.5 * qNext[j] + 0.5 * q[j], limits[j][0], limits[j][1]);
      }
    } else {
      q = qNext;
    }
  }
  if (best && best.posErr <= posTol && best.approachErrDeg <= angTol && best.closingErrDeg <= angTol) {
    return {
      ok: true,
      joints: best.joints,
      posErr: best.posErr,
      approachErrDeg: best.approachErrDeg,
      closingErrDeg: best.closingErrDeg,
      pose: best.pose,
    };
  }
  if (best) {
    return {
      ok: false,
      joints: best.joints,
      posErr: best.posErr,
      approachErrDeg: best.approachErrDeg,
      closingErrDeg: best.closingErrDeg,
      pose: best.pose,
    };
  }
  const pose = computeTcpPose(segments, q, gripper);
  return {
    ok: false,
    joints: q,
    posErr: Math.hypot(
      targetPos[0] - pose.position[0],
      targetPos[1] - pose.position[1],
      targetPos[2] - pose.position[2]
    ),
    approachErrDeg: angleBetween(pose.approach, aw),
    closingErrDeg: angleBetween(pose.closing, cw),
    pose,
  };
}

export function solveIkWithSeeds(segments, limits, seeds, targetPos, gripper, options) {
  const opts = options || {};
  const j1AbsMin = opts.j1AbsMin;
  let ordered = seeds;
  if (j1AbsMin != null) {
    // Try rear/side yaw configurations first when a minimum |J1| is required.
    ordered = seeds.slice().sort(function (a, b) {
      return Math.abs(b[0]) - Math.abs(a[0]);
    });
  }
  let best = null;
  let bestPassingYaw = null;
  for (let i = 0; i < ordered.length; i += 1) {
    const result = solveIk(segments, limits, ordered[i], targetPos, gripper, opts);
    if (
      !best ||
      result.posErr + result.approachErrDeg * 0.01 <
        best.posErr + best.approachErrDeg * 0.01
    ) {
      best = result;
    }
    if (result.ok) {
      if (j1AbsMin != null && Math.abs(result.joints[0]) < j1AbsMin) {
        continue;
      }
      return result;
    }
  }
  if (j1AbsMin != null) {
    return {
      ok: false,
      reason: "no_yaw_config",
      j1AbsMin: j1AbsMin,
      joints: (best && best.joints) || ordered[0],
      posErr: best ? best.posErr : 1,
      approachErrDeg: best ? best.approachErrDeg : 180,
      closingErrDeg: best ? best.closingErrDeg : 180,
    };
  }
  return best || { ok: false, joints: seeds[0], posErr: 1, approachErrDeg: 180, closingErrDeg: 180 };
}

function assertObjectOnTable(table, object, xy) {
  const usableR =
    table.radius_m - table.edge_margin_m - object.radius_m;
  const radial = Math.hypot(xy[0] - table.center_xy_m[0], xy[1] - table.center_xy_m[1]);
  if (radial > usableR + 1e-9) {
    return { ok: false, reason: "object_outside_usable_table", usableR: usableR, radial: radial };
  }
  return { ok: true, usableR: usableR };
}

function lineSamples(p0, p1, stepM) {
  const dx = p1[0] - p0[0];
  const dy = p1[1] - p0[1];
  const dz = p1[2] - p0[2];
  const dist = Math.hypot(dx, dy, dz);
  const n = Math.max(2, Math.ceil(dist / stepM));
  const pts = [];
  for (let i = 0; i <= n; i += 1) {
    const t = i / n;
    pts.push([p0[0] + dx * t, p0[1] + dy * t, p0[2] + dz * t]);
  }
  return pts;
}

function verticalColumnSamples(xy, z0, z1, stepM) {
  return lineSamples([xy[0], xy[1], z0], [xy[0], xy[1], z1], stepM);
}

function planPhases(demo, model, phases, geometry) {
  const gripper = demo.gripper;
  const motion = demo.motion;
  const limits = model.joint_limits_deg;
  const home = model.home_joints_deg.slice();
  const segments = model.segments;
  const seeds = collectOrientedSeeds(segments, limits, gripper);
  seeds.unshift(home);
  const opts = {
    posTol: motion.ik_pos_tol_m,
    angTol: motion.ik_ang_tol_deg,
    maxIter: motion.ik_max_iter,
  };

  const planned = [];
  let seed = home.slice();
  const track = {
    maxXyDrift: 0,
    maxXyPhase: null,
    maxApproachToNegZDeg: 0,
    maxApproachPhase: null,
    maxClosingToNegXDeg: 0,
    maxClosingToNegXPhase: null,
    maxClosingPerpToObjectZDeg: 0,
    maxClosingPerpPhase: null,
  };

  function accumulate(phaseName, pose, refXy) {
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

  for (let p = 0; p < phases.length; p += 1) {
    const phase = phases[p];
    if (phase.type === "joint_path") {
      planned.push({
        name: phase.name,
        type: "path",
        jointsSeq: phase.jointsSeq.map(function (q) {
          return q.slice();
        }),
        fixedXy: false,
        refXy: null,
      });
      if (phase.jointsSeq.length) {
        seed = phase.jointsSeq[phase.jointsSeq.length - 1].slice();
      }
      continue;
    }
    if (phase.type === "action" || phase.type === "joint") {
      if (phase.type === "joint") {
        const pose = computeTcpPose(segments, phase.joints, gripper);
        planned.push({
          name: phase.name,
          type: "joint",
          joints: phase.joints.slice(),
          pose,
        });
        seed = phase.joints.slice();
      } else {
        planned.push({ name: phase.name, type: "action", action: phase.action });
      }
      continue;
    }
    const targets = phase.type === "path" ? phase.samples : [phase.target];
    const jointSeq = [];
    const refXy = phase.refXy || null;
    const phaseOpts =
      phase.j1AbsMin != null
        ? Object.assign({}, opts, { j1AbsMin: phase.j1AbsMin })
        : opts;
    for (let t = 0; t < targets.length; t += 1) {
      const tgt = targets[t];
      // Prefer seeds whose FK is near the target (important once yaw seeds cover ±X/±Y).
      const ranked = seeds
        .map(function (s) {
          const p = computeTcpPose(segments, s, gripper).position;
          const d = Math.hypot(p[0] - tgt[0], p[1] - tgt[1], p[2] - tgt[2]);
          return { s: s, d: d };
        })
        .sort(function (a, b) {
          return a.d - b.d;
        });
      const nearby = ranked.slice(0, 48).map(function (item) {
        return item.s;
      });
      const trySeeds = [seed].concat(nearby);
      const solved = solveIkWithSeeds(
        segments,
        limits,
        trySeeds,
        tgt,
        gripper,
        phaseOpts
      );
      if (!solved.ok) {
        return {
          ok: false,
          reason: "ik_failed",
          phase: phase.name,
          target: tgt,
          detail: solved,
        };
      }
      if (phase.fixedXy) {
        const m = accumulate(phase.name, solved.pose, refXy);
        if (m.xyDriftM > motion.path_xy_drift_max_m) {
          return {
            ok: false,
            reason: "xy_drift",
            phase: phase.name,
            drift: m.xyDriftM,
            limit: motion.path_xy_drift_max_m,
          };
        }
        if (m.approachToNegZDeg > motion.path_ang_drift_max_deg) {
          return {
            ok: false,
            reason: "approach_ang_drift",
            phase: phase.name,
            approachToNegZDeg: m.approachToNegZDeg,
            limit: motion.path_ang_drift_max_deg,
          };
        }
        if (m.closingToNegXDeg > motion.path_ang_drift_max_deg) {
          return {
            ok: false,
            reason: "closing_to_target_ang_drift",
            phase: phase.name,
            closingToNegXDeg: m.closingToNegXDeg,
            limit: motion.path_ang_drift_max_deg,
          };
        }
        const perpLim =
          motion.path_closing_perp_max_deg != null
            ? motion.path_closing_perp_max_deg
            : motion.path_ang_drift_max_deg;
        if (m.closingPerpToObjectZDeg > perpLim) {
          return {
            ok: false,
            reason: "closing_perp_ang_drift",
            phase: phase.name,
            closingPerpToObjectZDeg: m.closingPerpToObjectZDeg,
            limit: perpLim,
          };
        }
      } else {
        // Free path (e.g. Transfer): track orientation only — XY vs pick is not meaningful.
        const m = measurePoseErrors(solved.pose, demo, refXy);
        if (m.approachToNegZDeg >= track.maxApproachToNegZDeg) {
          track.maxApproachToNegZDeg = m.approachToNegZDeg;
          track.maxApproachPhase = phase.name;
        }
        if (m.closingToNegXDeg >= track.maxClosingToNegXDeg) {
          track.maxClosingToNegXDeg = m.closingToNegXDeg;
          track.maxClosingToNegXPhase = phase.name;
        }
        if (m.closingPerpToObjectZDeg >= track.maxClosingPerpToObjectZDeg) {
          track.maxClosingPerpToObjectZDeg = m.closingPerpToObjectZDeg;
          track.maxClosingPerpPhase = phase.name;
        }
      }
      jointSeq.push(solved.joints.slice());
      seed = solved.joints.slice();
    }
    planned.push({
      name: phase.name,
      type: "path",
      jointsSeq: jointSeq,
      fixedXy: !!phase.fixedXy,
      refXy: refXy ? refXy.slice() : null,
    });
  }

  return {
    ok: true,
    planned,
    metrics: {
      stage: "preflight",
      formulas: demo.derived.error_formulas,
      limits: {
        path_xy_drift_max_m: motion.path_xy_drift_max_m,
        path_ang_drift_max_deg: motion.path_ang_drift_max_deg,
        path_closing_perp_max_deg:
          motion.path_closing_perp_max_deg != null
            ? motion.path_closing_perp_max_deg
            : motion.path_ang_drift_max_deg,
        ik_pos_tol_m: motion.ik_pos_tol_m,
        ik_ang_tol_deg: motion.ik_ang_tol_deg,
      },
      maxXyDrift: track.maxXyDrift,
      maxXyPhase: track.maxXyPhase,
      maxApproachToNegZDeg: track.maxApproachToNegZDeg,
      maxApproachPhase: track.maxApproachPhase,
      maxClosingToNegXDeg: track.maxClosingToNegXDeg,
      maxClosingToNegXPhase: track.maxClosingToNegXPhase,
      maxClosingPerpToObjectZDeg: track.maxClosingPerpToObjectZDeg,
      maxClosingPerpPhase: track.maxClosingPerpPhase,
      maxApproachErrDeg: track.maxApproachToNegZDeg,
      maxClosingErrDeg: track.maxClosingToNegXDeg,
    },
    geometry: geometry,
  };
}

export function buildDemoWaypoints(demo, model) {
  if (demo.pattern === "front_back_transfer") {
    return buildFrontBackWaypoints(demo, model);
  }
  return buildVerticalInplaceWaypoints(demo, model);
}

function buildVerticalInplaceWaypoints(demo, model) {
  const table = demo.table;
  const object = demo.object;
  const gripper = demo.gripper;
  const motion = demo.motion;
  const xy = object.center_xy_m;
  const topZ = table.top_z_m;
  const objH = object.height_m;
  const centerZ = topZ + objH / 2;
  const approachZ = topZ + objH + gripper.approach_clearance_z_m;
  const graspZ = centerZ;
  const liftZ = graspZ + gripper.lift_height_m;
  const onTable = assertObjectOnTable(table, object, xy);
  if (!onTable.ok) {
    return onTable;
  }
  if (Math.abs(demo.derived.object_center_z_m - centerZ) > 1e-9) {
    return { ok: false, reason: "derived_center_z_mismatch" };
  }
  if (Math.abs(demo.derived.object_bottom_z_m - topZ) > 1e-9) {
    return { ok: false, reason: "derived_bottom_z_mismatch" };
  }

  const home = model.home_joints_deg.slice();
  const phases = [
    { name: "Home", type: "joint", joints: home, fixedXy: false },
    {
      name: "Approach",
      type: "cartesian",
      target: [xy[0], xy[1], approachZ],
      fixedXy: false,
    },
    {
      name: "Descend",
      type: "path",
      samples: verticalColumnSamples(xy, approachZ, graspZ, motion.cartesian_step_m),
      fixedXy: true,
      refXy: xy,
    },
    { name: "Grasp", type: "action", action: "close" },
    {
      name: "VerticalLift",
      type: "path",
      samples: verticalColumnSamples(xy, graspZ, liftZ, motion.cartesian_step_m),
      fixedXy: true,
      refXy: xy,
    },
    {
      name: "VerticalLower",
      type: "path",
      samples: verticalColumnSamples(xy, liftZ, graspZ, motion.cartesian_step_m),
      fixedXy: true,
      refXy: xy,
    },
    { name: "Release", type: "action", action: "open" },
    {
      name: "Retract",
      type: "path",
      samples: verticalColumnSamples(xy, graspZ, approachZ, motion.cartesian_step_m),
      fixedXy: true,
      refXy: xy,
    },
    { name: "ReturnHome", type: "joint", joints: home, fixedXy: false },
  ];

  return planPhases(demo, model, phases, {
    xy: xy,
    topZ: topZ,
    centerZ: centerZ,
    approachZ: approachZ,
    graspZ: graspZ,
    liftZ: liftZ,
    usableRadius: onTable.usableR,
  });
}

function buildFrontBackWaypoints(demo, model) {
  const pickTable = demo.pick_table || demo.table;
  const placeTable = demo.place_table;
  const object = demo.object;
  const gripper = demo.gripper;
  const motion = demo.motion;
  if (!placeTable) {
    return { ok: false, reason: "missing_place_table" };
  }
  const pickXy = demoPickXy(demo);
  const placeXy = demoPlaceXy(demo);
  const topZ = pickTable.top_z_m;
  if (Math.abs(placeTable.top_z_m - topZ) > 1e-9) {
    return { ok: false, reason: "pick_place_top_z_mismatch" };
  }
  const objH = object.height_m;
  const centerZ = topZ + objH / 2;
  const approachZ = topZ + objH + gripper.approach_clearance_z_m;
  const graspZ = centerZ;
  const liftZ = graspZ + gripper.lift_height_m;
  const carryZ =
    demo.derived && demo.derived.horizontal_carry_z_m != null
      ? demo.derived.horizontal_carry_z_m
      : liftZ;

  const pickOk = assertObjectOnTable(pickTable, object, pickXy);
  if (!pickOk.ok) {
    return Object.assign({ phase: "pick" }, pickOk);
  }
  const placeOk = assertObjectOnTable(placeTable, object, placeXy);
  if (!placeOk.ok) {
    return Object.assign({ phase: "place" }, placeOk);
  }
  if (Math.abs(demo.derived.object_center_z_m - centerZ) > 1e-9) {
    return { ok: false, reason: "derived_center_z_mismatch" };
  }
  if (Math.abs(demo.derived.object_bottom_z_m - topZ) > 1e-9) {
    return { ok: false, reason: "derived_bottom_z_mismatch" };
  }

  const home = model.home_joints_deg.slice();
  const step = motion.cartesian_step_m;
  // Side via (joint-space) keeps the grasped object outside the arm/base
  // during front→rear transfer. Place column keeps normal oriented IK.
  const keepoutR =
    motion.transfer_keepout_radius_m != null
      ? motion.transfer_keepout_radius_m
      : 0.2;
  const jointStepDeg =
    motion.transfer_joint_step_deg != null ? motion.transfer_joint_step_deg : 5;
  let viaXy = (motion.transfer_via_xy_m || [0, 0.4]).slice();
  const viaZ =
    motion.transfer_via_z_m != null ? motion.transfer_via_z_m : Math.max(carryZ, 0.42);
  const viaAngTol =
    motion.transfer_via_ang_tol_deg != null ? motion.transfer_via_ang_tol_deg : 90;
  const viaPosTol =
    motion.transfer_via_pos_tol_m != null ? motion.transfer_via_pos_tol_m : 0.008;

  const pickPhases = [
    { name: "Home", type: "joint", joints: home, fixedXy: false },
    {
      name: "ApproachPick",
      type: "cartesian",
      target: [pickXy[0], pickXy[1], approachZ],
      fixedXy: false,
    },
    {
      name: "DescendPick",
      type: "path",
      samples: verticalColumnSamples(pickXy, approachZ, graspZ, step),
      fixedXy: true,
      refXy: pickXy,
    },
    { name: "Grasp", type: "action", action: "close" },
    {
      name: "LiftPick",
      type: "path",
      samples: verticalColumnSamples(pickXy, graspZ, carryZ, step),
      fixedXy: true,
      refXy: pickXy,
    },
  ];

  const pickPlan = planPhases(demo, model, pickPhases, {
    pickXy: pickXy,
    placeXy: placeXy,
    topZ: topZ,
    centerZ: centerZ,
    approachZ: approachZ,
    graspZ: graspZ,
    liftZ: liftZ,
    carryZ: carryZ,
  });
  if (!pickPlan.ok) {
    return pickPlan;
  }
  const liftPhase = pickPlan.planned.find(function (p) {
    return p.name === "LiftPick";
  });
  const liftEnd = liftPhase.jointsSeq[liftPhase.jointsSeq.length - 1].slice();

  const limits = model.joint_limits_deg;
  const segments = model.segments;
  const seeds = collectOrientedSeeds(segments, limits, gripper);
  seeds.unshift(home);
  // Dense yaw/pitch seeds for side-via (orientation tolerance is loose there).
  const viaSeeds = [];
  for (const j1 of [-180, -135, -90, -45, 0, 45, 90, 135, 180]) {
    for (const j2 of [-100, -60, -40, -20, 0, 20, 40, 60]) {
      for (const j3 of [-100, -60, -20, 20, 60, 100]) {
        for (const j5 of [-80, -40, 0, 40, 80]) {
          viaSeeds.push([
            clamp(j1, limits[0][0], limits[0][1]),
            clamp(j2, limits[1][0], limits[1][1]),
            clamp(j3, limits[2][0], limits[2][1]),
            0,
            clamp(j5, limits[4][0], limits[4][1]),
            0,
          ]);
        }
      }
    }
  }

  function solveNear(target, angTol, posTol, j1AbsMin, seedPool) {
    const pool = seedPool || seeds;
    const ranked = pool
      .map(function (s) {
        const p = computeTcpPose(segments, s, gripper).position;
        const d = Math.hypot(
          p[0] - target[0],
          p[1] - target[1],
          p[2] - target[2]
        );
        return { s: s, d: d };
      })
      .sort(function (a, b) {
        return a.d - b.d;
      });
    const trySeeds = ranked.slice(0, 100).map(function (item) {
      return item.s;
    });
    return solveIkWithSeeds(segments, limits, trySeeds, target, gripper, {
      posTol: posTol,
      angTol: angTol,
      maxIter: motion.ik_max_iter,
      j1AbsMin: j1AbsMin,
    });
  }

  const viaTarget = [viaXy[0], viaXy[1], viaZ];
  let viaSol = solveNear(viaTarget, viaAngTol, viaPosTol, 60, viaSeeds);
  if (!viaSol.ok) {
    viaSol = solveNear(viaTarget, viaAngTol, viaPosTol, null, viaSeeds);
  }
  if (!viaSol.ok) {
    // Flip via to −Y and retry.
    const viaTargetNeg = [viaXy[0], -Math.abs(viaXy[1]), viaZ];
    viaSol = solveNear(viaTargetNeg, viaAngTol, viaPosTol, 60, viaSeeds);
    if (!viaSol.ok) {
      viaSol = solveNear(viaTargetNeg, viaAngTol, viaPosTol, null, viaSeeds);
    }
    if (viaSol.ok) {
      viaXy[1] = viaTargetNeg[1];
    }
  }
  if (!viaSol.ok) {
    return {
      ok: false,
      reason: "transfer_via_ik_failed",
      target: viaTarget,
      detail: viaSol,
    };
  }

  const placeCarryTgt = [placeXy[0], placeXy[1], carryZ];
  const placeCarry = solveNear(
    placeCarryTgt,
    motion.ik_ang_tol_deg,
    motion.ik_pos_tol_m,
    null
  );
  if (!placeCarry.ok) {
    return {
      ok: false,
      reason: "place_carry_ik_failed",
      target: placeCarryTgt,
      detail: placeCarry,
    };
  }

  // Cartesian side route at viaZ (loose orientation), then down to place carry.
  // Avoids joint-lerp shortcuts that collapse through the base.
  const transferCart = [];
  lineSamples(
    [pickXy[0], pickXy[1], carryZ],
    [viaXy[0], viaXy[1], viaZ],
    step
  ).forEach(function (p, i) {
    if (i > 0) {
      transferCart.push(p);
    }
  });
  lineSamples(
    [viaXy[0], viaXy[1], viaZ],
    [placeXy[0], placeXy[1], viaZ],
    step
  ).forEach(function (p, i) {
    if (i > 0) {
      transferCart.push(p);
    }
  });
  lineSamples(
    [placeXy[0], placeXy[1], viaZ],
    [placeXy[0], placeXy[1], carryZ],
    step
  ).forEach(function (p, i) {
    if (i > 0) {
      transferCart.push(p);
    }
  });

  const transferJoints = [];
  let seedQ = liftEnd.slice();
  let minTcpR = Infinity;
  for (let i = 0; i < transferCart.length; i += 1) {
    const tgt = transferCart[i];
    const rxy = Math.hypot(tgt[0], tgt[1]);
    if (rxy < keepoutR) {
      return {
        ok: false,
        reason: "transfer_keepout_target",
        target: tgt,
        keepoutR: keepoutR,
      };
    }
    const solved = solveNear(
      tgt,
      viaAngTol,
      viaPosTol,
      null,
      viaSeeds.concat([seedQ])
    );
    if (!solved.ok) {
      return {
        ok: false,
        reason: "transfer_sample_ik_failed",
        target: tgt,
        detail: solved,
      };
    }
    // Prefer continuous J1 (avoid ±360 jumps).
    let j1 = solved.joints[0];
    while (j1 - seedQ[0] > 180) {
      j1 -= 360;
    }
    while (j1 - seedQ[0] < -180) {
      j1 += 360;
    }
    if (j1 > limits[0][1] || j1 < limits[0][0]) {
      j1 = solved.joints[0];
    }
    const q = solved.joints.slice();
    q[0] = j1;
    const tcp = computeTcpPose(segments, q, gripper).position;
    minTcpR = Math.min(minTcpR, Math.hypot(tcp[0], tcp[1]));
    transferJoints.push(q);
    seedQ = q;
  }
  if (minTcpR < keepoutR) {
    return {
      ok: false,
      reason: "transfer_keepout",
      minTcpR: minTcpR,
      keepoutR: keepoutR,
      via: viaXy,
      viaZ: viaZ,
    };
  }
  // Ensure final transfer pose matches oriented place-carry for LowerPlace seed.
  transferJoints.push(placeCarry.joints.slice());

  const placePhasesSeeded = [
    { name: "PlaceCarrySeed", type: "joint", joints: placeCarry.joints },
    {
      name: "LowerPlace",
      type: "path",
      samples: verticalColumnSamples(placeXy, carryZ, graspZ, step),
      fixedXy: true,
      refXy: placeXy,
    },
    { name: "Release", type: "action", action: "open" },
    {
      name: "RetractPlace",
      type: "path",
      samples: verticalColumnSamples(placeXy, graspZ, approachZ, step),
      fixedXy: true,
      refXy: placeXy,
    },
    { name: "ReturnHome", type: "joint", joints: home, fixedXy: false },
  ];
  const placePlan = planPhases(demo, model, placePhasesSeeded, {
    pickXy: pickXy,
    placeXy: placeXy,
    topZ: topZ,
    centerZ: centerZ,
    approachZ: approachZ,
    graspZ: graspZ,
    liftZ: liftZ,
    carryZ: carryZ,
    transferMinTcpR: minTcpR,
    keepoutR: keepoutR,
    viaXy: viaXy.slice(),
    viaZ: viaZ,
    usableRadiusPick: pickOk.usableR,
    usableRadiusPlace: placeOk.usableR,
  });
  if (!placePlan.ok) {
    return placePlan;
  }
  const placePlanned = placePlan.planned.filter(function (p) {
    return p.name !== "PlaceCarrySeed";
  });
  const transferPlanned = {
    name: "Transfer",
    type: "path",
    jointsSeq: transferJoints,
    fixedXy: false,
    refXy: null,
  };

  const m1 = pickPlan.metrics;
  const m2 = placePlan.metrics;
  function pickMax(a, aPhase, b, bPhase) {
    return a >= b ? { v: a, p: aPhase } : { v: b, p: bPhase };
  }
  const xy = pickMax(m1.maxXyDrift, m1.maxXyPhase, m2.maxXyDrift, m2.maxXyPhase);
  const app = pickMax(
    m1.maxApproachToNegZDeg,
    m1.maxApproachPhase,
    m2.maxApproachToNegZDeg,
    m2.maxApproachPhase
  );
  const clo = pickMax(
    m1.maxClosingToNegXDeg,
    m1.maxClosingToNegXPhase,
    m2.maxClosingToNegXDeg,
    m2.maxClosingToNegXPhase
  );
  const perp = pickMax(
    m1.maxClosingPerpToObjectZDeg,
    m1.maxClosingPerpPhase,
    m2.maxClosingPerpToObjectZDeg,
    m2.maxClosingPerpPhase
  );

  return {
    ok: true,
    planned: pickPlan.planned.concat([transferPlanned], placePlanned),
    metrics: {
      stage: "preflight",
      formulas: demo.derived.error_formulas,
      limits: m1.limits,
      maxXyDrift: xy.v,
      maxXyPhase: xy.p,
      maxApproachToNegZDeg: app.v,
      maxApproachPhase: app.p,
      maxClosingToNegXDeg: clo.v,
      maxClosingToNegXPhase: clo.p,
      maxClosingPerpToObjectZDeg: perp.v,
      maxClosingPerpPhase: perp.p,
      maxApproachErrDeg: app.v,
      maxClosingErrDeg: clo.v,
      transferMinTcpR: minTcpR,
    },
    geometry: {
      pickXy: pickXy,
      placeXy: placeXy,
      topZ: topZ,
      centerZ: centerZ,
      approachZ: approachZ,
      graspZ: graspZ,
      liftZ: liftZ,
      carryZ: carryZ,
      viaXy: viaXy.slice(),
      viaZ: viaZ,
      transferMinTcpR: minTcpR,
      keepoutR: keepoutR,
      placeJ1: placeCarry.joints[0],
      viaJ1: viaSol.joints[0],
      usableRadiusPick: pickOk.usableR,
      usableRadiusPlace: placeOk.usableR,
    },
  };
}

export function gapContactForObject(demo) {
  return 2 * demo.object.radius_m + demo.gripper.contact_epsilon_m;
}

export function fingerInnerHalf(demo, gap) {
  return gap / 2;
}

export function fingerCenterX(demo, gap) {
  return gap / 2 + demo.gripper.finger_thickness_m / 2;
}
