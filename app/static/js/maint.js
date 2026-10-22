(function () {
  const root = document.getElementById("maintRoot");
  if (!root) {
    return;
  }

  const state = {
    tableKey: root.getAttribute("data-table-key"),
    meta: null,
    mode: "view",
    selectedTxId: null,
    editTxId: null,
    copySource: null,
    search: "",
    flagFilters: {},
    rows: [],
    dirty: false,
    saving: false,
    baselinePayload: null,
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function api(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let detail = await response.text();
      try {
        const parsed = JSON.parse(detail);
        if (parsed && parsed.detail) {
          detail = typeof parsed.detail === "string"
            ? parsed.detail
            : JSON.stringify(parsed.detail);
        }
      } catch (_error) {
        // keep raw text
      }
      throw new Error(detail);
    }
    return response.json();
  }

  function columnByField(field) {
    return state.meta.columns.find(function (column) {
      return column.field === field;
    });
  }

  function isFormMode() {
    return state.mode === "add" || state.mode === "edit" || state.mode === "copy";
  }

  function selectedRow() {
    if (state.selectedTxId == null) {
      return null;
    }
    return (
      state.rows.find(function (row) {
        return Number(row.TxId) === Number(state.selectedTxId);
      }) || null
    );
  }

  function actionButton(id, icon, tip, enabled) {
    return (
      '<button type="button" class="maint-icon-btn' +
      (enabled ? "" : " is-disabled") +
      '" id="' +
      id +
      '" title="' +
      escapeHtml(tip) +
      '"' +
      (enabled ? "" : " disabled") +
      ">" +
      '<span class="maint-btn-icon" aria-hidden="true">' +
      escapeHtml(icon) +
      "</span>" +
      '<span class="maint-btn-label">' +
      escapeHtml(tip) +
      "</span>" +
      "</button>"
    );
  }

  function renderToolbar() {
    const labels = state.meta.labels;
    const flagFields = state.meta.flag_fields;
    let flagHtml = "";
    flagFields.forEach(function (field) {
      const column = columnByField(field);
      const selected = state.flagFilters[field] || "";
      flagHtml +=
        '<label class="maint-filter">' +
        "<span>" +
        escapeHtml(column.label) +
        "</span>" +
        '<select data-flag-field="' +
        escapeHtml(field) +
        '">' +
        '<option value="">' +
        escapeHtml(labels.filter_all) +
        "</option>" +
        '<option value="0"' +
        (selected === "0" ? " selected" : "") +
        ">" +
        escapeHtml(labels.status_enabled) +
        "</option>" +
        '<option value="1"' +
        (selected === "1" ? " selected" : "") +
        ">" +
        escapeHtml(labels.status_disabled) +
        "</option>" +
        "</select>" +
        "</label>";
    });

    const hasSelection = selectedRow() != null;
    const row = selectedRow();
    const toggleTip =
      row && row.isDisable ? labels.tip_enable : labels.tip_disable;
    const toggleIcon =
      row && row.isDisable ? labels.icon_enable : labels.icon_disable;

    let iconsHtml = "";
    if (isFormMode()) {
      iconsHtml =
        actionButton("maintSaveBtn", labels.icon_save, labels.tip_save, !state.saving) +
        actionButton("maintCancelBtn", labels.icon_cancel, labels.tip_cancel, true);
    } else {
      iconsHtml =
        actionButton("maintAddBtn", labels.icon_add, labels.tip_add, true) +
        actionButton("maintEditBtn", labels.icon_edit, labels.tip_edit, hasSelection) +
        actionButton(
          "maintToggleBtn",
          toggleIcon,
          toggleTip,
          hasSelection
        ) +
        actionButton("maintCopyBtn", labels.icon_copy, labels.tip_copy, hasSelection);
    }

    return (
      '<div class="maint-toolbar">' +
      '<label class="maint-search">' +
      "<span>" +
      escapeHtml(labels.search) +
      "</span>" +
      '<input type="text" id="maintSearchInput" value="' +
      escapeHtml(state.search) +
      '">' +
      "</label>" +
      flagHtml +
      '<div class="maint-icons">' +
      iconsHtml +
      "</div>" +
      '<div class="maint-message" id="maintMessage"></div>' +
      "</div>"
    );
  }

  function displayValue(row, field) {
    if (field === "isDisable") {
      return row.isDisable_label;
    }
    const labeled = row[field + "_label"];
    if (labeled != null && labeled !== "") {
      return labeled;
    }
    const value = row[field];
    return value == null ? "" : value;
  }

  function statusClass(row) {
    return row.isDisable ? "maint-status is-disabled" : "maint-status is-enabled";
  }

  function renderFieldControl(column, value, readonly) {
    const field = column.field;
    const requiredMark =
      column.required && !readonly && !column.auto_gen && !column.is_flag
        ? '<span class="maint-required">*</span>'
        : "";
    let control = "";
    if (readonly || column.auto_gen || column.is_flag) {
      let shown = value == null ? "" : value;
      if (column.is_flag) {
        shown = value ? state.meta.labels.status_disabled : state.meta.labels.status_enabled;
      }
      if (column.options) {
        const option = column.options.find(function (item) {
          return item.value === value;
        });
        if (option) {
          shown = option.label;
        }
      }
      control =
        '<div class="maint-readonly' +
        (column.is_flag
          ? value
            ? " is-disabled"
            : " is-enabled"
          : "") +
        '">' +
        escapeHtml(shown) +
        "</div>";
    } else if (column.field_type === "select") {
      let optionsHtml = '<option value=""></option>';
      (column.options || []).forEach(function (option) {
        optionsHtml +=
          '<option value="' +
          escapeHtml(option.value) +
          '"' +
          (String(value) === String(option.value) ? " selected" : "") +
          ">" +
          escapeHtml(option.label) +
          "</option>";
      });
      control =
        '<select data-field="' +
        escapeHtml(field) +
        '" id="maintField_' +
        escapeHtml(field) +
        '">' +
        optionsHtml +
        "</select>";
    } else {
      const inputType = column.field_type === "number" ? "number" : "text";
      control =
        '<input type="' +
        inputType +
        '" data-field="' +
        escapeHtml(field) +
        '" id="maintField_' +
        escapeHtml(field) +
        '" value="' +
        escapeHtml(value == null ? "" : value) +
        '">';
    }
    return (
      '<label class="maint-form-field">' +
      "<span>" +
      escapeHtml(column.label) +
      requiredMark +
      "</span>" +
      control +
      "</label>"
    );
  }

  function formTitle() {
    const labels = state.meta.labels;
    if (state.mode === "add") {
      return labels.form_add;
    }
    if (state.mode === "edit") {
      return labels.form_edit;
    }
    if (state.mode === "copy") {
      return labels.form_copy;
    }
    return labels.form_view;
  }

  function renderDetailOrForm() {
    const labels = state.meta.labels;
    if (state.mode === "view" && selectedRow() == null) {
      return "";
    }

    let source = {};
    if (state.mode === "view") {
      source = selectedRow() || {};
    } else if (state.mode === "edit") {
      source = selectedRow() || {};
    } else if (state.mode === "copy") {
      source = state.copySource || {};
    }

    const readonly = state.mode === "view";
    let fieldsHtml = "";
    state.meta.columns.forEach(function (column) {
      if (column.auto_gen && state.mode !== "view" && state.mode !== "edit") {
        return;
      }
      if (column.auto_gen && state.mode === "add") {
        return;
      }
      if (column.auto_gen && state.mode === "copy") {
        return;
      }
      if (column.is_flag && (state.mode === "add" || state.mode === "copy")) {
        return;
      }
      let value = source[column.field];
      if (column.is_flag && state.mode === "view") {
        value = source.isDisable;
      }
      if (state.mode === "add") {
        value = "";
      }
      if (state.mode === "copy" && column.field === "TxId") {
        return;
      }
      fieldsHtml += renderFieldControl(column, value, readonly);
    });

    return (
      '<div class="maint-form' +
      (readonly ? " is-view" : "") +
      '">' +
      "<h3>" +
      escapeHtml(formTitle()) +
      "</h3>" +
      '<div class="maint-form-grid">' +
      fieldsHtml +
      "</div>" +
      "</div>"
    );
  }

  function renderTable(rows) {
    const labels = state.meta.labels;
    const displayFields = state.meta.display_fields;
    let head = "<tr>";
    displayFields.forEach(function (field) {
      const column = columnByField(field);
      head += "<th>" + escapeHtml(column.label) + "</th>";
    });
    head += "</tr>";

    let body = "";
    rows.forEach(function (row) {
      const selected =
        state.selectedTxId != null &&
        Number(row.TxId) === Number(state.selectedTxId);
      body +=
        '<tr class="maint-row' +
        (selected ? " is-selected" : "") +
        '" data-txid="' +
        escapeHtml(row.TxId) +
        '">';
      displayFields.forEach(function (field) {
        let value = displayValue(row, field);
        if (field === "isDisable") {
          body +=
            '<td><span class="' +
            statusClass(row) +
            '">' +
            escapeHtml(value) +
            "</span></td>";
        } else {
          body += "<td>" + escapeHtml(value) + "</td>";
        }
      });
      body += "</tr>";
    });

    return (
      '<div class="maint-table-wrap"><table class="maint-table"><thead>' +
      head +
      "</thead><tbody>" +
      body +
      "</tbody></table></div>"
    );
  }

  async function loadRows() {
    const params = new URLSearchParams();
    if (state.search) {
      params.set("search", state.search);
    }
    Object.keys(state.flagFilters).forEach(function (field) {
      const value = state.flagFilters[field];
      if (value !== "") {
        params.set(field, value);
      }
    });
    const query = params.toString();
    const url =
      "/api/maint/" +
      encodeURIComponent(state.tableKey) +
      "/rows" +
      (query ? "?" + query : "");
    const data = await api(url);
    state.rows = data.rows;
    return data.rows;
  }

  function readFormPayload() {
    const payload = {};
    state.meta.columns.forEach(function (column) {
      if (!column.editable) {
        return;
      }
      const input = document.getElementById("maintField_" + column.field);
      if (input) {
        payload[column.field] = input.value;
      }
    });
    return payload;
  }

  function captureBaseline() {
    if (!isFormMode()) {
      state.baselinePayload = null;
      state.dirty = false;
      return;
    }
    state.baselinePayload = JSON.stringify(readFormPayload());
    state.dirty = false;
  }

  function markDirtyIfNeeded() {
    if (!isFormMode() || state.baselinePayload == null) {
      return;
    }
    state.dirty = JSON.stringify(readFormPayload()) !== state.baselinePayload;
  }

  function setMessage(text, isError) {
    const box = document.getElementById("maintMessage");
    if (!box) {
      return;
    }
    box.textContent = text || "";
    box.className = "maint-message" + (isError ? " is-error" : text ? " is-ok" : "");
  }

  function validateRequired(payload) {
    const missing = [];
    state.meta.columns.forEach(function (column) {
      if (!column.editable || !column.required) {
        return;
      }
      const value = payload[column.field];
      if (value == null || String(value).trim() === "") {
        missing.push(column.label);
      }
    });
    return missing;
  }

  async function confirmLeaveIfDirty() {
    if (!state.dirty) {
      return true;
    }
    return window.confirm(state.meta.labels.confirm_discard);
  }

  async function enterView(selectedTxId) {
    state.mode = "view";
    state.editTxId = null;
    state.copySource = null;
    state.saving = false;
    if (selectedTxId !== undefined) {
      state.selectedTxId = selectedTxId;
    }
    state.dirty = false;
    state.baselinePayload = null;
    await render();
  }

  async function render() {
    const rows = await loadRows();
    if (
      state.selectedTxId != null &&
      !rows.some(function (row) {
        return Number(row.TxId) === Number(state.selectedTxId);
      })
    ) {
      // Keep selection if filtered out temporarily; still allow detail from cache.
    }
    root.innerHTML = renderToolbar() + renderDetailOrForm() + renderTable(rows);
    bindEvents();
    if (isFormMode()) {
      captureBaseline();
    }
  }

  function bindEvents() {
    const searchInput = document.getElementById("maintSearchInput");
    if (searchInput) {
      searchInput.addEventListener("change", async function () {
        if (!(await confirmLeaveIfDirty())) {
          searchInput.value = state.search;
          return;
        }
        state.search = searchInput.value.trim();
        await enterView(state.selectedTxId);
      });
      searchInput.addEventListener("keydown", async function (event) {
        if (event.key === "Enter") {
          if (!(await confirmLeaveIfDirty())) {
            searchInput.value = state.search;
            return;
          }
          state.search = searchInput.value.trim();
          await enterView(state.selectedTxId);
        }
      });
    }

    root.querySelectorAll("[data-flag-field]").forEach(function (select) {
      select.addEventListener("change", async function () {
        if (!(await confirmLeaveIfDirty())) {
          select.value = state.flagFilters[select.getAttribute("data-flag-field")] || "";
          return;
        }
        state.flagFilters[select.getAttribute("data-flag-field")] = select.value;
        await enterView(state.selectedTxId);
      });
    });

    root.querySelectorAll(".maint-form [data-field]").forEach(function (input) {
      input.addEventListener("input", markDirtyIfNeeded);
      input.addEventListener("change", markDirtyIfNeeded);
    });

    const addBtn = document.getElementById("maintAddBtn");
    if (addBtn) {
      addBtn.addEventListener("click", async function () {
        state.mode = "add";
        state.editTxId = null;
        state.copySource = null;
        await render();
      });
    }

    const editBtn = document.getElementById("maintEditBtn");
    if (editBtn) {
      editBtn.addEventListener("click", async function () {
        const row = selectedRow();
        if (!row) {
          setMessage(state.meta.labels.msg_select_row, true);
          return;
        }
        state.mode = "edit";
        state.editTxId = Number(row.TxId);
        state.selectedTxId = Number(row.TxId);
        state.copySource = null;
        await render();
      });
    }

    const copyBtn = document.getElementById("maintCopyBtn");
    if (copyBtn) {
      copyBtn.addEventListener("click", async function () {
        const row = selectedRow();
        if (!row) {
          setMessage(state.meta.labels.msg_select_row, true);
          return;
        }
        const fresh = await api(
          "/api/maint/" +
            encodeURIComponent(state.tableKey) +
            "/rows/" +
            encodeURIComponent(row.TxId)
        );
        state.mode = "copy";
        state.editTxId = null;
        state.copySource = fresh;
        await render();
      });
    }

    const toggleBtn = document.getElementById("maintToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", async function () {
        const row = selectedRow();
        if (!row) {
          setMessage(state.meta.labels.msg_select_row, true);
          return;
        }
        const message = row.isDisable
          ? state.meta.labels.confirm_enable
          : state.meta.labels.confirm_disable;
        if (!window.confirm(message)) {
          return;
        }
        try {
          const updated = await api(
            "/api/maint/" +
              encodeURIComponent(state.tableKey) +
              "/rows/" +
              encodeURIComponent(row.TxId) +
              "/toggle-disable",
            { method: "POST" }
          );
          state.selectedTxId = Number(updated.TxId);
          await enterView(state.selectedTxId);
        } catch (error) {
          setMessage(String(error.message || error), true);
        }
      });
    }

    const saveBtn = document.getElementById("maintSaveBtn");
    if (saveBtn) {
      saveBtn.addEventListener("click", async function () {
        if (state.saving) {
          return;
        }
        const payload = readFormPayload();
        const missing = validateRequired(payload);
        if (missing.length) {
          setMessage(state.meta.labels.msg_required + " " + missing.join(", "), true);
          return;
        }
        state.saving = true;
        saveBtn.disabled = true;
        try {
          let saved;
          if (state.mode === "add" || state.mode === "copy") {
            saved = await api(
              "/api/maint/" + encodeURIComponent(state.tableKey) + "/rows",
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ data: payload }),
              }
            );
          } else if (state.mode === "edit") {
            saved = await api(
              "/api/maint/" +
                encodeURIComponent(state.tableKey) +
                "/rows/" +
                encodeURIComponent(state.editTxId),
              {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ data: payload }),
              }
            );
          }
          state.saving = false;
          state.dirty = false;
          await enterView(saved ? Number(saved.TxId) : state.selectedTxId);
          setMessage(state.meta.labels.msg_save_ok, false);
        } catch (error) {
          state.saving = false;
          saveBtn.disabled = false;
          setMessage(String(error.message || error), true);
        }
      });
    }

    const cancelBtn = document.getElementById("maintCancelBtn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", async function () {
        if (!(await confirmLeaveIfDirty())) {
          return;
        }
        await enterView(state.selectedTxId);
      });
    }

    root.querySelectorAll(".maint-row").forEach(function (rowEl) {
      rowEl.addEventListener("click", async function () {
        const txid = Number(rowEl.getAttribute("data-txid"));
        if (isFormMode()) {
          if (!(await confirmLeaveIfDirty())) {
            return;
          }
          await enterView(txid);
          return;
        }
        state.selectedTxId = txid;
        await render();
      });
    });
  }

  document.querySelectorAll(".settings-tab").forEach(function (tab) {
    tab.addEventListener("click", async function () {
      if (!(await confirmLeaveIfDirty())) {
        return;
      }
      document.querySelectorAll(".settings-tab").forEach(function (item) {
        item.classList.remove("active");
      });
      tab.classList.add("active");
      state.tableKey = tab.getAttribute("data-table-key");
      root.setAttribute("data-table-key", state.tableKey);
      state.mode = "view";
      state.selectedTxId = null;
      state.editTxId = null;
      state.copySource = null;
      state.search = "";
      state.flagFilters = {};
      state.dirty = false;
      state.meta = await api(
        "/api/maint/" + encodeURIComponent(state.tableKey) + "/meta"
      );
      state.meta.flag_fields.forEach(function (field) {
        state.flagFilters[field] = "";
      });
      await render();
    });
  });

  window.addEventListener("beforeunload", function (event) {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  api("/api/maint/" + encodeURIComponent(state.tableKey) + "/meta")
    .then(function (meta) {
      state.meta = meta;
      state.meta.flag_fields.forEach(function (field) {
        state.flagFilters[field] = "";
      });
      return render();
    })
    .catch(function (error) {
      root.textContent = String(error);
    });
})();
