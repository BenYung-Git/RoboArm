(function () {
  const root = document.getElementById("maintRoot");
  if (!root) {
    return;
  }

  const state = {
    tableKey: root.getAttribute("data-table-key"),
    meta: null,
    mode: "list",
    editTxId: null,
    search: "",
    flagFilters: {},
  };

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

  function columnByField(field) {
    return state.meta.columns.find(function (column) {
      return column.field === field;
    });
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

    const saveCancelVisible = state.mode === "add" || state.mode === "edit";
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
      '<button type="button" class="maint-icon-btn" id="maintAddBtn" title="' +
      escapeHtml(labels.tip_add) +
      '">' +
      escapeHtml(labels.icon_add) +
      "</button>" +
      (saveCancelVisible
        ? '<button type="button" class="maint-icon-btn" id="maintSaveBtn" title="' +
          escapeHtml(labels.tip_save) +
          '">' +
          escapeHtml(labels.icon_save) +
          "</button>" +
          '<button type="button" class="maint-icon-btn" id="maintCancelBtn" title="' +
          escapeHtml(labels.tip_cancel) +
          '">' +
          escapeHtml(labels.icon_cancel) +
          "</button>"
        : "") +
      "</div>" +
      "</div>"
    );
  }

  function renderForm() {
    if (state.mode !== "add" && state.mode !== "edit") {
      return "";
    }
    const labels = state.meta.labels;
    const title = state.mode === "add" ? labels.form_add : labels.form_edit;
    let fieldsHtml = "";
    state.meta.columns.forEach(function (column) {
      if (column.auto_gen) {
        return;
      }
      if (column.is_flag) {
        return;
      }
      if (!column.editable && state.mode === "edit") {
        return;
      }
      if (!column.editable && state.mode === "add") {
        return;
      }
      fieldsHtml +=
        '<label class="maint-form-field">' +
        "<span>" +
        escapeHtml(column.label) +
        "</span>" +
        '<input type="text" data-field="' +
        escapeHtml(column.field) +
        '" id="maintField_' +
        escapeHtml(column.field) +
        '">' +
        "</label>";
    });
    return (
      '<div class="maint-form">' +
      "<h3>" +
      escapeHtml(title) +
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
    head += "<th>" + escapeHtml(labels.actions) + "</th></tr>";

    let body = "";
    rows.forEach(function (row) {
      body += "<tr>";
      displayFields.forEach(function (field) {
        let value = row[field];
        if (field === "isDisable") {
          value = row.isDisable_label;
        }
        body += "<td>" + escapeHtml(value) + "</td>";
      });
      const toggleTip = row.isDisable ? labels.tip_enable : labels.tip_disable;
      const toggleIcon = row.isDisable ? labels.icon_enable : labels.icon_disable;
      body +=
        '<td class="maint-row-actions">' +
        '<button type="button" class="maint-icon-btn maint-edit-btn" data-txid="' +
        escapeHtml(row.TxId) +
        '" title="' +
        escapeHtml(labels.tip_edit) +
        '">' +
        escapeHtml(labels.icon_edit) +
        "</button>" +
        '<button type="button" class="maint-icon-btn maint-toggle-btn" data-txid="' +
        escapeHtml(row.TxId) +
        '" title="' +
        escapeHtml(toggleTip) +
        '">' +
        escapeHtml(toggleIcon) +
        "</button>" +
        "</td></tr>";
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
    return data.rows;
  }

  async function fillEditForm(txid) {
    const row = await api(
      "/api/maint/" +
        encodeURIComponent(state.tableKey) +
        "/rows/" +
        encodeURIComponent(txid)
    );
    state.meta.columns.forEach(function (column) {
      if (!column.editable) {
        return;
      }
      const input = document.getElementById("maintField_" + column.field);
      if (input) {
        input.value = row[column.field];
      }
    });
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

  async function render() {
    const rows = await loadRows();
    root.innerHTML = renderToolbar() + renderForm() + renderTable(rows);
    bindEvents();
    if (state.mode === "edit" && state.editTxId !== null) {
      await fillEditForm(state.editTxId);
    }
  }

  function bindEvents() {
    const searchInput = document.getElementById("maintSearchInput");
    if (searchInput) {
      searchInput.addEventListener("change", async function () {
        state.search = searchInput.value.trim();
        await render();
      });
      searchInput.addEventListener("keydown", async function (event) {
        if (event.key === "Enter") {
          state.search = searchInput.value.trim();
          await render();
        }
      });
    }

    root.querySelectorAll("[data-flag-field]").forEach(function (select) {
      select.addEventListener("change", async function () {
        state.flagFilters[select.getAttribute("data-flag-field")] = select.value;
        await render();
      });
    });

    const addBtn = document.getElementById("maintAddBtn");
    if (addBtn) {
      addBtn.addEventListener("click", async function () {
        state.mode = "add";
        state.editTxId = null;
        await render();
      });
    }

    const saveBtn = document.getElementById("maintSaveBtn");
    if (saveBtn) {
      saveBtn.addEventListener("click", async function () {
        const payload = readFormPayload();
        if (state.mode === "add") {
          await api("/api/maint/" + encodeURIComponent(state.tableKey) + "/rows", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ data: payload }),
          });
        } else if (state.mode === "edit") {
          await api(
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
        state.mode = "list";
        state.editTxId = null;
        await render();
      });
    }

    const cancelBtn = document.getElementById("maintCancelBtn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", async function () {
        state.mode = "list";
        state.editTxId = null;
        await render();
      });
    }

    root.querySelectorAll(".maint-edit-btn").forEach(function (button) {
      button.addEventListener("click", async function () {
        state.mode = "edit";
        state.editTxId = Number(button.getAttribute("data-txid"));
        await render();
      });
    });

    root.querySelectorAll(".maint-toggle-btn").forEach(function (button) {
      button.addEventListener("click", async function () {
        const txid = button.getAttribute("data-txid");
        await api(
          "/api/maint/" +
            encodeURIComponent(state.tableKey) +
            "/rows/" +
            encodeURIComponent(txid) +
            "/toggle-disable",
          { method: "POST" }
        );
        await render();
      });
    });
  }

  document.querySelectorAll(".settings-tab").forEach(function (tab) {
    tab.addEventListener("click", async function () {
      document.querySelectorAll(".settings-tab").forEach(function (item) {
        item.classList.remove("active");
      });
      tab.classList.add("active");
      state.tableKey = tab.getAttribute("data-table-key");
      root.setAttribute("data-table-key", state.tableKey);
      state.mode = "list";
      state.editTxId = null;
      state.search = "";
      state.flagFilters = {};
      state.meta = await api(
        "/api/maint/" + encodeURIComponent(state.tableKey) + "/meta"
      );
      await render();
    });
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
