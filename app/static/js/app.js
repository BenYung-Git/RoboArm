(function () {
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const languageSelect = document.getElementById("languageSelect");
  const fontSelect = document.getElementById("fontSelect");
  const fontSizeSelect = document.getElementById("fontSizeSelect");
  const systemSettingTabs = document.getElementById("systemSettingTabs");
  const softwareVersionRoot = document.getElementById("softwareVersionRoot");

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

  if (systemSettingTabs) {
    const panels = {
      ui_text: document.getElementById("systemPanelUiText"),
      software: document.getElementById("systemPanelSoftware"),
    };
    let softwareLoaded = false;
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
      });
    });
  }
})();
