import { createArmViewer } from "/static/js/virtual_demo_3d.js";
import { createCarryDemoRunner } from "/static/js/carry_demo_runner.js?v=wf_anim1";

const root = document.getElementById("workflowRunRoot");
if (!root) {
  throw new Error("workflowRunRoot missing");
}

const state = {
  labels: null,
  status: null,
  selectedWorkflowTxId: null,
  pollTimer: null,
  message: "",
  messageError: false,
  viewer: null,
  demoRunner: null,
  snapshot: null,
  animBusy: false,
  lastAnimSeq: null,
};

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function api(url, options) {
  const response = await fetch(url, options || {});
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (err) {
    data = { detail: text };
  }
  if (!response.ok) {
    const detail =
      data && data.detail != null ? data.detail : text || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function findSelectedWorkflowTxId() {
  const tableRoot = document.getElementById("tableUiRoot");
  if (!tableRoot) {
    return null;
  }
  const selected = tableRoot.querySelector(
    ".tui-data-table tbody tr.is-current, .tui-data-table tbody tr.is-selected"
  );
  if (selected && selected.getAttribute("data-txid")) {
    return Number(selected.getAttribute("data-txid"));
  }
  const first = tableRoot.querySelector(".tui-data-table tbody tr[data-txid]");
  if (first) {
    return Number(first.getAttribute("data-txid"));
  }
  return null;
}

function stepStatusClass(status) {
  if (status === "running") {
    return "is-running";
  }
  if (status === "completed") {
    return "is-completed";
  }
  if (status === "error") {
    return "is-error";
  }
  return "";
}

function stepStatusLabel(status, labels) {
  const key = "wf_run_step_" + status;
  return labels[key] || status;
}

function ensureViewerHost() {
  let host = document.getElementById("wfRunViewerHost");
  if (!host) {
    host = document.createElement("div");
    host.id = "wfRunViewerHost";
    host.className = "wf-run-viewer-host";
    root.appendChild(host);
  }
  return host;
}

function syncViewer(snapshot) {
  if (!snapshot || !snapshot.viewer_model) {
    return;
  }
  const host = ensureViewerHost();
  const modelKey = snapshot.viewer_model.model_key;
  if (state.viewer && state.viewer.modelKey === modelKey) {
    state.viewer.setJointsDeg(snapshot.current_joints || []);
    if (snapshot.carry_demo && state.viewer.setCarryDemo) {
      state.viewer.setCarryDemo(
        snapshot.carry_demo,
        snapshot.demo_object_pose,
        snapshot.demo_gap_m
      );
      if (state.viewer.setGrasped) {
        state.viewer.setGrasped(!!snapshot.demo_grasped);
      }
    }
    return;
  }
  if (state.viewer && state.viewer.dispose) {
    state.viewer.dispose();
  }
  host.innerHTML = "";
  const viewer = createArmViewer(
    host,
    snapshot.viewer_model,
    snapshot.current_joints || []
  );
  viewer.modelKey = modelKey;
  state.viewer = viewer;
  if (snapshot.carry_demo && viewer.setCarryDemo) {
    viewer.setCarryDemo(
      snapshot.carry_demo,
      snapshot.demo_object_pose,
      snapshot.demo_gap_m
    );
    if (viewer.setGrasped) {
      viewer.setGrasped(!!snapshot.demo_grasped);
    }
  }
}

function makeDemoRunner() {
  return createCarryDemoRunner({
    onJoints: function (joints) {
      if (state.viewer) {
        state.viewer.setJointsDeg(joints);
      }
      if (state.snapshot) {
        state.snapshot.current_joints = joints.slice();
      }
    },
    onSnapshot: function (snap) {
      state.snapshot = snap;
      syncViewer(snap);
    },
    onMetrics: function () {},
    getJoints: function () {
      return (
        (state.snapshot && state.snapshot.current_joints) ||
        [0, 0, 0, 0, 0, 0]
      );
    },
    getObjectPose: function () {
      if (state.viewer && state.viewer.getObjectPose) {
        return state.viewer.getObjectPose();
      }
      return (
        (state.snapshot && state.snapshot.demo_object_pose) || {
          center_xyz_m: [0.35, 0, 0.22],
          axis_world: [0, 0, 1],
        }
      );
    },
    setObjectPose: function (pose) {
      if (state.viewer && state.viewer.setObjectPose) {
        state.viewer.setObjectPose(pose);
      }
    },
    getGap: function () {
      return state.snapshot ? state.snapshot.demo_gap_m : 0.095;
    },
    setGap: function (gap) {
      if (state.snapshot) {
        state.snapshot.demo_gap_m = gap;
      }
      if (state.viewer && state.viewer.setGap) {
        state.viewer.setGap(gap);
      }
    },
    isGrasped: function () {
      return !!(state.snapshot && state.snapshot.demo_grasped);
    },
    setGrasped: function (v) {
      if (state.snapshot) {
        state.snapshot.demo_grasped = !!v;
      }
      if (state.viewer && state.viewer.setGrasped) {
        state.viewer.setGrasped(!!v);
      }
    },
  });
}

async function ensureDemoContext() {
  const snap = await api("/api/virtual-demo/state");
  state.snapshot = snap;
  syncViewer(snap);
  if (!state.demoRunner) {
    state.demoRunner = makeDemoRunner();
  }
  return snap;
}

async function handleAnimationCue(status) {
  const cue = status && status.animation;
  if (!cue || state.animBusy) {
    return;
  }
  if (state.lastAnimSeq === cue.seq) {
    return;
  }
  state.animBusy = true;
  state.lastAnimSeq = cue.seq;
  try {
    await ensureDemoContext();
    if (state.demoRunner && state.demoRunner.resetSegmentState && cue.seq === 1) {
      const demo = state.snapshot && state.snapshot.carry_demo;
      if (demo) {
        state.demoRunner.resetSegmentState(demo);
      }
    }
    await state.demoRunner.runNamedPhases(cue.phases || [], {
      snapshot: state.snapshot,
      allowNested: true,
    });
    await api("/api/workflow-runs/animation-ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_txid: cue.run_txid,
        step_txid: cue.step_txid,
        seq: cue.seq,
        ok: true,
      }),
    });
  } catch (err) {
    const msg = String(err && err.message ? err.message : err);
    try {
      await api("/api/workflow-runs/animation-ack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_txid: cue.run_txid,
          step_txid: cue.step_txid,
          seq: cue.seq,
          ok: false,
          error: msg === "aborted" ? "stopped" : msg,
        }),
      });
    } catch (ackErr) {
      // ignore
    }
    if (msg !== "aborted") {
      state.message = msg;
      state.messageError = true;
    }
  } finally {
    state.animBusy = false;
  }
}

function render() {
  const labels = state.labels || {};
  const status = state.status || {};
  const run = status.run;
  const steps = status.steps || [];
  const canStart = !!status.can_start;
  const canStop = !!status.can_stop;
  const canReset = !!status.can_reset;
  const done = run ? Number(run.ProgressDone || 0) : 0;
  const total = run ? Number(run.ProgressTotal || 0) : 0;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const currentText =
    run && (run.CurrentStepNo != null || run.CurrentStepName)
      ? (run.CurrentStepNo != null ? String(run.CurrentStepNo) + " " : "") +
        String(run.CurrentStepName || "")
      : "-";
  const resultText =
    run && run.ErrorMessage
      ? String(run.ErrorMessage)
      : run
        ? status.status_label || run.Status
        : "-";
  const session = status.session || {};
  const sessionText = session.busy
    ? String(session.owner || "busy")
    : "free";

  let stepsHtml = "";
  steps.forEach(function (step) {
    stepsHtml +=
      '<tr class="' +
      stepStatusClass(step.Status) +
      '"><td>' +
      escapeHtml(step.StepNo) +
      "</td><td>" +
      escapeHtml(step.StepName) +
      "</td><td>" +
      escapeHtml(step.ActionType) +
      "</td><td>" +
      escapeHtml(step.TargetKey || "") +
      "</td><td>" +
      escapeHtml(stepStatusLabel(step.Status, labels)) +
      "</td><td>" +
      escapeHtml(step.ResultMessage || "") +
      "</td></tr>";
  });

  const viewerHost = document.getElementById("wfRunViewerHost");
  const savedViewer = viewerHost;

  root.innerHTML =
    '<div class="wf-run-header">' +
    '<div class="wf-run-title">' +
    escapeHtml(labels.wf_run_panel_title || "Virtual Run") +
    "</div>" +
    '<div class="wf-run-actions">' +
    '<button type="button" data-wf-action="start"' +
    (canStart ? "" : " disabled") +
    ">" +
    escapeHtml(labels.wf_run_btn_start || "Start") +
    "</button>" +
    '<button type="button" data-wf-action="stop"' +
    (canStop ? "" : " disabled") +
    ">" +
    escapeHtml(labels.wf_run_btn_stop || "Stop") +
    "</button>" +
    '<button type="button" data-wf-action="reset"' +
    (canReset ? "" : " disabled") +
    ">" +
    escapeHtml(labels.wf_run_btn_reset || "Reset") +
    "</button>" +
    "</div></div>" +
    '<div class="wf-run-meta">' +
    "<div><strong>" +
    escapeHtml(labels.wf_run_label_status || "Status") +
    ":</strong> " +
    escapeHtml(status.status_label || "-") +
    "</div>" +
    "<div><strong>" +
    escapeHtml(labels.wf_run_label_progress || "Progress") +
    ":</strong> " +
    escapeHtml(done + " / " + total) +
    "</div>" +
    "<div><strong>" +
    escapeHtml(labels.wf_run_label_current_step || "Current Step") +
    ":</strong> " +
    escapeHtml(currentText) +
    "</div>" +
    "<div><strong>" +
    escapeHtml(labels.wf_run_label_result || "Result") +
    ":</strong> " +
    escapeHtml(resultText) +
    "</div>" +
    "<div><strong>Session:</strong> " +
    escapeHtml(sessionText) +
    "</div>" +
    "</div>" +
    '<div class="wf-run-progress"><span style="width:' +
    pct +
    '%"></span></div>' +
    '<div id="wfRunViewerHost" class="wf-run-viewer-host"></div>' +
    (stepsHtml
      ? '<table class="wf-run-steps"><thead><tr><th>StepNo</th><th>Name</th><th>Action</th><th>Target</th><th>Status</th><th>Result</th></tr></thead><tbody>' +
        stepsHtml +
        "</tbody></table>"
      : "") +
    (state.message
      ? '<div class="wf-run-msg' +
        (state.messageError ? " is-error" : "") +
        '">' +
        escapeHtml(state.message) +
        "</div>"
      : "");

  if (savedViewer && state.viewer) {
    const host = document.getElementById("wfRunViewerHost");
    if (host && savedViewer.childNodes.length) {
      while (savedViewer.firstChild) {
        host.appendChild(savedViewer.firstChild);
      }
    }
  }

  root.querySelectorAll("[data-wf-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      handleAction(btn.getAttribute("data-wf-action"));
    });
  });
}

async function refreshStatus() {
  const runTxId =
    state.status && state.status.run ? state.status.run.TxId : null;
  const query =
    runTxId != null ? "?run_txid=" + encodeURIComponent(runTxId) : "";
  state.status = await api("/api/workflow-runs/status" + query);
  if (!state.labels && state.status.labels) {
    state.labels = state.status.labels;
  }
  render();
  if (state.status.animation) {
    handleAnimationCue(state.status);
  }
  if (state.status.is_running || state.status.animation) {
    schedulePoll(250);
  } else {
    schedulePoll(1500);
  }
}

function schedulePoll(ms) {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
  }
  state.pollTimer = setTimeout(function () {
    refreshStatus().catch(function (err) {
      state.message = String(err.message || err);
      state.messageError = true;
      render();
      schedulePoll(2000);
    });
  }, ms);
}

async function handleAction(action) {
  const labels = state.labels || {};
  try {
    if (action === "start") {
      const txid = findSelectedWorkflowTxId();
      state.selectedWorkflowTxId = txid;
      if (txid == null || !Number.isFinite(txid)) {
        state.message =
          labels.wf_run_msg_select_workflow || "Select a workflow";
        state.messageError = true;
        render();
        return;
      }
      await ensureDemoContext();
      if (state.demoRunner && state.demoRunner.abortLocal) {
        state.demoRunner.abortLocal();
      }
      state.lastAnimSeq = null;
      state.status = await api("/api/workflow-runs/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow_txid: txid }),
      });
      state.labels = state.status.labels || state.labels;
      state.message = labels.wf_run_msg_started || "Started";
      state.messageError = false;
    } else if (action === "stop") {
      if (state.demoRunner && state.demoRunner.abortLocal) {
        state.demoRunner.abortLocal();
      }
      state.status = await api("/api/workflow-runs/stop", { method: "POST" });
      state.message = labels.wf_run_msg_stopped || "Stopped";
      state.messageError = false;
    } else if (action === "reset") {
      if (state.demoRunner && state.demoRunner.abortLocal) {
        state.demoRunner.abortLocal();
      }
      state.status = await api("/api/workflow-runs/reset", { method: "POST" });
      state.lastAnimSeq = null;
      state.message = labels.wf_run_msg_reset || "Reset";
      state.messageError = false;
      await ensureDemoContext();
    }
    render();
    if (state.status && (state.status.is_running || state.status.animation)) {
      schedulePoll(200);
    }
  } catch (err) {
    state.message = String(err.message || err);
    state.messageError = true;
    render();
  }
}

const tableRoot = document.getElementById("tableUiRoot");
if (tableRoot) {
  const observer = new MutationObserver(function () {
    state.selectedWorkflowTxId = findSelectedWorkflowTxId();
  });
  observer.observe(tableRoot, { childList: true, subtree: true });
}

ensureDemoContext()
  .then(function () {
    return refreshStatus();
  })
  .catch(function (err) {
    state.message = String(err.message || err);
    state.messageError = true;
    render();
  });
