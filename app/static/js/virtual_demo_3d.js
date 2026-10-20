import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { sceneToRobot } from "/static/js/arm_kinematics.js";

/**
 * Model JSON uses Z-up robot coordinates (offsets / joint_axis in that frame).
 * A single root rotation maps robot Z -> scene Y. Joint axes are NOT remapped again.
 */

/**
 * Fixed joint-label panel layout (viewer-relative).
 * Edit here to reposition panels; motion/camera must not move these slots.
 */
const JOINT_LABEL_LAYOUT = {
  marginX: 10,
  marginY: 12,
  panelWidth: 112,
  panelGap: 8,
  /** Estimated panel height used for vertical stacking (px). */
  panelHeight: 58,
  /**
   * Slot per joint index 0..5 → J1..J6.
   * side: "left" | "right"; row: 0 top … downward.
   */
  slots: [
    { side: "left", row: 0 },
    { side: "left", row: 1 },
    { side: "left", row: 2 },
    { side: "right", row: 0 },
    { side: "right", row: 1 },
    { side: "right", row: 2 },
  ],
};

function jointLabelPanelRect(index, viewW, viewH) {
  const layout = JOINT_LABEL_LAYOUT;
  const slot = layout.slots[index] || { side: "left", row: index };
  const top =
    layout.marginY + slot.row * (layout.panelHeight + layout.panelGap);
  const left =
    slot.side === "right"
      ? Math.max(layout.marginX, viewW - layout.marginX - layout.panelWidth)
      : layout.marginX;
  return {
    left: left,
    top: top,
    width: layout.panelWidth,
    height: layout.panelHeight,
    side: slot.side,
  };
}

/** Anchor on panel edge facing the model (line must not cross label text). */
function jointLabelLineAnchor(rect) {
  if (rect.side === "right") {
    return { x: rect.left, y: rect.top + rect.height * 0.5 };
  }
  return { x: rect.left + rect.width, y: rect.top + rect.height * 0.5 };
}

function colorFromRole(model, role) {
  return new THREE.Color(model[role] || model.link_color || "#888888");
}

function makeMesh(segment, model) {
  const color = colorFromRole(model, segment.color_role || "link_color");
  const material = new THREE.MeshStandardMaterial({
    color,
    metalness: 0.18,
    roughness: 0.48,
  });
  let geometry;
  const axisHint = segment.mesh_axis || "z";
  if (segment.shape === "cylinder") {
    geometry = new THREE.CylinderGeometry(
      segment.radius,
      segment.radius_top != null ? segment.radius_top : segment.radius,
      segment.height,
      28
    );
    // CylinderGeometry is Y-aligned; rotate into requested local axis.
    if (axisHint === "z") {
      geometry.rotateX(Math.PI / 2);
    } else if (axisHint === "x") {
      geometry.rotateZ(-Math.PI / 2);
    }
    // axisHint === "y": leave as-is
  } else {
    const size = segment.size || [0.06, 0.06, 0.06];
    geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
  }
  return new THREE.Mesh(geometry, material);
}

function placeMesh(mesh, segment) {
  const place = segment.mesh_place || "along_z";
  if (place === "center") {
    return;
  }
  if (segment.shape === "cylinder") {
    const h = segment.height || 0;
    const axisHint = segment.mesh_axis || "z";
    if (axisHint === "z") {
      mesh.position.z = h / 2;
    } else if (axisHint === "y") {
      mesh.position.y = h / 2;
    } else if (axisHint === "x") {
      mesh.position.x = h / 2;
    }
    return;
  }
  if (segment.size) {
    mesh.position.z = segment.size[2] / 2;
  }
}

function fitCameraToObject(camera, controls, object, padding) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) {
    return;
  }
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);
  const maxDim = Math.max(size.x, size.y, size.z, 0.25);
  const fov = (camera.fov * Math.PI) / 180;
  let distance = (maxDim / (2 * Math.tan(fov / 2))) * (padding || 1.65);
  distance = Math.max(distance, 0.55);
  controls.target.copy(center);
  // Front-right elevated oblique; scene Y is up after root convert.
  camera.position.set(
    center.x + distance * 0.72,
    center.y + distance * 0.42,
    center.z + distance * 0.78
  );
  camera.near = Math.max(0.01, distance / 80);
  camera.far = Math.max(20, distance * 25);
  camera.updateProjectionMatrix();
  controls.update();
}

export function createArmViewer(container, model, initialJoints) {
  const width = container.clientWidth || 640;
  const height = container.clientHeight || 420;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe8eef4);

  const camera = new THREE.PerspectiveCamera(40, width / height, 0.01, 40);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.innerHTML = "";
  container.style.position = "relative";
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.25;
  controls.maxDistance = 8;

  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const key = new THREE.DirectionalLight(0xffffff, 0.95);
  key.position.set(1.5, 2.4, 1.2);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xdde7f2, 0.45);
  fill.position.set(-1.8, 1.2, -1.0);
  scene.add(fill);

  const platformRadius = Number(model.platform_radius);
  if (!Number.isFinite(platformRadius) || platformRadius <= 0) {
    throw new Error("viewer_model.platform_radius missing or invalid");
  }
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(platformRadius, 64),
    new THREE.MeshStandardMaterial({
      color: 0xc5d0db,
      roughness: 0.95,
      metalness: 0,
      transparent: true,
      opacity: 0.55,
    })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.002;
  scene.add(ground);

  // Single Z-up -> Y-up conversion for the whole arm.
  const armRoot = new THREE.Group();
  armRoot.rotation.x = -Math.PI / 2;
  scene.add(armRoot);

  const jointNodes = [];
  let parent = armRoot;

  (model.segments || []).forEach(function (segment) {
    const offset = segment.offset || [0, 0, 0];
    const pivot = new THREE.Group();
    pivot.position.set(offset[0], offset[1], offset[2]);
    parent.add(pivot);

    if (segment.joint_axis) {
      jointNodes.push({
        node: pivot,
        axis: new THREE.Vector3(
          segment.joint_axis[0],
          segment.joint_axis[1],
          segment.joint_axis[2]
        ).normalize(),
      });
    }

    const mesh = makeMesh(segment, model);
    placeMesh(mesh, segment);
    pivot.add(mesh);
    parent = pivot;
  });

  let disposed = false;
  let jointLabelsVisible = true;
  const pivotScratch = new THREE.Vector3();
  const projScratch = new THREE.Vector3();

  const labelLayer = document.createElement("div");
  labelLayer.className = "vd-joint-label-layer";
  container.appendChild(labelLayer);

  const labelSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  labelSvg.setAttribute("class", "vd-joint-label-lines");
  labelLayer.appendChild(labelSvg);

  const jointLabels = jointNodes.map(function (_item, index) {
    const el = document.createElement("div");
    el.className = "vd-joint-label";
    el.innerHTML =
      "<div class='vd-joint-label-name'>J" +
      (index + 1) +
      "</div>" +
      "<div class='vd-joint-label-xyz'>" +
      "<div>X: <span data-axis='x'>0.000</span> m</div>" +
      "<div>Y: <span data-axis='y'>0.000</span> m</div>" +
      "<div>Z: <span data-axis='z'>0.000</span> m</div>" +
      "</div>";
    labelLayer.appendChild(el);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("class", "vd-joint-label-line");
    labelSvg.appendChild(line);
    return {
      el: el,
      line: line,
      xEl: el.querySelector("[data-axis='x']"),
      yEl: el.querySelector("[data-axis='y']"),
      zEl: el.querySelector("[data-axis='z']"),
    };
  });

  function setJointsDeg(jointsDeg) {
    jointNodes.forEach(function (item, index) {
      const deg = Number((jointsDeg && jointsDeg[index]) || 0);
      const rad = (deg * Math.PI) / 180;
      item.node.quaternion.setFromAxisAngle(item.axis, rad);
    });
    armRoot.updateMatrixWorld(true);
    updateJointLabels();
  }

  function updateJointLabels() {
    if (disposed) {
      return;
    }
    const w = renderer.domElement.clientWidth || width;
    const h = renderer.domElement.clientHeight || height;
    labelSvg.setAttribute("viewBox", "0 0 " + w + " " + h);
    labelSvg.setAttribute("width", String(w));
    labelSvg.setAttribute("height", String(h));

    if (!jointLabelsVisible) {
      labelLayer.style.display = "none";
      return;
    }
    labelLayer.style.display = "block";
    armRoot.updateMatrixWorld(true);

    jointNodes.forEach(function (item, index) {
      const label = jointLabels[index];
      if (!label) {
        return;
      }
      // Fixed panel slot (viewer layout only; not driven by pose/camera).
      const rect = jointLabelPanelRect(index, w, h);
      label.el.style.display = "block";
      label.el.style.left = rect.left + "px";
      label.el.style.top = rect.top + "px";
      label.el.style.width = rect.width + "px";
      label.el.style.transform = "none";

      // Pivot origin = joint axis center (not mesh center / not TCP).
      pivotScratch.set(0, 0, 0);
      item.node.localToWorld(pivotScratch);
      const robot = sceneToRobot([
        pivotScratch.x,
        pivotScratch.y,
        pivotScratch.z,
      ]);
      label.xEl.textContent = robot[0].toFixed(3);
      label.yEl.textContent = robot[1].toFixed(3);
      label.zEl.textContent = robot[2].toFixed(3);

      // Dynamic leader: panel edge fixed ↔ joint screen projection.
      projScratch.copy(pivotScratch).project(camera);
      const behind = projScratch.z < -1 || projScratch.z > 1;
      const jx = (projScratch.x * 0.5 + 0.5) * w;
      const jy = (-projScratch.y * 0.5 + 0.5) * h;
      const offscreen = jx < 0 || jx > w || jy < 0 || jy > h;
      if (behind || offscreen) {
        label.line.style.display = "none";
        return;
      }
      const anchor = jointLabelLineAnchor(rect);
      label.line.style.display = "block";
      label.line.setAttribute("x1", String(anchor.x));
      label.line.setAttribute("y1", String(anchor.y));
      label.line.setAttribute("x2", String(jx));
      label.line.setAttribute("y2", String(jy));
    });
  }

  function setJointLabelsVisible(visible) {
    jointLabelsVisible = !!visible;
    updateJointLabels();
  }

  function getJointPivotRobotXYZ() {
    armRoot.updateMatrixWorld(true);
    return jointNodes.map(function (item) {
      pivotScratch.set(0, 0, 0);
      item.node.localToWorld(pivotScratch);
      const robot = sceneToRobot([
        pivotScratch.x,
        pivotScratch.y,
        pivotScratch.z,
      ]);
      return {
        x: Number(robot[0].toFixed(6)),
        y: Number(robot[1].toFixed(6)),
        z: Number(robot[2].toFixed(6)),
      };
    });
  }

  function fitView(jointsDeg) {
    setJointsDeg(jointsDeg || [0, 0, 0, 0, 0, 0]);
    armRoot.updateMatrixWorld(true);
    fitCameraToObject(camera, controls, armRoot, 1.7);
    updateJointLabels();
  }

  const startJoints = initialJoints || [0, 0, 0, 0, 0, 0];
  fitView(startJoints);

  function renderFrame() {
    if (disposed) {
      return;
    }
    controls.update();
    updateJointLabels();
    renderer.render(scene, camera);
    requestAnimationFrame(renderFrame);
  }
  renderFrame();

  function resize() {
    const w = container.clientWidth || width;
    const h = container.clientHeight || height;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    updateJointLabels();
  }
  window.addEventListener("resize", resize);

  function setViewPreset(preset) {
    const target = controls.target.clone();
    const dist = Math.max(camera.position.distanceTo(target), 0.6);
    if (preset === "front") {
      camera.position.set(target.x, target.y + dist * 0.12, target.z + dist);
    } else if (preset === "side") {
      camera.position.set(target.x + dist, target.y + dist * 0.12, target.z);
    } else {
      camera.position.set(
        target.x + dist * 0.72,
        target.y + dist * 0.42,
        target.z + dist * 0.78
      );
    }
    controls.update();
  }

  function sampleTipWorld(localOffset) {
    let tip = null;
    armRoot.traverse(function (obj) {
      if (obj.isMesh) {
        tip = obj;
      }
    });
    const v = new THREE.Vector3();
    if (tip) {
      if (localOffset) {
        v.set(localOffset[0], localOffset[1], localOffset[2]);
        tip.localToWorld(v);
      } else {
        tip.getWorldPosition(v);
      }
    }
    return { x: v.x, y: v.y, z: v.z };
  }

  function jointLocalAngleDeg(index) {
    const item = jointNodes[index];
    if (!item) {
      return null;
    }
    const q = item.node.quaternion;
    const angle = 2 * Math.acos(Math.min(1, Math.max(-1, q.w))) * (180 / Math.PI);
    return Number(angle.toFixed(3));
  }

  let flangeNode = parent;
  let carryRoot = null;
  let objectMesh = null;
  let fingerL = null;
  let fingerR = null;
  let carryDemo = null;
  let objectPose = null;
  let gapM = 0.095;
  let grasped = false;

  function clearCarry() {
    if (carryRoot) {
      armRoot.remove(carryRoot);
      carryRoot = null;
    }
    if (fingerL) {
      flangeNode.remove(fingerL);
      fingerL = null;
    }
    if (fingerR) {
      flangeNode.remove(fingerR);
      fingerR = null;
    }
    objectMesh = null;
    carryDemo = null;
    grasped = false;
  }

  function makeZCylinder(radius, height, color) {
    const geo = new THREE.CylinderGeometry(radius, radius, height, 32);
    geo.rotateX(Math.PI / 2);
    return new THREE.Mesh(
      geo,
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.85 })
    );
  }

  function setCarryDemo(demo, pose, gap) {
    clearCarry();
    if (!demo) {
      return;
    }
    carryDemo = demo;
    objectPose = pose;
    gapM = gap != null ? gap : demo.gripper.gap_fully_open_m;
    carryRoot = new THREE.Group();
    armRoot.add(carryRoot);

    const tables = [];
    if (demo.pick_table && demo.place_table) {
      tables.push(demo.pick_table, demo.place_table);
    } else if (demo.table) {
      tables.push(demo.table);
    }
    tables.forEach(function (table) {
      const topZ = table.top_z_m;
      const thick = table.thickness_m;
      const tableMesh = makeZCylinder(
        table.radius_m,
        thick,
        table.color || "#8b98a8"
      );
      tableMesh.position.set(
        table.center_xy_m[0],
        table.center_xy_m[1],
        topZ - thick / 2
      );
      carryRoot.add(tableMesh);

      const legH = Math.max(0.01, topZ - thick);
      (table.legs || []).forEach(function (leg) {
        const legMesh = makeZCylinder(leg.radius_m, legH, "#6b7684");
        legMesh.position.set(
          table.center_xy_m[0] + leg.offset_xy_m[0],
          table.center_xy_m[1] + leg.offset_xy_m[1],
          legH / 2
        );
        carryRoot.add(legMesh);
      });
    });

    const obj = demo.object;
    objectMesh = makeZCylinder(
      obj.radius_m,
      obj.height_m,
      obj.color || "#c45c26"
    );
    carryRoot.add(objectMesh);

    const g = demo.gripper;
    const fingerMat = new THREE.MeshStandardMaterial({
      color: "#d9e2ec",
      metalness: 0.25,
      roughness: 0.4,
    });
    const fGeo = new THREE.BoxGeometry(
      g.finger_thickness_m,
      g.finger_height_m,
      g.finger_length_m
    );
    fingerL = new THREE.Mesh(fGeo, fingerMat);
    fingerR = new THREE.Mesh(fGeo, fingerMat);
    flangeNode.add(fingerL);
    flangeNode.add(fingerR);
    updateCarryVisuals();
  }

  function updateCarryVisuals() {
    if (!carryDemo || !objectMesh) {
      return;
    }
    const pose = objectPose || {
      center_xyz_m: [
        carryDemo.object.center_xy_m[0],
        carryDemo.object.center_xy_m[1],
        carryDemo.derived.object_center_z_m,
      ],
      axis_world: [0, 0, 1],
    };
    objectMesh.position.set(
      pose.center_xyz_m[0],
      pose.center_xyz_m[1],
      pose.center_xyz_m[2]
    );
    const g = carryDemo.gripper;
    const half = gapM / 2 + g.finger_thickness_m / 2;
    const zPad = g.finger_pad_center_z_tcp_m;
    // closing along TCP +X; fingers at ±half on X, pad center on Z
    if (fingerL && fingerR) {
      fingerL.position.set(-half, 0, zPad);
      fingerR.position.set(half, 0, zPad);
    }
  }

  function setObjectPose(pose) {
    objectPose = pose;
    updateCarryVisuals();
  }

  function setGap(gap) {
    gapM = gap;
    updateCarryVisuals();
  }

  function getFlangeWorldPos() {
    flangeNode.updateWorldMatrix(true, false);
    const v = new THREE.Vector3();
    flangeNode.getWorldPosition(v);
    return { x: v.x, y: v.y, z: v.z };
  }

  function getTcpWorldPos(tcpOffset) {
    flangeNode.updateWorldMatrix(true, false);
    const v = new THREE.Vector3(tcpOffset[0], tcpOffset[1], tcpOffset[2]);
    flangeNode.localToWorld(v);
    return { x: v.x, y: v.y, z: v.z };
  }

  return {
    setJointsDeg: function (jointsDeg) {
      setJointsDeg(jointsDeg);
      updateCarryVisuals();
    },
    fitView,
    setViewPreset,
    sampleTipWorld,
    jointLocalAngleDeg,
    jointCount: jointNodes.length,
    setCarryDemo,
    clearCarry,
    setObjectPose,
    setGap,
    getObjectPose: function () {
      return objectPose;
    },
    getGap: function () {
      return gapM;
    },
    setGrasped: function (v) {
      grasped = !!v;
    },
    isGrasped: function () {
      return grasped;
    },
    getFlangeWorldPos,
    getTcpWorldPos,
    setJointLabelsVisible,
    getJointLabelsVisible: function () {
      return jointLabelsVisible;
    },
    getJointPivotRobotXYZ,
    updateJointLabels,
    armRoot,
    dispose: function () {
      disposed = true;
      clearCarry();
      window.removeEventListener("resize", resize);
      controls.dispose();
      renderer.dispose();
      container.innerHTML = "";
    },
  };
}
