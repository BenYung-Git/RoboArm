(function () {
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const languageSelect = document.getElementById("languageSelect");
  const fontSelect = document.getElementById("fontSelect");
  const fontSizeSelect = document.getElementById("fontSizeSelect");
  const systemSettingTabs = document.getElementById("systemSettingTabs");
  const softwareVersionRoot = document.getElementById("softwareVersionRoot");
  const attachmentPathsRoot = document.getElementById("attachmentPathsRoot");

  function readPrefsFromControls() {
    return {
      language: languageSelect.value,
      font: fontSelect.value,
      font_size: Number(fontSizeSelect.value),
    };
  }

  async function savePrefsAndReload() {
    const body = readPrefsFromControls();
    const response = await fetch("/api/prefs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }
    window.location.reload();
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
  }

  languageSelect.addEventListener("change", savePrefsAndReload);
  fontSelect.addEventListener("change", savePrefsAndReload);
  fontSizeSelect.addEventListener("change", savePrefsAndReload);

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderInfoSection(section) {
    let rowsHtml = "";
    (section.rows || []).forEach(function (row) {
      rowsHtml +=
        '<div class="sw-row">' +
        '<div class="sw-label">' +
        escapeHtml(row.label) +
        "</div>" +
        '<div class="sw-value">' +
        escapeHtml(row.value) +
        "</div>" +
        "</div>";
    });
    return (
      '<section class="sw-section">' +
      "<h3>" +
      escapeHtml(section.title) +
      "</h3>" +
      '<div class="sw-grid">' +
      rowsHtml +
      "</div></section>"
    );
  }

  function renderSoftwareInfo(data) {
    if (!softwareVersionRoot) {
      return;
    }
    const details = data.details || {};
    const labels = data.labels || {};
    let detailsRows = "";
    (details.rows || []).forEach(function (row) {
      detailsRows +=
        '<div class="sw-row sw-row-full">' +
        '<div class="sw-label">' +
        escapeHtml(row.label) +
        "</div>" +
        '<div class="sw-value sw-value-path">' +
        escapeHtml(row.value) +
        "</div>" +
        "</div>";
    });
    softwareVersionRoot.innerHTML =
      renderInfoSection(data.system || { title: "", rows: [] }) +
      renderInfoSection(data.jaka || { title: "", rows: [] }) +
      '<section class="sw-section sw-details">' +
      '<button type="button" class="sw-details-toggle" id="swDetailsToggle" aria-expanded="false">' +
      escapeHtml(labels.toggle_expand || "") +
      "</button>" +
      '<div class="sw-details-body is-collapsed" id="swDetailsBody">' +
      '<h3 class="sw-details-title">' +
      escapeHtml(details.title || "") +
      "</h3>" +
      '<div class="sw-grid sw-grid-details">' +
      detailsRows +
      "</div></div></section>";

    const toggle = document.getElementById("swDetailsToggle");
    const body = document.getElementById("swDetailsBody");
    if (toggle && body) {
      toggle.addEventListener("click", function () {
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        const next = !expanded;
        toggle.setAttribute("aria-expanded", next ? "true" : "false");
        body.classList.toggle("is-collapsed", !next);
        toggle.textContent = next
          ? labels.toggle_collapse || ""
          : labels.toggle_expand || "";
      });
    }
  }

  async function loadSoftwareInfo() {
    if (!softwareVersionRoot) {
      return;
    }
    const response = await fetch("/api/system/software-info");
    if (!response.ok) {
      softwareVersionRoot.textContent = await response.text();
      return;
    }
    renderSoftwareInfo(await response.json());
  }

  let attachmentState = null;

  function osDisplayName(serverOs, labels) {
    if (serverOs === "Windows") {
      return labels.os_windows || "Windows";
    }
    if (serverOs === "Linux") {
      return labels.os_linux || "Linux";
    }
    return labels.os_unsupported || serverOs || "";
  }

  function setAttachmentMessage(text, kind) {
    const el = document.getElementById("apMessage");
    if (!el) {
      return;
    }
    el.textContent = text || "";
    el.classList.remove("is-error", "is-ok");
    if (kind === "error") {
      el.classList.add("is-error");
    } else if (kind === "ok") {
      el.classList.add("is-ok");
    }
  }

  function setPathStatus(text, kind) {
    const el = document.getElementById("apPathStatus");
    if (!el) {
      return;
    }
    el.textContent = text || "";
    el.classList.remove("is-error", "is-ok");
    if (kind === "error") {
      el.classList.add("is-error");
    } else if (kind === "ok") {
      el.classList.add("is-ok");
    }
  }

  function readAttachmentForm() {
    const windowsInput = document.getElementById("apWindowsPath");
    const linuxInput = document.getElementById("apLinuxPath");
    return {
      model_root_windows: windowsInput ? windowsInput.value : "",
      model_root_linux: linuxInput ? linuxInput.value : "",
    };
  }

  async function copyFieldValue(inputId) {
    const input = document.getElementById(inputId);
    const labels = (attachmentState && attachmentState.labels) || {};
    if (!input) {
      return;
    }
    const text = input.value || "";
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        setAttachmentMessage(labels.copy_ok || "", "ok");
        return;
      }
      throw new Error("clipboard unavailable");
    } catch (err) {
      input.focus();
      input.select();
      setAttachmentMessage(labels.copy_fail || "", "error");
    }
  }

  function closeBrowseModal() {
    const backdrop = document.getElementById("apBrowseBackdrop");
    if (backdrop && backdrop.parentNode) {
      backdrop.parentNode.removeChild(backdrop);
    }
  }

  async function loadBrowseListing(path) {
    const response = await fetch("/api/system/attachment-paths/browse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path || null }),
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }
    if (!response.ok) {
      const detail =
        data && data.detail
          ? typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail)
          : text;
      throw new Error(detail || "browse failed");
    }
    return data;
  }

  function renderBrowseModal(listing, targetField) {
    closeBrowseModal();
    const labels = (attachmentState && attachmentState.labels) || {};
    const backdrop = document.createElement("div");
    backdrop.className = "ap-modal-backdrop";
    backdrop.id = "apBrowseBackdrop";

    let dirsHtml = "";
    const dirs = listing.directories || [];
    if (dirs.length === 0) {
      dirsHtml =
        '<p class="ap-dir-empty">' +
        escapeHtml(labels.empty_dirs || "") +
        "</p>";
    } else {
      dirsHtml = '<div class="ap-dir-list">';
      dirs.forEach(function (item) {
        dirsHtml +=
          '<button type="button" class="ap-dir-item" data-path="' +
          escapeHtml(item.path) +
          '">' +
          escapeHtml(item.name) +
          "</button>";
      });
      dirsHtml += "</div>";
    }

    backdrop.innerHTML =
      '<div class="ap-modal" role="dialog" aria-modal="true">' +
      "<h3>" +
      escapeHtml(labels.browse_title || "") +
      "</h3>" +
      '<div class="ap-label">' +
      escapeHtml(labels.browse_current || "") +
      "</div>" +
      '<p class="ap-modal-current">' +
      escapeHtml(listing.current_path || "") +
      "</p>" +
      dirsHtml +
      '<div class="ap-modal-actions">' +
      '<button type="button" id="apBrowseUp"' +
      (listing.can_go_up ? "" : " disabled") +
      ">" +
      escapeHtml(labels.go_up || "") +
      "</button>" +
      '<button type="button" id="apBrowseCancel">' +
      escapeHtml(labels.cancel || "") +
      "</button>" +
      '<button type="button" class="ap-btn-primary" id="apBrowseSelect">' +
      escapeHtml(labels.select_folder || "") +
      "</button>" +
      "</div></div>";

    document.body.appendChild(backdrop);

    backdrop.addEventListener("click", function (event) {
      if (event.target === backdrop) {
        closeBrowseModal();
      }
    });
    backdrop.querySelector("#apBrowseCancel").addEventListener("click", closeBrowseModal);
    backdrop.querySelector("#apBrowseSelect").addEventListener("click", function () {
      const input = document.getElementById(
        targetField === "linux" ? "apLinuxPath" : "apWindowsPath"
      );
      if (input) {
        input.value = listing.current_path || "";
      }
      closeBrowseModal();
    });
    const upBtn = backdrop.querySelector("#apBrowseUp");
    if (upBtn && listing.can_go_up && listing.parent_path) {
      upBtn.addEventListener("click", function () {
        openBrowseModal(targetField, listing.parent_path);
      });
    }
    backdrop.querySelectorAll(".ap-dir-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openBrowseModal(targetField, btn.getAttribute("data-path"));
      });
    });
  }

  async function openBrowseModal(targetField, path) {
    const labels = (attachmentState && attachmentState.labels) || {};
    try {
      const listing = await loadBrowseListing(path || null);
      renderBrowseModal(listing, targetField);
    } catch (err) {
      setAttachmentMessage(String(err.message || err), "error");
      if (!attachmentState.browse_available) {
        setAttachmentMessage(labels.no_browse_roots || String(err), "error");
      }
    }
  }

  function bindAttachmentActions() {
    const browseWin = document.getElementById("apBrowseWindows");
    const browseLin = document.getElementById("apBrowseLinux");
    const copyWin = document.getElementById("apCopyWindows");
    const copyLin = document.getElementById("apCopyLinux");
    const checkBtn = document.getElementById("apCheck");
    const saveBtn = document.getElementById("apSave");
    const labels = (attachmentState && attachmentState.labels) || {};

    if (browseWin) {
      browseWin.addEventListener("click", function () {
        if (browseWin.disabled) {
          setAttachmentMessage(labels.browse_disabled || "", "error");
          return;
        }
        const start =
          (document.getElementById("apWindowsPath") || {}).value ||
          (attachmentState.browse_roots && attachmentState.browse_roots[0]) ||
          null;
        openBrowseModal("windows", start);
      });
    }
    if (browseLin) {
      browseLin.addEventListener("click", function () {
        if (browseLin.disabled) {
          setAttachmentMessage(labels.browse_disabled || "", "error");
          return;
        }
        const start =
          (document.getElementById("apLinuxPath") || {}).value ||
          (attachmentState.browse_roots && attachmentState.browse_roots[0]) ||
          null;
        openBrowseModal("linux", start);
      });
    }
    if (copyWin) {
      copyWin.addEventListener("click", function () {
        copyFieldValue("apWindowsPath");
      });
    }
    if (copyLin) {
      copyLin.addEventListener("click", function () {
        copyFieldValue("apLinuxPath");
      });
    }
    if (checkBtn) {
      checkBtn.addEventListener("click", function () {
        checkAttachmentPaths().catch(function (err) {
          setAttachmentMessage(String(err), "error");
        });
      });
    }
    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        saveAttachmentPaths().catch(function (err) {
          setAttachmentMessage(String(err), "error");
        });
      });
    }
  }

  function renderAttachmentPaths(data) {
    if (!attachmentPathsRoot) {
      return;
    }
    attachmentState = data;
    const labels = data.labels || {};
    const serverOs = data.server_os || "";
    const winActive = serverOs === "Windows";
    const linActive = serverOs === "Linux";
    const winBrowse =
      data.browse_enabled_field === "windows" && data.browse_available;
    const linBrowse =
      data.browse_enabled_field === "linux" && data.browse_available;
    const winPlaceholder = data.suggested_windows_path || "C:\\RoboModels";
    const effective =
      data.effective_path && String(data.effective_path).trim()
        ? data.effective_path
        : labels.path_status
          ? "—"
          : "—";

    attachmentPathsRoot.innerHTML =
      '<section class="ap-section">' +
      "<h3>" +
      escapeHtml(labels.section_model_library || "") +
      "</h3>" +
      '<div class="ap-meta">' +
      '<div class="ap-meta-item"><div class="ap-label">' +
      escapeHtml(labels.server_env || "") +
      '</div><div class="ap-value">' +
      escapeHtml(osDisplayName(serverOs, labels)) +
      "</div></div>" +
      '<div class="ap-meta-item"><div class="ap-label">' +
      escapeHtml(labels.selection_mode || "") +
      '</div><div class="ap-value">' +
      escapeHtml(labels.selection_mode_value || "") +
      "</div></div>" +
      '<div class="ap-meta-item"><div class="ap-label">' +
      escapeHtml(labels.effective_path || "") +
      '</div><div class="ap-value ap-value-path" id="apEffectivePath">' +
      escapeHtml(effective) +
      "</div></div>" +
      '<div class="ap-meta-item"><div class="ap-label">' +
      escapeHtml(labels.path_status || "") +
      '</div><div class="ap-value" id="apPathStatus">' +
      escapeHtml(data.validation_message || "") +
      "</div></div>" +
      "</div>" +
      '<div class="ap-field">' +
      '<div class="ap-field-head"><span class="ap-label">' +
      escapeHtml(labels.windows_path || "") +
      "</span>" +
      (winActive
        ? '<span class="ap-badge ap-badge-active">' +
          escapeHtml(labels.in_use || "") +
          "</span>"
        : "") +
      "</div>" +
      '<div class="ap-input-row">' +
      '<input type="text" id="apWindowsPath" spellcheck="false" placeholder="' +
      escapeHtml(winPlaceholder) +
      '" value="' +
      escapeHtml(data.windows_path || "") +
      '">' +
      '<button type="button" id="apBrowseWindows"' +
      (winBrowse ? "" : " disabled") +
      ' title="' +
      escapeHtml(winBrowse ? "" : labels.browse_disabled || "") +
      '">' +
      escapeHtml(labels.browse || "") +
      "</button>" +
      '<button type="button" id="apCopyWindows">' +
      escapeHtml(labels.copy || "") +
      "</button>" +
      "</div></div>" +
      '<div class="ap-field">' +
      '<div class="ap-field-head"><span class="ap-label">' +
      escapeHtml(labels.linux_path || "") +
      "</span>" +
      (linActive
        ? '<span class="ap-badge ap-badge-active">' +
          escapeHtml(labels.in_use || "") +
          "</span>"
        : "") +
      "</div>" +
      '<div class="ap-input-row">' +
      '<input type="text" id="apLinuxPath" spellcheck="false" value="' +
      escapeHtml(data.linux_path || "") +
      '">' +
      '<button type="button" id="apBrowseLinux"' +
      (linBrowse ? "" : " disabled") +
      ' title="' +
      escapeHtml(linBrowse ? "" : labels.browse_disabled || "") +
      '">' +
      escapeHtml(labels.browse || "") +
      "</button>" +
      '<button type="button" id="apCopyLinux">' +
      escapeHtml(labels.copy || "") +
      "</button>" +
      "</div></div>" +
      '<p class="ap-hint">' +
      escapeHtml(labels.hint_server_path || "") +
      "</p>" +
      '<div class="ap-actions">' +
      '<button type="button" id="apCheck">' +
      escapeHtml(labels.check || "") +
      "</button>" +
      '<button type="button" class="ap-btn-primary" id="apSave">' +
      escapeHtml(labels.save || "") +
      "</button>" +
      "</div>" +
      '<div class="ap-msg" id="apMessage"></div>' +
      "</section>";

    const statusKind =
      data.validation_status === "ok"
        ? "ok"
        : data.validation_status &&
            data.validation_status !== "not_checked" &&
            data.validation_status !== "format_ok_unverified"
          ? "error"
          : "";
    setPathStatus(data.validation_message || "", statusKind);
    bindAttachmentActions();
  }

  async function loadAttachmentPaths() {
    if (!attachmentPathsRoot) {
      return;
    }
    const response = await fetch("/api/system/attachment-paths");
    if (!response.ok) {
      attachmentPathsRoot.textContent = await response.text();
      return;
    }
    renderAttachmentPaths(await response.json());
  }

  async function checkAttachmentPaths() {
    const body = readAttachmentForm();
    const response = await fetch("/api/system/attachment-paths/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }
    if (!response.ok) {
      throw new Error(
        data && data.detail
          ? typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail)
          : text
      );
    }
    const current = data.current_validation || {};
    const kind = current.ok ? "ok" : "error";
    setPathStatus(data.validation_message || "", kind);
    const effectiveEl = document.getElementById("apEffectivePath");
    if (effectiveEl) {
      effectiveEl.textContent =
        data.effective_path && String(data.effective_path).trim()
          ? data.effective_path
          : "—";
    }
    setAttachmentMessage(data.validation_message || "", kind);
    return data;
  }

  async function saveAttachmentPaths() {
    const labels = (attachmentState && attachmentState.labels) || {};
    const body = readAttachmentForm();
    const response = await fetch("/api/system/attachment-paths", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }
    if (!response.ok) {
      throw new Error(
        data && data.detail
          ? typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail)
          : text
      );
    }
    const keepWindows = body.model_root_windows;
    const keepLinux = body.model_root_linux;
    renderAttachmentPaths(data);
    const winInput = document.getElementById("apWindowsPath");
    const linInput = document.getElementById("apLinuxPath");
    if (winInput) {
      winInput.value = data.windows_path != null ? data.windows_path : keepWindows;
    }
    if (linInput) {
      linInput.value = data.linux_path != null ? data.linux_path : keepLinux;
    }
    const kind = data.validation_status === "ok" ? "ok" : "";
    setPathStatus(data.validation_message || "", kind || "");
    setAttachmentMessage(labels.save_ok || "", "ok");
  }

  if (systemSettingTabs) {
    const panels = {
      ui_text: document.getElementById("systemPanelUiText"),
      software: document.getElementById("systemPanelSoftware"),
      attachment_paths: document.getElementById("systemPanelAttachmentPaths"),
    };
    let softwareLoaded = false;
    let attachmentLoaded = false;
    systemSettingTabs.querySelectorAll(".settings-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        const panelKey = tab.getAttribute("data-panel");
        systemSettingTabs.querySelectorAll(".settings-tab").forEach(function (item) {
          item.classList.remove("active");
        });
        tab.classList.add("active");
        Object.keys(panels).forEach(function (key) {
          if (!panels[key]) {
            return;
          }
          panels[key].classList.toggle("is-hidden", key !== panelKey);
        });
        if (panelKey === "software" && !softwareLoaded) {
          softwareLoaded = true;
          loadSoftwareInfo().catch(function (err) {
            softwareVersionRoot.textContent = String(err);
          });
        }
        if (panelKey === "attachment_paths" && !attachmentLoaded) {
          attachmentLoaded = true;
          loadAttachmentPaths().catch(function (err) {
            if (attachmentPathsRoot) {
              attachmentPathsRoot.textContent = String(err);
            }
          });
        }
      });
    });
  }
})();
