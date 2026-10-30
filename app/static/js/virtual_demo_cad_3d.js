import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

/**
 * Static CAD GLB viewer (meters, Y-up as authored).
 * No mm→m, no Z-up→Y-up, no recenter/rescale of the model.
 */
export function createCadStaticViewer(container, cadConfig) {
  const width = container.clientWidth || 640;
  const height = container.clientHeight || 420;
  const labels = cadConfig.labels || {};
  const parts = cadConfig.parts || [];

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe8eef4);

  const camera = new THREE.PerspectiveCamera(40, width / height, 0.01, 50);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  container.innerHTML = "";
  container.style.position = "relative";
  container.appendChild(renderer.domElement);

  const toolbar = document.createElement("div");
  toolbar.className = "cad-toolbar";
  toolbar.innerHTML =
    '<button type="button" class="cad-btn" data-cad-act="fit"></button>' +
    '<button type="button" class="cad-btn" data-cad-act="reset"></button>' +
    '<label class="cad-check"><input type="checkbox" data-cad-grid checked> <span data-cad-grid-label></span></label>' +
    '<label class="cad-check"><input type="checkbox" data-cad-axes checked> <span data-cad-axes-label></span></label>' +
    '<div class="cad-size" data-cad-size></div>';
  container.appendChild(toolbar);
  toolbar.querySelector('[data-cad-act="fit"]').textContent = labels.fit || "Fit";
  toolbar.querySelector('[data-cad-act="reset"]').textContent = labels.reset || "Reset";
  toolbar.querySelector("[data-cad-grid-label]").textContent = labels.grid || "Grid";
  toolbar.querySelector("[data-cad-axes-label]").textContent = labels.axes || "Axes";

  const partsBar = document.createElement("div");
  partsBar.className = "cad-parts";
  const partsTitle = document.createElement("div");
  partsTitle.className = "cad-parts-title";
  partsTitle.textContent = labels.parts || "Parts";
  partsBar.appendChild(partsTitle);
  parts.forEach(function (part) {
    const lab = document.createElement("label");
    lab.className = "cad-check";
    lab.innerHTML =
      '<input type="checkbox" checked data-cad-part="' +
      String(part.node_name).replace(/"/g, "") +
      '"> <span></span>';
    lab.querySelector("span").textContent =
      (part.label || part.product_name || part.node_name) +
      " (" +
      (part.product_name || "") +
      ")";
    partsBar.appendChild(lab);
  });
  // Generic attachment GLB may have no part metadata; keep Zu7 parts UI intact.
  if (parts.length) {
    container.appendChild(partsBar);
  }

  const statusEl = document.createElement("div");
  statusEl.className = "cad-status";
  statusEl.textContent = labels.loading || "Loading…";
  container.appendChild(statusEl);

  const disclaimer = document.createElement("div");
  disclaimer.className = "cad-banner";
  disclaimer.textContent = cadConfig.disclaimer || "";
  container.appendChild(disclaimer);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 0.05;
  controls.maxDistance = 20;

  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(1.2, 2.0, 1.0);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xdde7f2, 0.4);
  fill.position.set(-1.5, 1.0, -1.2);
  scene.add(fill);

  const grid = new THREE.GridHelper(2.0, 20, 0x7a8a9a, 0xb7c4d1);
  grid.position.y = 0;
  scene.add(grid);

  const axes = new THREE.AxesHelper(0.35);
  scene.add(axes);

  const modelRoot = new THREE.Group();
  // Keep authored GLB frame: meters, Y-up. Do not rotate/scale/recenter.
  scene.add(modelRoot);

  const partNodes = {};
  let disposed = false;
  let defaultCameraPos = new THREE.Vector3(1.2, 0.9, 1.4);
  let defaultTarget = new THREE.Vector3(0.3, 0, 0);
  let measuredSize = cadConfig.aabb_m || null;

  function formatSize(aabb) {
    if (!aabb) {
      return (labels.size || "Size") + ": —";
    }
    const dx = Number(aabb.dx);
    const dy = Number(aabb.dy);
    const dz = Number(aabb.dz);
    return (
      (labels.size || "Size") +
      ": " +
      dx.toFixed(3) +
      " × " +
      dy.toFixed(3) +
      " × " +
      dz.toFixed(3) +
      " m"
    );
  }

  toolbar.querySelector("[data-cad-size]").textContent = formatSize(measuredSize);

  function aabbToPayload(box, meta) {
    if (!box || box.isEmpty()) {
      return null;
    }
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    return Object.assign(
      {
        xmin: box.min.x,
        ymin: box.min.y,
        zmin: box.min.z,
        xmax: box.max.x,
        ymax: box.max.y,
        zmax: box.max.z,
        dx: size.x,
        dy: size.y,
        dz: size.z,
        cx: center.x,
        cy: center.y,
        cz: center.z,
        unit: "m",
        frame: "gltf_Yup",
      },
      meta || {}
    );
  }

  /**
   * Same basis as reconcile: only Mesh/SkinnedMesh POSITION vertices,
   * transformed by each mesh world matrix. Excludes Line/Points/helpers.
   */
  function meshVertexWorldAabb(root) {
    const box = new THREE.Box3();
    const v = new THREE.Vector3();
    let count = 0;
    root.updateWorldMatrix(true, true);
    root.traverse(function (obj) {
      if (!obj.isMesh && !obj.isSkinnedMesh) {
        return;
      }
      // Skip helper-like meshes if any ever land under root.
      if (obj.isLine || obj.isLineSegments || obj.isPoints || obj.isSprite) {
        return;
      }
      const geom = obj.geometry;
      if (!geom) {
        return;
      }
      const pos = geom.getAttribute("position");
      if (!pos) {
        return;
      }
      const matrix = obj.matrixWorld;
      for (let i = 0; i < pos.count; i += 1) {
        v.fromBufferAttribute(pos, i).applyMatrix4(matrix);
        box.expandByPoint(v);
        count += 1;
      }
    });
    return { box: box, vertex_count: count };
  }

  function naiveSetFromObjectAabb(root) {
    root.updateWorldMatrix(true, true);
    return new THREE.Box3().setFromObject(root);
  }

  function fitCameraToBox(box) {
    if (!box || box.isEmpty()) {
      return;
    }
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 0.01);
    const fitDist =
      (maxDim / (2 * Math.tan((Math.PI * camera.fov) / 360))) * 1.35;
    const dir = new THREE.Vector3(1, 0.7, 1).normalize();
    camera.position.copy(center).addScaledVector(dir, fitDist);
    camera.near = Math.max(0.001, fitDist / 200);
    camera.far = Math.max(50, fitDist * 20);
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }

  function resetCamera() {
    camera.position.copy(defaultCameraPos);
    controls.target.copy(defaultTarget);
    camera.near = 0.01;
    camera.far = 50;
    camera.updateProjectionMatrix();
    controls.update();
  }

  function measureLoaded(gltfRoot) {
    // Diagnostic: naive Box3.setFromObject on arm root only (no scene helpers).
    const naiveArm = aabbToPayload(naiveSetFromObjectAabb(modelRoot), {
      method: "THREE.Box3.setFromObject(modelRoot)",
      note: "Uses local geom AABB 8-corners; can inflate when meshes are rotated.",
    });
    // Diagnostic: whole scene (includes grid/axes) — must NOT be used for size.
    const naiveScene = aabbToPayload(naiveSetFromObjectAabb(scene), {
      method: "THREE.Box3.setFromObject(scene)",
      note: "Includes grid/axes/lights hierarchy; invalid for model size.",
    });
    // Authoritative: mesh vertices under GLB root only.
    const measureRoot = gltfRoot || modelRoot;
    const meshOnly = meshVertexWorldAabb(measureRoot);
    const accurate = aabbToPayload(meshOnly.box, {
      method: "mesh_POSITION_world_matrix",
      scope: "glb_scene_under_modelRoot_only",
      excluded: [
        "scene_grid",
        "axes_helper",
        "camera",
        "lights",
        "ui_labels",
        "non_mesh",
      ],
      vertex_count: meshOnly.vertex_count,
    });

    const accepted = cadConfig.aabb_m || null;
    const axisDiff = accurate && accepted
      ? {
          dx: accurate.dx - Number(accepted.dx),
          dy: accurate.dy - Number(accepted.dy),
          dz: accurate.dz - Number(accepted.dz),
          xmin: accurate.xmin - (accepted.xmin != null ? Number(accepted.xmin) : accurate.xmin),
          ymin: accurate.ymin - (accepted.ymin != null ? Number(accepted.ymin) : accurate.ymin),
          zmin: accurate.zmin - (accepted.zmin != null ? Number(accepted.zmin) : accurate.zmin),
          xmax: accurate.xmax - (accepted.xmax != null ? Number(accepted.xmax) : accurate.xmax),
          ymax: accurate.ymax - (accepted.ymax != null ? Number(accepted.ymax) : accurate.ymax),
          zmax: accurate.zmax - (accepted.zmax != null ? Number(accepted.zmax) : accurate.zmax),
        }
      : null;

    const report = {
      naive_setFromObject_modelRoot: naiveArm,
      naive_setFromObject_fullScene_includesHelpers: naiveScene,
      mesh_vertex_world_excl_helpers: accurate,
      accepted_glb_aabb_from_backend: accepted,
      diff_accurate_minus_accepted: axisDiff,
      root_cause:
        "UI previously used Box3.setFromObject on the arm root. That expands local geometry AABBs via 8 corners and inflates X/Z after node rotations (~11 mm). Grid/axes were already outside modelRoot; inflation was measurement method, not helper inclusion or GLB transform error.",
      reexport_required: false,
    };
    window.__vdCadMeasure = report;
    // eslint-disable-next-line no-console
    console.info("[cad-measure]", report);

    measuredSize = accurate;
    toolbar.querySelector("[data-cad-size]").textContent = formatSize(measuredSize);
    return meshOnly.box;
  }

  function applyPartVisibility() {
    partsBar.querySelectorAll("[data-cad-part]").forEach(function (input) {
      const name = input.getAttribute("data-cad-part");
      const node = partNodes[name];
      if (node) {
        node.visible = !!input.checked;
      }
    });
  }

  toolbar.addEventListener("click", function (event) {
    const btn = event.target.closest("[data-cad-act]");
    if (!btn) {
      return;
    }
    const act = btn.getAttribute("data-cad-act");
    if (act === "fit") {
      const meshOnly = meshVertexWorldAabb(modelRoot);
      fitCameraToBox(meshOnly.box);
    } else if (act === "reset") {
      resetCamera();
    }
  });
  toolbar.querySelector("[data-cad-grid]").addEventListener("change", function (e) {
    grid.visible = !!e.target.checked;
  });
  toolbar.querySelector("[data-cad-axes]").addEventListener("change", function (e) {
    axes.visible = !!e.target.checked;
  });
  partsBar.addEventListener("change", function (event) {
    if (event.target && event.target.hasAttribute("data-cad-part")) {
      applyPartVisibility();
    }
  });

  function onResize() {
    if (disposed) {
      return;
    }
    const w = container.clientWidth || 640;
    const h = container.clientHeight || 420;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  window.addEventListener("resize", onResize);

  let raf = 0;
  function tick() {
    if (disposed) {
      return;
    }
    raf = requestAnimationFrame(tick);
    controls.update();
    renderer.render(scene, camera);
  }
  tick();

  const loader = new GLTFLoader();
  if (!cadConfig.available) {
    statusEl.textContent = labels.unavailable || "CAD unavailable";
    statusEl.classList.add("is-error");
  } else {
    loader.load(
      cadConfig.glb_url,
      function (gltf) {
        if (disposed) {
          return;
        }
        const root = gltf.scene || gltf.scenes[0];
        modelRoot.add(root);
        root.traverse(function (obj) {
          if (obj.isMesh) {
            obj.castShadow = false;
            obj.receiveShadow = false;
            if (obj.material) {
              const mats = Array.isArray(obj.material)
                ? obj.material
                : [obj.material];
              mats.forEach(function (m) {
                if (m && m.side === undefined) {
                  m.side = THREE.FrontSide;
                }
              });
            }
          }
          if (obj.name && parts.some(function (p) { return p.node_name === obj.name; })) {
            partNodes[obj.name] = obj;
          }
        });
        // Also map by direct children of first group named Zu 7
        root.traverse(function (obj) {
          parts.forEach(function (p) {
            if (!partNodes[p.node_name] && obj.name === p.node_name) {
              partNodes[p.node_name] = obj;
            }
          });
        });
        applyPartVisibility();
        const fittedBox = measureLoaded(root);
        fitCameraToBox(fittedBox);
        defaultCameraPos = camera.position.clone();
        defaultTarget = controls.target.clone();
        statusEl.textContent = "";
        statusEl.classList.remove("is-error");
      },
      undefined,
      function (err) {
        statusEl.textContent =
          (labels.load_failed || "Load failed") +
          ": " +
          String(err && err.message ? err.message : err);
        statusEl.classList.add("is-error");
      }
    );
  }

  const api = {
    modelKey: cadConfig.model_key,
    isCadStatic: true,
    setJointsDeg: function () {},
    setCarryDemo: function () {},
    clearCarry: function () {},
    setGrasped: function () {},
    isGrasped: function () {
      return false;
    },
    setGap: function () {},
    getGap: function () {
      return 0;
    },
    getObjectPose: function () {
      return null;
    },
    setObjectPose: function () {},
    setJointLabelsVisible: function () {},
    dispose: function () {
      disposed = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      controls.dispose();
      renderer.dispose();
      container.innerHTML = "";
    },
  };
  return api;
}
