import { createArmViewer } from "/static/js/virtual_demo_3d.js";
import { createCadStaticViewer } from "/static/js/virtual_demo_cad_3d.js?v=cad2";
import { createCarryDemoRunner } from "/static/js/carry_demo_runner.js?v=demo2fix4";
import {
  computeFlangeMatrix,
  computeTcpPose,
  sceneToRobot,
} from "/static/js/arm_kinematics.js";

const root = document.getElementById("virtualDemoRoot");
if (!root) {
  throw new Error("virtualDemoRoot missing");
}

const ui = {
  snapshot: null,
  viewer: null,
  animToken: 0,
  syncTimer: null,
  demoRunner: null,
  lastMetrics: null,
  localJoints: null,
  showJointLabels: true,
  /** True while moveJ / home / demo animation is in progress. */
  jointInputsLocked: false,
  /** Joint index being edited while idle; skip overwriting that field. */
  editingJointIndex: null,
  /** Target joints captured at moveJ start; not overwritten by live display. */
  savedMotionTarget: null,
  /** Demo2-only playback rate (×1 / ×2 / ×3). Reset to 1 on demo reset. */
  demoPlayRate: 1,
};

const DEMO2_KEY = "carry_front_back_2";

function isDemo2Selected(snapshot) {
  return !!(snapshot && snapshot.selected_demo_key === DEMO2_KEY);
}

function syncDemoSpeedButtons() {
  const wrap = document.getElementById("vdDemoSpeed");
  if (!wrap) {
    return;
  }
  const rate = Number(ui.demoPlayRate) || 1;
  wrap.querySelectorAll("[data-demo-rate]").forEach(function (btn) {
    const r = Number(btn.getAttribute("data-demo-rate"));
    btn.classList.toggle("is-active", r === rate);
    btn.setAttribute("aria-pressed", r === rate ? "true" : "false");
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail);
  }
  return response.json();
}

function readTargetJoints() {
  const joints = [];
  root.querySelectorAll("[data-target-index]").forEach(function (input) {
    joints[Number(input.getAttribute("data-target-index"))] = Number(input.value);
  });
  return joints;
}

function formatJointDeg(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "0";
  }
  return String(Math.round(n * 100) / 100);
}

function setJointAngleControlsLocked(locked) {
  ui.jointInputsLocked = !!locked;
  if (locked) {
    ui.editingJointIndex = null;
  }
  root.querySelectorAll("[data-target-index], [data-target-slider]").forEach(function (el) {
    el.disabled = !!locked;
  });
}

/** Clear saved moveJ target and re-enable angle inputs (E-stop / abort / complete). */
function releaseMotionControls() {
  ui.savedMotionTarget = null;
  setJointAngleControlsLocked(false);
}

/** Visible banner; create one if render omitted it (e.g. empty last_message). */
function showDemoBanner(text) {
  const msg = String(text || "").trim();
  if (!msg) {
    return;
  }
  let banner = document.querySelector(".vd-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.className = "vd-banner";
    if (root.firstChild) {
      root.insertBefore(banner, root.firstChild);
    } else {
      root.appendChild(banner);
    }
  }
  banner.textContent = msg;
}

/**
 * Human-readable reason when demo did not run / did not complete.
 * Prefer server last_message; else map last_result_key + state to action hints.
 */
function explainDemoOutcome(snapshot) {
  if (!snapshot) {
    return "示範無法啟動（無伺服器回應）。";
  }
  if (snapshot.last_message) {
    return String(snapshot.last_message);
  }
  const key = snapshot.last_result_key || "";
  const labels = snapshot.labels || {};
  if (key === "vd_result_estop" || snapshot.e_stopped) {
    return "緊急停止中，已拒絕。請先按「解除緊急停止」後再執行示範。";
  }
  if (key === "vd_result_not_connected" || !snapshot.connected) {
    return "尚未連線，已拒絕。請先按「連線」後再執行示範。";
  }
  if (key === "vd_demo_needs_reset" || snapshot.demo_run_state === "needs_reset") {
    return (labels.demo_needs_reset || "請先重置示範") + "。請按「重置示範」後再執行。";
  }
  if (key === "vd_demo_blocked") {
    return "示範執行中，已拒絕。請等待結束，或按緊急停止／重置示範。";
  }
  if (key === "vd_demo_model_unsupported") {
    return "目前型號不支援此示範。請切換至支援型號（如 ROKAE CR7）。";
  }
  if (key === "vd_result_unreachable") {
    return "路徑不可達／預檢失敗。請按「重置示範」後再試。";
  }
  if (!snapshot.selected_demo_key) {
    return "尚未選擇示範。請先在「示範」下拉選單選擇搬運示範。";
  }
  if (key) {
    return "示範未啟動：" + key;
  }
  return "示範未啟動。請確認已連線、已解除緊急停止，並已選擇示範。";
}

/**
 * Sync number inputs + sliders to a joint pose (degrees).
 * While idle, does not overwrite a field the user is actively editing.
 * While locked (motion), always mirrors the live pose — never writes set-target.
 */
function updateJointAngleControls(joints) {
  if (!joints || !joints.length) {
    return;
  }
  for (let i = 0; i < joints.length; i += 1) {
    if (!ui.jointInputsLocked) {
      if (ui.editingJointIndex === i) {
        continue;
      }
      const active = document.activeElement;
      if (
        active &&
        active.getAttribute &&
        active.getAttribute("data-target-index") === String(i)
      ) {
        continue;
      }
    }
    const num = root.querySelector("[data-target-index='" + i + "']");
    const slider = root.querySelector("[data-target-slider='" + i + "']");
    const text = formatJointDeg(joints[i]);
    if (num) {
      num.value = text;
    }
    if (slider) {
      const min = Number(slider.min);
      const max = Number(slider.max);
      let v = Number(joints[i]);
      if (Number.isFinite(min) && Number.isFinite(max)) {
        v = Math.max(min, Math.min(max, v));
      }
      slider.value = String(v);
    }
  }
}

function stopAnimation(token) {
  ui.animToken += 1;
  if (token !== undefined && token !== ui.animToken - 1) {
    return;
  }
  if (ui.syncTimer) {
    clearInterval(ui.syncTimer);
    ui.syncTimer = null;
  }
}

function syncCarryScene(snapshot) {
  if (!ui.viewer) {
    return;
  }
  if (
    snapshot.selected_demo_key &&
    snapshot.carry_demo &&
    snapshot.carry_demo.supported_models.indexOf(snapshot.model_key) >= 0
  ) {
    ui.viewer.setCarryDemo(
      snapshot.carry_demo,
      snapshot.demo_object_pose,
      snapshot.demo_gap_m
    );
    ui.viewer.setGrasped(!!snapshot.demo_grasped);
  } else {
    ui.viewer.clearCarry();
  }
}

function useCadStatic(snapshot) {
  const cad = snapshot.viewer_model && snapshot.viewer_model.cad_static;
  return !!(cad && cad.available && snapshot.viewer_model.display_mode === "cad_static");
}

function ensureViewer(snapshot) {
  const host = document.getElementById("vdViewer");
  if (!host) {
    return;
  }
  const modelKey = snapshot.viewer_model.model_key;
  const wantCad = useCadStatic(snapshot);
  const same =
    ui.viewer &&
    ui.viewer.modelKey === modelKey &&
    !!ui.viewer.isCadStatic === wantCad;
  if (same) {
    if (!wantCad) {
      ui.viewer.setJointsDeg(snapshot.current_joints);
      syncCarryScene(snapshot);
    }
    return;
  }
  if (ui.viewer) {
    ui.viewer.dispose();
    ui.viewer = null;
  }
  let viewer;
  if (wantCad) {
    viewer = createCadStaticViewer(host, snapshot.viewer_model.cad_static);
  } else {
    viewer = createArmViewer(
      host,
      snapshot.viewer_model,
      snapshot.current_joints
    );
    viewer.setJointLabelsVisible(ui.showJointLabels !== false);
    syncCarryScene(snapshot);
  }
  viewer.modelKey = modelKey;
  ui.viewer = viewer;
  window.__vdViewer = viewer;
}

function abortDemoLocal() {
  if (ui.demoRunner) {
    ui.demoRunner.abortLocal();
  }
}

function makeDemoRunner() {
  return createCarryDemoRunner({
    onJoints: function (joints) {
      ui.localJoints = joints.slice();
      updateLocalCurrent(joints);
    },
    onSnapshot: function (snap) {
      applySoftSnapshot(snap);
    },
    onMetrics: function (metrics) {
      ui.lastMetrics = metrics;
      window.__vdCarryMetrics = metrics;
      const el = document.getElementById("vdDemoMetrics");
      if (!el || !metrics) {
        return;
      }
      const pre = metrics.preflight || metrics;
      const run = metrics.runtime;
      let text =
        "pre XY=" +
        Number(pre.maxXyDrift).toFixed(4) +
        "m @" +
        (pre.maxXyPhase || "-") +
        " app=" +
        Number(pre.maxApproachToNegZDeg != null ? pre.maxApproachToNegZDeg : pre.maxApproachErrDeg).toFixed(1) +
        "° closeX=" +
        Number(pre.maxClosingToNegXDeg != null ? pre.maxClosingToNegXDeg : pre.maxClosingErrDeg).toFixed(1) +
        "° perp=" +
        Number(pre.maxClosingPerpToObjectZDeg || 0).toFixed(1) +
        "°";
      if (run) {
        text +=
          " | run XY=" +
          Number(run.maxXyDrift).toFixed(4) +
          "m app=" +
          Number(run.maxApproachToNegZDeg).toFixed(1) +
          "° closeX=" +
          Number(run.maxClosingToNegXDeg).toFixed(1) +
          "° perp=" +
          Number(run.maxClosingPerpToObjectZDeg).toFixed(1) +
          "°";
      }
      el.textContent = text;
    },
    getJoints: function () {
      if (ui.localJoints) {
        return ui.localJoints.slice();
      }
      return (ui.snapshot && ui.snapshot.current_joints) || [0, 0, 0, 0, 0, 0];
    },
    getObjectPose: function () {
      if (ui.viewer && ui.viewer.getObjectPose()) {
        return ui.viewer.getObjectPose();
      }
      return ui.snapshot.demo_object_pose;
    },
    setGap: function (gap) {
      if (ui.viewer) {
        ui.viewer.setGap(gap);
      }
    },
    getGap: function () {
      return ui.viewer ? ui.viewer.getGap() : 0.095;
    },
    setGrasped: function (v) {
      if (ui.viewer) {
        ui.viewer.setGrasped(v);
      }
    },
    isGrasped: function () {
      return ui.viewer ? ui.viewer.isGrasped() : false;
    },
    followObject: function (tcp, graspOffset) {
      if (!ui.viewer || !graspOffset) {
        return;
      }
      ui.viewer.setObjectPose({
        center_xyz_m: [
          tcp.position[0] + graspOffset.center[0],
          tcp.position[1] + graspOffset.center[1],
          tcp.position[2] + graspOffset.center[2],
        ],
        axis_world: graspOffset.axis.slice(),
      });
    },
    setObjectPose: function (pose) {
      if (ui.viewer && pose) {
        ui.viewer.setObjectPose(pose);
      }
    },
    getDemoPlayRate: function () {
      // Only demo2 playback uses a non-1 rate; demo1 / moveJ ignore this.
      if (!isDemo2Selected(ui.snapshot)) {
        return 1;
      }
      const r = Number(ui.demoPlayRate);
      return Number.isFinite(r) && r > 0 ? r : 1;
    },
  });
}

function applySoftSnapshot(snapshot) {
  ui.snapshot = snapshot;
  ui.localJoints = snapshot.current_joints.slice();
  const phaseEl = document.getElementById("vdDemoPhase");
  if (phaseEl) {
    phaseEl.textContent = snapshot.demo_phase || "-";
  }
  const stateEl = document.getElementById("vdDemoState");
  if (stateEl) {
    stateEl.textContent = snapshot.demo_run_state || "-";
  }
  const cur = document.getElementById("vdCurrentJoints");
  if (cur) {
    cur.textContent = JSON.stringify(snapshot.current_joints);
  }
  const tgt = document.getElementById("vdTargetJoints");
  if (tgt) {
    tgt.textContent = JSON.stringify(snapshot.target_joints);
  }
  if (ui.viewer) {
    ui.viewer.setJointsDeg(snapshot.current_joints);
    if (snapshot.demo_object_pose) {
      ui.viewer.setObjectPose(snapshot.demo_object_pose);
    }
    if (snapshot.demo_gap_m != null) {
      ui.viewer.setGap(snapshot.demo_gap_m);
    }
    ui.viewer.setGrasped(!!snapshot.demo_grasped);
  }
  if (ui.jointInputsLocked) {
    updateJointAngleControls(snapshot.current_joints);
  }
  const banner = document.querySelector(".vd-banner");
  if (banner && snapshot.last_message) {
    banner.textContent = snapshot.last_message;
  }
}

function renderIoGroup(title, map, kind) {
  let html = "<div class='vd-io-group'><h4>" + escapeHtml(title) + "</h4><div class='vd-io-grid'>";
  Object.keys(map)
    .sort(function (a, b) {
      return Number(a) - Number(b);
    })
    .forEach(function (pin) {
      const checked = map[pin] ? " checked" : "";
      html +=
        "<label class='vd-io-item'><span>" +
        escapeHtml(kind.toUpperCase()) +
        " " +
        escapeHtml(pin) +
        "</span><input type='checkbox' data-io-kind='" +
        escapeHtml(kind) +
        "' data-pin='" +
        escapeHtml(pin) +
        "'" +
        checked +
        "></label>";
    });
  html += "</div></div>";
  return html;
}

function render(snapshot) {
  ui.snapshot = snapshot;
  const labels = snapshot.labels;
  let modelOptions = "";
  snapshot.models.forEach(function (item) {
    modelOptions +=
      "<option value='" +
      escapeHtml(item.model_key) +
      "'" +
      (item.model_key === snapshot.model_key ? " selected" : "") +
      ">" +
      escapeHtml(item.label) +
      "</option>";
  });

  // Idle: show last actual pose (editable as next target). Moving: will be locked + live-synced.
  const angleDisplay = snapshot.current_joints;
  let targetInputs = "";
  for (let i = 0; i < snapshot.dof; i += 1) {
    const value = formatJointDeg(angleDisplay[i]);
    const limits = snapshot.joint_limits_deg[i];
    targetInputs +=
      "<label class='vd-joint-field'>J" +
      (i + 1) +
      " (°)" +
      "<input type='number' step='any' data-target-index='" +
      i +
      "' value='" +
      escapeHtml(value) +
      "'" +
      (ui.jointInputsLocked ? " disabled" : "") +
      ">" +
      "<input type='range' min='" +
      escapeHtml(limits[0]) +
      "' max='" +
      escapeHtml(limits[1]) +
      "' step='1' data-target-slider='" +
      i +
      "' value='" +
      escapeHtml(value) +
      "'" +
      (ui.jointInputsLocked ? " disabled" : "") +
      "></label>";
  }

  let logRows = "";
  snapshot.logs.forEach(function (item) {
    logRows +=
      "<tr><td>" +
      escapeHtml(item.time) +
      "</td><td>" +
      escapeHtml(item.action) +
      "</td><td>" +
      escapeHtml(item.result) +
      "</td></tr>";
  });

  let demoOptions =
    "<option value='none'" +
    (!snapshot.selected_demo_key ? " selected" : "") +
    ">" +
    escapeHtml(labels.demo_none) +
    "</option>";
  (snapshot.demos || []).forEach(function (item) {
    demoOptions +=
      "<option value='" +
      escapeHtml(item.demo_key) +
      "'" +
      (item.demo_key === snapshot.selected_demo_key ? " selected" : "") +
      ">" +
      escapeHtml(item.label) +
      "</option>";
  });

  const message = snapshot.last_message
    ? "<div class='vd-banner'>" + escapeHtml(snapshot.last_message) + "</div>"
    : "";

  const sameModel =
    ui.viewer &&
    snapshot.viewer_model &&
    ui.viewer.modelKey === snapshot.viewer_model.model_key;
  let parkedCanvas = null;
  let parkedLabelLayer = null;
  if (sameModel) {
    const host = document.getElementById("vdViewer");
    if (host && host.querySelector("canvas")) {
      parkedCanvas = host.querySelector("canvas");
      parkedCanvas.remove();
    }
    if (host && host.querySelector(".vd-joint-label-layer")) {
      parkedLabelLayer = host.querySelector(".vd-joint-label-layer");
      parkedLabelLayer.remove();
    }
  } else if (ui.viewer) {
    ui.viewer.dispose();
    ui.viewer = null;
    window.__vdViewer = null;
  }

  const cadMode = useCadStatic(snapshot);
  const disclaimerText = cadMode
    ? labels.cad_static_disclaimer || labels.schematic_disclaimer
    : labels.schematic_disclaimer;
  const section3dTitle = cadMode
    ? labels.section_3d_cad || labels.section_3d
    : labels.section_3d;
  root.innerHTML =
    "<div class='vd-disclaimer" +
    (cadMode ? " is-cad" : "") +
    "'>" +
    escapeHtml(disclaimerText) +
    "</div>" +
    message +
    "<div class='vd-layout'>" +
    "<section class='vd-card vd-viewer-card'><h3>" +
    escapeHtml(section3dTitle) +
    "</h3><div id='vdViewer' class='vd-viewer'></div>" +
    (cadMode
      ? ""
      : "<label class='vd-joint-label-toggle'><input type='checkbox' id='vdShowJointLabels'" +
        (ui.showJointLabels !== false ? " checked" : "") +
        "> " +
        escapeHtml(labels.show_joint_labels || "顯示關節標籤") +
        "</label>") +
    "</section>" +
    "<div class='vd-side'>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.section_robot) +
    "</h3><label class='control-block'><span>" +
    escapeHtml(labels.model_select) +
    "</span><select id='vdModelSelect'>" +
    modelOptions +
    "</select></label><p><strong>" +
    escapeHtml(labels.robot) +
    ":</strong> " +
    escapeHtml(snapshot.display_name) +
    " (" +
    escapeHtml(snapshot.robot_id) +
    ")</p><div class='vd-actions'>" +
    "<button type='button' id='vdConnect'>" +
    escapeHtml(labels.connect) +
    "</button><button type='button' id='vdDisconnect'>" +
    escapeHtml(labels.disconnect) +
    "</button><button type='button' id='vdEstop'>" +
    escapeHtml(labels.estop) +
    "</button><button type='button' id='vdResetEstop'>" +
    escapeHtml(labels.reset_estop) +
    "</button></div></section>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.section_status) +
    "</h3><div class='vd-status-grid'>" +
    "<div>" +
    escapeHtml(labels.connected) +
    ": <strong>" +
    escapeHtml(snapshot.connected ? labels.status_yes : labels.status_no) +
    "</strong></div><div>" +
    escapeHtml(labels.e_stopped) +
    ": <strong>" +
    escapeHtml(snapshot.e_stopped ? labels.status_yes : labels.status_no) +
    "</strong></div><div>" +
    escapeHtml(labels.is_moving) +
    ": <strong>" +
    escapeHtml(snapshot.is_moving ? labels.status_yes : labels.status_no) +
    "</strong></div><div>" +
    escapeHtml(labels.current_joints) +
    ": <code id='vdCurrentJoints'>" +
    escapeHtml(JSON.stringify(snapshot.current_joints)) +
    "</code></div><div>" +
    escapeHtml(labels.target_joints) +
    ": <code id='vdTargetJoints'>" +
    escapeHtml(JSON.stringify(snapshot.target_joints)) +
    "</code></div><div>" +
    escapeHtml(labels.pose) +
    ": <strong class='vd-pose-pending'>" +
    escapeHtml(snapshot.pose_text) +
    "</strong></div><p class='vd-hint'>" +
    escapeHtml(labels.demo_limits_note) +
    "</p></div></section>" +
    "</div></div>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.demo_select) +
    "</h3><label class='control-block'><span>" +
    escapeHtml(labels.demo_select) +
    "</span><select id='vdDemoSelect'>" +
    demoOptions +
    "</select></label><div class='vd-status-grid'><div>" +
    escapeHtml(labels.demo_phase) +
    ": <strong id='vdDemoPhase'>" +
    escapeHtml(snapshot.demo_phase || "-") +
    "</strong></div><div>state: <strong id='vdDemoState'>" +
    escapeHtml(snapshot.demo_run_state || "-") +
    "</strong></div><div id='vdDemoMetrics' class='vd-hint'></div></div>" +
    (snapshot.selected_demo_key === "carry_front_back_2"
      ? "<div class=\"vd-demo-speed\" id=\"vdDemoSpeed\"><span class=\"vd-demo-speed-label\">" +
        escapeHtml(labels.demo_speed || "播放速度") +
        "</span><div class=\"vd-demo-speed-btns\" role=\"group\" aria-label=\"" +
        escapeHtml(labels.demo_speed || "播放速度") +
        "\">" +
        "<button type=\"button\" data-demo-rate=\"1\" class=\"" +
        (Number(ui.demoPlayRate) === 1 ? "is-active" : "") +
        "\" aria-pressed=\"" +
        (Number(ui.demoPlayRate) === 1 ? "true" : "false") +
        "\">" +
        escapeHtml(labels.demo_speed_x1 || "×1 正常") +
        "</button><button type=\"button\" data-demo-rate=\"2\" class=\"" +
        (Number(ui.demoPlayRate) === 2 ? "is-active" : "") +
        "\" aria-pressed=\"" +
        (Number(ui.demoPlayRate) === 2 ? "true" : "false") +
        "\">" +
        escapeHtml(labels.demo_speed_x2 || "×2") +
        "</button><button type=\"button\" data-demo-rate=\"3\" class=\"" +
        (Number(ui.demoPlayRate) === 3 ? "is-active" : "") +
        "\" aria-pressed=\"" +
        (Number(ui.demoPlayRate) === 3 ? "true" : "false") +
        "\">" +
        escapeHtml(labels.demo_speed_x3 || "×3") +
        "</button></div></div>"
      : "") +
    "<div class='vd-actions'>" +
    "<button type='button' id='vdRunDemo'>" +
    escapeHtml(labels.run_demo) +
    "</button><button type='button' id='vdResetDemo'>" +
    escapeHtml(labels.reset_demo) +
    "</button></div></section>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.section_motion) +
    "</h3><p class='vd-hint'>" +
    escapeHtml(labels.joint_hint) +
    "</p><div class='vd-joint-grid'>" +
    targetInputs +
    "</div><div class='vd-actions'>" +
    "<button type='button' id='vdMoveHome'>" +
    escapeHtml(labels.move_home) +
    "</button><button type='button' id='vdMoveJ'>" +
    escapeHtml(labels.move_j) +
    "</button></div></section>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.section_io) +
    "</h3>" +
    renderIoGroup(labels.do, snapshot.digital_outputs, "do") +
    renderIoGroup(labels.di, snapshot.digital_inputs, "di") +
    "</section>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.section_unimplemented) +
    "</h3><div class='vd-actions'>" +
    "<button type='button' class='vd-unimplemented' data-action='vd_action_move_l'>" +
    escapeHtml(labels.move_l) +
    "</button><button type='button' class='vd-unimplemented' data-action='vd_action_move_servo'>" +
    escapeHtml(labels.move_servo) +
    "</button><button type='button' class='vd-unimplemented' data-action='vd_action_move_line'>" +
    escapeHtml(labels.move_line) +
    "</button><button type='button' class='vd-unimplemented' data-action='vd_action_sync_move'>" +
    escapeHtml(labels.sync_move) +
    "</button><button type='button' class='vd-unimplemented' data-action='vd_action_torch'>" +
    escapeHtml(labels.torch) +
    "</button><button type='button' class='vd-unimplemented' data-action='vd_action_weld'>" +
    escapeHtml(labels.weld) +
    "</button></div></section>" +
    "<section class='vd-card'><h3>" +
    escapeHtml(labels.log_title) +
    "</h3><div class='vd-table-wrap'><table class='vd-log-table'><thead><tr><th>" +
    escapeHtml(labels.log_time) +
    "</th><th>" +
    escapeHtml(labels.log_action) +
    "</th><th>" +
    escapeHtml(labels.log_result) +
    "</th></tr></thead><tbody>" +
    logRows +
    "</tbody></table></div></section>";

  if (sameModel && parkedCanvas && ui.viewer) {
    const host = document.getElementById("vdViewer");
    host.appendChild(parkedCanvas);
    if (parkedLabelLayer) {
      host.appendChild(parkedLabelLayer);
    }
    ui.viewer.setJointsDeg(snapshot.current_joints);
    if (ui.viewer.setJointLabelsVisible) {
      ui.viewer.setJointLabelsVisible(ui.showJointLabels !== false);
    }
    window.__vdViewer = ui.viewer;
    syncCarryScene(snapshot);
  } else {
    ensureViewer(snapshot);
  }
  ui.localJoints = snapshot.current_joints.slice();
  if (ui.lastMetrics) {
    const el = document.getElementById("vdDemoMetrics");
    if (el) {
      const pre = ui.lastMetrics.preflight || ui.lastMetrics;
      const run = ui.lastMetrics.runtime;
      let text =
        "pre XY=" +
        Number(pre.maxXyDrift).toFixed(4) +
        "m app=" +
        Number(
          pre.maxApproachToNegZDeg != null
            ? pre.maxApproachToNegZDeg
            : pre.maxApproachErrDeg
        ).toFixed(1) +
        "° closeX=" +
        Number(
          pre.maxClosingToNegXDeg != null
            ? pre.maxClosingToNegXDeg
            : pre.maxClosingErrDeg
        ).toFixed(1) +
        "° perp=" +
        Number(pre.maxClosingPerpToObjectZDeg || 0).toFixed(1) +
        "°";
      if (run) {
        text +=
          " | run XY=" +
          Number(run.maxXyDrift).toFixed(4) +
          "m app=" +
          Number(run.maxApproachToNegZDeg).toFixed(1) +
          "° closeX=" +
          Number(run.maxClosingToNegXDeg).toFixed(1) +
          "° perp=" +
          Number(run.maxClosingPerpToObjectZDeg).toFixed(1) +
          "°";
      }
      el.textContent = text;
    }
  }
  bind(snapshot);
}

function updateLocalCurrent(joints) {
  ui.localJoints = joints.slice();
  const el = document.getElementById("vdCurrentJoints");
  if (el) {
    el.textContent = JSON.stringify(joints);
  }
  if (ui.viewer) {
    ui.viewer.setJointsDeg(joints);
  }
  // Same live pose drives angle inputs/sliders (when locked / not editing).
  updateJointAngleControls(joints);
}

async function runMotionAnimation(snapshot) {
  stopAnimation();
  setJointAngleControlsLocked(true);
  const token = ui.animToken;
  const start = snapshot.current_joints.slice();
  // Prefer target captured at click; fall back to server target_joints.
  const target = (ui.savedMotionTarget || snapshot.target_joints).slice();
  const speed = Number(snapshot.animation_deg_per_sec) || 45;
  let maxDelta = 0;
  for (let i = 0; i < start.length; i += 1) {
    maxDelta = Math.max(maxDelta, Math.abs(target[i] - start[i]));
  }
  const durationMs = Math.max(200, (maxDelta / speed) * 1000);
  const t0 = performance.now();

  // Show start pose immediately (not the motion end target).
  updateLocalCurrent(start);

  ui.syncTimer = setInterval(async function () {
    if (token !== ui.animToken) {
      return;
    }
    if (!ui.localJoints) {
      return;
    }
    try {
      await api("/api/virtual-demo/update-current", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ joints: ui.localJoints }),
      });
    } catch (err) {
      // keep animating local view; next poll may recover
    }
  }, 120);

  function frame(now) {
    if (token !== ui.animToken) {
      return;
    }
    const ratio = Math.min(1, (now - t0) / durationMs);
    const joints = start.map(function (value, index) {
      return value + (target[index] - value) * ratio;
    });
    updateLocalCurrent(joints);
    if (ratio < 1) {
      requestAnimationFrame(frame);
      return;
    }
    stopAnimation(token);
    api("/api/virtual-demo/complete-motion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then(function (next) {
        releaseMotionControls();
        render(next);
      })
      .catch(function (err) {
        releaseMotionControls();
        root.textContent = String(err);
      });
  }
  requestAnimationFrame(frame);
}

function bind(snapshot) {
  document.getElementById("vdModelSelect").addEventListener("change", async function (event) {
    stopAnimation();
    abortDemoLocal();
    releaseMotionControls();
    if (ui.viewer) {
      ui.viewer.dispose();
      ui.viewer = null;
    }
    const next = await api("/api/virtual-demo/select-model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_key: event.target.value }),
    });
    render(next);
  });

  const showLabels = document.getElementById("vdShowJointLabels");
  if (showLabels) {
    showLabels.addEventListener("change", function () {
      ui.showJointLabels = !!showLabels.checked;
      if (ui.viewer && ui.viewer.setJointLabelsVisible) {
        ui.viewer.setJointLabelsVisible(ui.showJointLabels);
      }
    });
  }

  document.getElementById("vdDemoSelect").addEventListener("change", async function (event) {
    stopAnimation();
    abortDemoLocal();
    releaseMotionControls();
    const next = await api("/api/virtual-demo/select-demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demo_key: event.target.value }),
    });
    render(next);
  });

  const speedWrap = document.getElementById("vdDemoSpeed");
  if (speedWrap) {
    speedWrap.addEventListener("click", function (event) {
      const btn = event.target.closest("[data-demo-rate]");
      if (!btn) {
        return;
      }
      const rate = Number(btn.getAttribute("data-demo-rate"));
      if (!Number.isFinite(rate) || rate <= 0) {
        return;
      }
      ui.demoPlayRate = rate;
      syncDemoSpeedButtons();
    });
  }

  document.getElementById("vdRunDemo").addEventListener("click", async function () {
    if (ui.demoRunner && ui.demoRunner.isRunning()) {
      showDemoBanner("示範執行中，請等待完成，或按「緊急停止」／「重置示範」。");
      return;
    }
    const snap = ui.snapshot;
    if (!snap || !snap.selected_demo_key) {
      showDemoBanner("尚未選擇示範。請先在「示範」下拉選單選擇搬運示範。");
      return;
    }
    if (!snap.connected) {
      showDemoBanner("尚未連線，無法執行示範。請先按「連線」。");
      return;
    }
    if (snap.e_stopped) {
      showDemoBanner("緊急停止中，無法執行示範。請先按「解除緊急停止」。");
      return;
    }
    if (snap.demo_run_state === "needs_reset") {
      showDemoBanner("示範需先重置。請按「重置示範」後再執行。");
      return;
    }
    if (
      snap.carry_demo &&
      snap.carry_demo.supported_models &&
      snap.carry_demo.supported_models.indexOf(snap.model_key) < 0
    ) {
      showDemoBanner("目前型號不支援此示範。請切換至支援型號（如 ROKAE CR7）。");
      return;
    }

    stopAnimation();
    abortDemoLocal();
    setJointAngleControlsLocked(true);
    ui.demoRunner = makeDemoRunner();
    try {
      const done = await ui.demoRunner.run();
      releaseMotionControls();
      if (!done) {
        showDemoBanner("示範未啟動（無回應）。");
        return;
      }
      // Rejected at start: demo_started === false (explicit) or missing after idle reject.
      if (done.demo_started === false || (done.demo_run_state === "idle" && !done.demo_started)) {
        done.last_message = explainDemoOutcome(done);
        render(done);
        showDemoBanner(done.last_message);
        return;
      }
      if (done.demo_run_state === "needs_reset") {
        done.last_message = explainDemoOutcome(done);
        render(done);
        showDemoBanner(done.last_message);
        return;
      }
      render(done);
      if (done.demo_run_state === "completed" && done.last_message) {
        showDemoBanner(done.last_message);
      }
    } catch (err) {
      releaseMotionControls();
      let state = null;
      try {
        state = await api("/api/virtual-demo/state");
      } catch (stateErr) {
        showDemoBanner(String(err.message || err));
        return;
      }
      const detail = String(err.message || err);
      state.last_message = detail.indexOf("aborted") >= 0
        ? "示範已中止。"
        : "示範失敗：" + detail + "。若狀態為 needs_reset，請按「重置示範」。";
      render(state);
      showDemoBanner(state.last_message);
    }
  });

  document.getElementById("vdResetDemo").addEventListener("click", async function () {
    stopAnimation();
    abortDemoLocal();
    releaseMotionControls();
    ui.demoPlayRate = 1;
    const next = await api("/api/virtual-demo/demo/reset", { method: "POST" });
    ui.lastMetrics = null;
    render(next);
  });

  document.getElementById("vdConnect").addEventListener("click", async function () {
    render(await api("/api/virtual-demo/connect", { method: "POST" }));
  });
  document.getElementById("vdDisconnect").addEventListener("click", async function () {
    stopAnimation();
    abortDemoLocal();
    const stopJoints =
      ui.localJoints ||
      (ui.snapshot && ui.snapshot.current_joints) ||
      null;
    if (stopJoints) {
      await api("/api/virtual-demo/update-current", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ joints: stopJoints }),
      }).catch(function () {
        return null;
      });
    }
    if (ui.viewer && ui.snapshot && ui.snapshot.demo_run_state === "running") {
      await api("/api/virtual-demo/demo/runtime", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          aborted: true,
          phase: "Aborted",
          grasped: ui.viewer.isGrasped(),
          gap_m: ui.viewer.getGap(),
          object_pose: ui.viewer.getObjectPose(),
        }),
      }).catch(function () {
        return null;
      });
    }
    releaseMotionControls();
    render(await api("/api/virtual-demo/disconnect", { method: "POST" }));
  });
  document.getElementById("vdEstop").addEventListener("click", async function () {
    stopAnimation();
    abortDemoLocal();
    const stopJoints =
      ui.localJoints ||
      (ui.snapshot && ui.snapshot.current_joints) ||
      null;
    if (stopJoints) {
      await api("/api/virtual-demo/update-current", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ joints: stopJoints }),
      }).catch(function () {
        return null;
      });
    }
    // Persist grasp/gap/object before marking aborted on server if demo was running
    if (ui.viewer && ui.snapshot && ui.snapshot.demo_run_state === "running") {
      await api("/api/virtual-demo/demo/runtime", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          aborted: true,
          phase: "Aborted",
          grasped: ui.viewer.isGrasped(),
          gap_m: ui.viewer.getGap(),
          object_pose: ui.viewer.getObjectPose(),
        }),
      }).catch(function () {
        return null;
      });
    }
    releaseMotionControls();
    render(await api("/api/virtual-demo/estop", { method: "POST" }));
  });
  document.getElementById("vdResetEstop").addEventListener("click", async function () {
    releaseMotionControls();
    render(await api("/api/virtual-demo/reset-estop", { method: "POST" }));
  });

  root.querySelectorAll("[data-target-index]").forEach(function (input) {
    const index = Number(input.getAttribute("data-target-index"));
    input.addEventListener("focus", function () {
      if (!ui.jointInputsLocked) {
        ui.editingJointIndex = index;
      }
    });
    input.addEventListener("blur", function () {
      if (ui.editingJointIndex === index) {
        ui.editingJointIndex = null;
      }
    });
    input.addEventListener("change", async function () {
      if (ui.jointInputsLocked) {
        return;
      }
      const joints = readTargetJoints();
      const slider = root.querySelector(
        "[data-target-slider='" + input.getAttribute("data-target-index") + "']"
      );
      if (slider) {
        slider.value = input.value;
      }
      const next = await api("/api/virtual-demo/set-target", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ joints: joints }),
      });
      const targetEl = document.getElementById("vdTargetJoints");
      if (targetEl) {
        targetEl.textContent = JSON.stringify(next.target_joints);
      }
    });
  });

  root.querySelectorAll("[data-target-slider]").forEach(function (slider) {
    const index = Number(slider.getAttribute("data-target-slider"));
    slider.addEventListener("pointerdown", function () {
      if (!ui.jointInputsLocked) {
        ui.editingJointIndex = index;
      }
    });
    slider.addEventListener("pointerup", function () {
      if (ui.editingJointIndex === index) {
        ui.editingJointIndex = null;
      }
    });
    slider.addEventListener("input", function () {
      if (ui.jointInputsLocked) {
        return;
      }
      ui.editingJointIndex = index;
      const numberInput = root.querySelector("[data-target-index='" + index + "']");
      if (numberInput) {
        numberInput.value = slider.value;
      }
    });
    slider.addEventListener("change", async function () {
      if (ui.jointInputsLocked) {
        return;
      }
      ui.editingJointIndex = null;
      const joints = readTargetJoints();
      const next = await api("/api/virtual-demo/set-target", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ joints: joints }),
      });
      const targetEl = document.getElementById("vdTargetJoints");
      if (targetEl) {
        targetEl.textContent = JSON.stringify(next.target_joints);
      }
    });
  });

  document.getElementById("vdMoveHome").addEventListener("click", async function () {
    if (ui.jointInputsLocked) {
      return;
    }
    const next = await api("/api/virtual-demo/move-home", { method: "POST" });
    if (next.motion_started) {
      ui.savedMotionTarget = next.target_joints.slice();
      ui.snapshot = next;
      setJointAngleControlsLocked(true);
      updateLocalCurrent(next.current_joints);
      const tgt = document.getElementById("vdTargetJoints");
      if (tgt) {
        tgt.textContent = JSON.stringify(next.target_joints);
      }
      runMotionAnimation(next);
    } else {
      render(next);
    }
  });

  document.getElementById("vdMoveJ").addEventListener("click", async function () {
    if (ui.jointInputsLocked) {
      return;
    }
    // Capture full target before live display switches to current pose.
    const joints = readTargetJoints();
    ui.savedMotionTarget = joints.slice();
    const next = await api("/api/virtual-demo/move-j", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ joints: joints }),
    });
    if (next.motion_started) {
      ui.snapshot = next;
      setJointAngleControlsLocked(true);
      // Show actual start pose — not the end target — then animate.
      updateLocalCurrent(next.current_joints);
      const tgt = document.getElementById("vdTargetJoints");
      if (tgt) {
        tgt.textContent = JSON.stringify(next.target_joints);
      }
      runMotionAnimation(next);
    } else {
      releaseMotionControls();
      render(next);
    }
  });

  root.querySelectorAll("[data-io-kind]").forEach(function (input) {
    input.addEventListener("change", async function () {
      const kind = input.getAttribute("data-io-kind");
      const pin = Number(input.getAttribute("data-pin"));
      const url = kind === "do" ? "/api/virtual-demo/set-do" : "/api/virtual-demo/set-di";
      render(
        await api(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin: pin, value: input.checked }),
        })
      );
    });
  });

  root.querySelectorAll(".vd-unimplemented").forEach(function (button) {
    button.addEventListener("click", async function () {
      render(
        await api("/api/virtual-demo/not-implemented", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action_key: button.getAttribute("data-action") }),
        })
      );
    });
  });
}

function verifyFkViewerConsistency(jointsDeg) {
  if (!ui.viewer || !ui.snapshot) {
    return { ok: false, reason: "no_viewer" };
  }
  const joints = jointsDeg || ui.snapshot.current_joints;
  const segments = ui.snapshot.viewer_model.segments;
  ui.viewer.setJointsDeg(joints);
  const fk = computeFlangeMatrix(segments, joints);
  const fkPos = [fk[0][3], fk[1][3], fk[2][3]];
  const scenePos = ui.viewer.getFlangeWorldPos();
  const viewerRobot = sceneToRobot([scenePos.x, scenePos.y, scenePos.z]);
  const err = Math.hypot(
    fkPos[0] - viewerRobot[0],
    fkPos[1] - viewerRobot[1],
    fkPos[2] - viewerRobot[2]
  );
  let tcpErr = null;
  if (ui.snapshot.carry_demo) {
    const g = ui.snapshot.carry_demo.gripper;
    const tcp = computeTcpPose(segments, joints, g);
    const tcpScene = ui.viewer.getTcpWorldPos(g.tcp_offset_xyz_m);
    const tcpRobot = sceneToRobot([tcpScene.x, tcpScene.y, tcpScene.z]);
    tcpErr = Math.hypot(
      tcp.position[0] - tcpRobot[0],
      tcp.position[1] - tcpRobot[1],
      tcp.position[2] - tcpRobot[2]
    );
  }
  return {
    ok: err < 1e-4 && (tcpErr == null || tcpErr < 1e-4),
    flangeErrM: err,
    tcpErrM: tcpErr,
    fkPos: fkPos,
    viewerRobot: viewerRobot,
  };
}

window.__vdVerifyFk = verifyFkViewerConsistency;
window.__vdUi = ui;

api("/api/virtual-demo/state")
  .then(function (snapshot) {
    render(snapshot);
  })
  .catch(function (error) {
    root.textContent = String(error);
  });
