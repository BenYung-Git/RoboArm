(function () {
  const root = document.getElementById("tableUiRoot");
  if (!root) {
    return;
  }

  const state = {
    tableKey: root.getAttribute("data-table-key"),
    meta: null,
    tab: "list",
    rows: [],
    currentIndex: -1,
    selectedIds: {},
    search: "",
    flagFilter: "0",
    editMode: null,
    editSource: null,
    previewTxId: null,
    baseline: null,
    dirty: false,
    saving: false,
    pendingAction: null,
    message: "",
    messageError: false,
    layout: null,
    layoutDraft: null,
    layoutBaseline: null,
    layoutDirty: false,
    columnSort: {},
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
        if (parsed && parsed.detail != null) {
          detail =
            typeof parsed.detail === "string"
              ? parsed.detail
              : JSON.stringify(parsed.detail);
        }
      } catch (_error) {
        // keep raw
      }
      throw new Error(detail);
    }
    return response.json();
  }

  function labels() {
    return state.meta.labels;
  }

  function columnByField(field) {
    return state.meta.columns.find(function (column) {
      return column.field === field;
    });
  }

  function currentRow() {
    if (state.currentIndex < 0 || state.currentIndex >= state.rows.length) {
      return null;
    }
    return state.rows[state.currentIndex];
  }

  function filteredTotal() {
    return state.rows.length;
  }

  function positionText() {
    const total = filteredTotal();
    if (total === 0) {
      return "0 / 0";
    }
    const pos = state.currentIndex >= 0 ? state.currentIndex + 1 : 0;
    return pos + " / " + total;
  }

  function checkedCount() {
    let count = 0;
    state.rows.forEach(function (row) {
      if (state.selectedIds[row.TxId]) {
        count += 1;
      }
    });
    return count;
  }

  function allFilteredChecked() {
    if (state.rows.length === 0) {
      return false;
    }
    return state.rows.every(function (row) {
      return !!state.selectedIds[row.TxId];
    });
  }

  function displayValue(row, field) {
    if (field === "isDisable") {
      return row.isDisable_label;
    }
    if (row[field + "_label"] != null && row[field + "_label"] !== "") {
      return row[field + "_label"];
    }
    return row[field] == null ? "" : row[field];
  }

  function iconBtn(id, icon, tip, enabled, extraClass) {
    return (
      '<button type="button" class="tui-icon-btn' +
      (extraClass ? " " + extraClass : "") +
      '" id="' +
      id +
      '" title="' +
      escapeHtml(tip) +
      '"' +
      (enabled ? "" : " disabled") +
      ">" +
      escapeHtml(icon) +
      "</button>"
    );
  }

  function renderTabBar() {
    const L = labels();
    const tabs = [
      { key: "list", label: L.tab_list },
      { key: "edit", label: L.tab_edit },
      { key: "attachments", label: L.tab_attachments },
      { key: "messages", label: L.tab_messages },
      { key: "layout", label: L.tab_layout },
    ];
    let tabsHtml = "";
    tabs.forEach(function (tab) {
      tabsHtml +=
        '<button type="button" class="tui-tab' +
        (state.tab === tab.key ? " is-active" : "") +
        '" data-tui-tab="' +
        tab.key +
        '">' +
        escapeHtml(tab.label) +
        "</button>";
    });
    const canPrev = state.currentIndex > 0;
    const canNext =
      state.currentIndex >= 0 && state.currentIndex < state.rows.length - 1;
    const canFirst = canPrev;
    const canLast = canNext;
    return (
      '<div class="tui-tabbar">' +
      '<div class="tui-tabs">' +
      tabsHtml +
      "</div>" +
      '<div class="tui-nav">' +
      iconBtn("tuiNavFirst", L.icon_nav_first, L.tip_nav_first, canFirst) +
      iconBtn("tuiNavPrev", L.icon_nav_prev, L.tip_nav_prev, canPrev) +
      '<span class="tui-pos">' +
      escapeHtml(positionText()) +
      "</span>" +
      iconBtn("tuiNavNext", L.icon_nav_next, L.tip_nav_next, canNext) +
      iconBtn("tuiNavLast", L.icon_nav_last, L.tip_nav_last, canLast) +
      "</div>" +
      "</div>"
    );
  }

  function renderListToolbar() {
    const L = labels();
    const selectAllLabel = allFilteredChecked()
      ? L.label_deselect_all
      : L.label_select_all;
    return (
      '<div class="tui-toolbar">' +
      '<div class="tui-search">' +
      "<span>" +
      escapeHtml(L.search) +
      "</span>" +
      '<div class="tui-search-row">' +
      '<input type="text" id="tuiSearch" value="' +
      escapeHtml(state.search) +
      '">' +
      iconBtn("tuiSearchBtn", L.icon_search, L.tip_search, true, "tui-icon-search") +
      "</div></div>" +
      '<label class="tui-filter"><span>' +
      escapeHtml(columnByField("isDisable").label) +
      '</span><select id="tuiFlagFilter">' +
      '<option value=""' +
      (state.flagFilter === "" ? " selected" : "") +
      ">" +
      escapeHtml(L.filter_all) +
      "</option>" +
      '<option value="0"' +
      (state.flagFilter === "0" ? " selected" : "") +
      ">" +
      escapeHtml(L.status_enabled) +
      "</option>" +
      '<option value="1"' +
      (state.flagFilter === "1" ? " selected" : "") +
      ">" +
      escapeHtml(L.status_disabled) +
      "</option>" +
      "</select></label>" +
      '<div class="tui-toolbar-right">' +
      iconBtn("tuiLayoutBtn", L.icon_layout, L.tip_layout, true) +
      '<label class="tui-check-all">' +
      '<input type="checkbox" id="tuiSelectAll"' +
      (allFilteredChecked() ? " checked" : "") +
      ">" +
      "<span>" +
      escapeHtml(selectAllLabel) +
      "</span></label>" +
      '<span class="tui-check-count">' +
      escapeHtml(checkedCount() + " / " + filteredTotal()) +
      "</span>" +
      iconBtn("tuiAddBtn", L.icon_add, L.tip_add, true) +
      "</div></div>"
    );
  }

  function listFields() {
    if (state.layout && state.layout.list_fields) {
      return state.layout.list_fields.slice();
    }
    return state.meta.display_fields.slice();
  }

  function syncColumnSortFromLayout(layout) {
    const source = layout || state.layout;
    const next = {};
    source.columns.forEach(function (col) {
      const direction = col.sort_direction || "";
      if (direction === "asc" || direction === "desc") {
        next[col.field_key] = direction;
      } else {
        next[col.field_key] = "";
      }
    });
    state.columnSort = next;
  }

  function activeSortSpecs() {
    const specs = [];
    state.layout.columns.forEach(function (col) {
      const direction = state.columnSort[col.field_key] || "";
      if (direction === "asc" || direction === "desc") {
        specs.push({ field: col.field_key, dir: direction });
      }
    });
    return specs;
  }

  function sortMark(field) {
    const direction = state.columnSort[field] || "";
    if (direction === "asc") {
      return " ▲";
    }
    if (direction === "desc") {
      return " ▼";
    }
    return "";
  }

  function listZebraEnabled() {
    if (!state.layout) {
      throw new Error("Missing layout for zebra enabled");
    }
    return !!state.layout.zebra_enabled;
  }

  function listZebraCss() {
    if (!state.layout) {
      throw new Error("Missing layout for zebra color");
    }
    return state.layout.zebra_css_value;
  }

  function draftZebraCss() {
    if (!state.layoutDraft) {
      throw new Error("Missing layout draft for zebra color");
    }
    const key = state.layoutDraft.zebra_color;
    const opt = state.layoutDraft.zebra_color_options.find(function (item) {
      return item.color_key === key;
    });
    if (!opt) {
      throw new Error("Unknown zebra_color: " + key);
    }
    return opt.css_value;
  }

  function renderListTablePanel() {
    const L = labels();
    const fields = listFields();
    const zebraEnabled = listZebraEnabled();
    const zebraCss = listZebraCss();
    let head = "<tr><th></th>";
    fields.forEach(function (field) {
      head +=
        '<th class="tui-sortable" data-sort-field="' +
        escapeHtml(field) +
        '">' +
        escapeHtml(columnByField(field).label + sortMark(field)) +
        "</th>";
    });
    head += "<th>" + escapeHtml(L.actions) + "</th></tr>";

    let body = "";
    state.rows.forEach(function (row, index) {
      const isCurrent = index === state.currentIndex;
      body +=
        '<tr class="tui-row' +
        (isCurrent ? " is-current" : "") +
        '" data-index="' +
        index +
        '" data-txid="' +
        escapeHtml(row.TxId) +
        '">';
      body +=
        '<td><input type="checkbox" class="tui-row-check" data-txid="' +
        escapeHtml(row.TxId) +
        '"' +
        (state.selectedIds[row.TxId] ? " checked" : "") +
        "></td>";
      fields.forEach(function (field) {
        const value = displayValue(row, field);
        if (field === "isDisable") {
          body +=
            '<td><span class="tui-status ' +
            (row.isDisable ? "is-disabled" : "is-enabled") +
            '">' +
            escapeHtml(value) +
            "</span></td>";
        } else {
          body += "<td>" + escapeHtml(value) + "</td>";
        }
      });
      const toggleTip = row.isDisable ? L.tip_enable : L.tip_disable;
      const toggleIcon = row.isDisable ? L.icon_enable : L.icon_disable;
      body +=
        '<td class="tui-row-actions">' +
        '<button type="button" class="tui-icon-btn tui-toggle-btn" data-txid="' +
        escapeHtml(row.TxId) +
        '" title="' +
        escapeHtml(toggleTip) +
        '">' +
        escapeHtml(toggleIcon) +
        "</button>" +
        '<button type="button" class="tui-icon-btn tui-copy-btn" data-txid="' +
        escapeHtml(row.TxId) +
        '" title="' +
        escapeHtml(L.tip_copy) +
        '">' +
        escapeHtml(L.icon_copy) +
        "</button>" +
        "</td></tr>";
    });

    return (
      '<div class="tui-panel"><div class="tui-table-wrap"><table class="tui-table tui-data-table' +
      (zebraEnabled ? " tui-zebra" : "") +
      '" style="--zebra-color: ' +
      escapeHtml(zebraCss) +
      ';"><thead>' +
      head +
      "</thead><tbody>" +
      body +
      "</tbody></table></div></div>"
    );
  }

  function renderList() {
    return renderListToolbar() + renderListTablePanel();
  }

  function cloneLayout(layout) {
    return JSON.parse(JSON.stringify(layout));
  }

  function layoutPayloadFromDraft() {
    return {
      zebra_enabled: !!state.layoutDraft.zebra_enabled,
      zebra_color: state.layoutDraft.zebra_color,
      columns: state.layoutDraft.columns.map(function (col) {
        return {
          field_key: col.field_key,
          visible: !!col.visible,
          sort_direction: col.sort_direction,
        };
      }),
    };
  }

  function captureLayoutBaseline() {
    state.layoutBaseline = JSON.stringify(layoutPayloadFromDraft());
    state.layoutDirty = false;
  }

  function markLayoutDirty() {
    if (!state.layoutDraft || state.layoutBaseline == null) {
      return;
    }
    state.layoutDirty =
      JSON.stringify(layoutPayloadFromDraft()) !== state.layoutBaseline;
  }

  function visibleLayoutColumns() {
    return state.layoutDraft.columns
      .filter(function (col) {
        return col.visible;
      })
      .slice()
      .sort(function (a, b) {
        return a.display_order - b.display_order;
      });
  }

  function reorderLayoutColumns() {
    const draft = state.layoutDraft;
    const visible = [];
    const hidden = [];
    draft.columns.forEach(function (col) {
      if (col.visible) {
        visible.push(col);
      } else {
        hidden.push(col);
      }
    });
    visible.sort(function (a, b) {
      return a.display_order - b.display_order;
    });
    visible.forEach(function (col, index) {
      col.display_order = index + 1;
    });
    hidden.sort(function (a, b) {
      return String(a.field_label).localeCompare(String(b.field_label));
    });
    hidden.forEach(function (col) {
      col.display_order = 0;
    });
    draft.columns = visible.concat(hidden);
  }

  function renderLayout() {
    const L = labels();
    const draft = state.layoutDraft;
    if (!draft) {
      return renderPlaceholderTab(L.tab_layout);
    }
    let colorOptions = "";
    draft.zebra_color_options.forEach(function (opt) {
      colorOptions +=
        '<option value="' +
        escapeHtml(opt.color_key) +
        '" data-css="' +
        escapeHtml(opt.css_value) +
        '" style="background-color: ' +
        escapeHtml(opt.css_value) +
        '"' +
        (draft.zebra_color === opt.color_key ? " selected" : "") +
        ">" +
        escapeHtml(opt.label) +
        "</option>";
    });
    const selectedZebra = draft.zebra_color_options.find(function (opt) {
      return opt.color_key === draft.zebra_color;
    });
    if (!selectedZebra) {
      throw new Error("Unknown zebra_color: " + draft.zebra_color);
    }
    const zebraSelectStyle =
      ' style="background-color: ' + escapeHtml(selectedZebra.css_value) + '"';
    const visibleCols = visibleLayoutColumns();
    let rowsHtml = "";
    draft.columns.forEach(function (col) {
      const canMove = !!col.visible;
      let upDisabled = true;
      let downDisabled = true;
      if (canMove) {
        const pos = visibleCols.findIndex(function (item) {
          return item.field_key === col.field_key;
        });
        upDisabled = pos <= 0;
        downDisabled = pos < 0 || pos >= visibleCols.length - 1;
      }
      const sortValue = col.sort_direction || "";
      rowsHtml +=
        '<tr class="tui-layout-row' +
        (col.visible ? " is-visible" : "") +
        '" data-field="' +
        escapeHtml(col.field_key) +
        '"' +
        (canMove ? ' draggable="true"' : "") +
        ">" +
        '<td class="tui-drag-cell" title="' +
        escapeHtml(L.tip_drag) +
        '">' +
        (canMove ? escapeHtml(L.icon_drag) : "") +
        "</td>" +
        "<td>" +
        '<input type="checkbox" class="tui-layout-visible" data-field="' +
        escapeHtml(col.field_key) +
        '"' +
        (col.visible ? " checked" : "") +
        ">" +
        "</td>" +
        "<td>" +
        escapeHtml(col.field_label) +
        "</td>" +
        "<td>" +
        escapeHtml(col.field_desc) +
        "</td>" +
        "<td>" +
        '<select class="tui-layout-sort" data-field="' +
        escapeHtml(col.field_key) +
        '">' +
        '<option value=""' +
        (sortValue === "" ? " selected" : "") +
        ">" +
        escapeHtml(L.layout_sort_empty) +
        "</option>" +
        '<option value="asc"' +
        (sortValue === "asc" ? " selected" : "") +
        ">" +
        escapeHtml(L.layout_sort_asc) +
        "</option>" +
        '<option value="desc"' +
        (sortValue === "desc" ? " selected" : "") +
        ">" +
        escapeHtml(L.layout_sort_desc) +
        "</option>" +
        "</select></td>" +
        '<td class="tui-row-actions">' +
        '<button type="button" class="tui-icon-btn tui-layout-up" data-field="' +
        escapeHtml(col.field_key) +
        '" title="' +
        escapeHtml(L.tip_move_up) +
        '"' +
        (upDisabled ? " disabled" : "") +
        ">" +
        escapeHtml(L.icon_move_up) +
        "</button>" +
        '<button type="button" class="tui-icon-btn tui-layout-down" data-field="' +
        escapeHtml(col.field_key) +
        '" title="' +
        escapeHtml(L.tip_move_down) +
        '"' +
        (downDisabled ? " disabled" : "") +
        ">" +
        escapeHtml(L.icon_move_down) +
        "</button>" +
        "</td></tr>";
    });
    return (
      '<div class="tui-panel"><div class="tui-edit-wrap tui-layout-wrap">' +
      '<div class="tui-layout-row1">' +
      '<h3 class="tui-edit-title">' +
      escapeHtml(L.layout_title) +
      "</h3>" +
      '<div class="tui-layout-table-name">' +
      escapeHtml(L.layout_table_name) +
      " " +
      '<span class="tui-table-name-hl">' +
      escapeHtml(draft.table_name) +
      "</span></div></div>" +
      '<div class="tui-layout-row2">' +
      '<span class="tui-layout-zebra-label">' +
      escapeHtml(L.layout_zebra) +
      "</span>" +
      '<select id="tuiZebraColor"' +
      zebraSelectStyle +
      ">" +
      colorOptions +
      "</select>" +
      '<label class="tui-check-all"><input type="checkbox" id="tuiZebraEnabled"' +
      (draft.zebra_enabled ? " checked" : "") +
      "> <span>" +
      escapeHtml(L.layout_zebra_enabled) +
      "</span></label></div>" +
      '<div class="tui-layout-row3">' +
      "<h4>" +
      escapeHtml(L.layout_columns) +
      "</h4>" +
      '<div class="tui-edit-toolbar">' +
      iconBtn("tuiLayoutSaveBtn", L.icon_save, L.tip_save_layout, true) +
      iconBtn("tuiLayoutCancelBtn", L.icon_cancel, L.tip_cancel_layout, true) +
      "</div></div>" +
      '<div class="tui-table-wrap"><table class="tui-table tui-layout-table' +
      (draft.zebra_enabled ? " tui-zebra" : "") +
      '" style="--zebra-color: ' +
      escapeHtml(selectedZebra.css_value) +
      ';"><thead><tr>' +
      "<th></th><th>" +
      escapeHtml(L.layout_visible) +
      "</th><th>" +
      escapeHtml(L.layout_field_name) +
      "</th><th>" +
      escapeHtml(L.layout_field_desc) +
      "</th><th>" +
      escapeHtml(L.layout_sort_dir) +
      "</th><th>" +
      escapeHtml(L.actions) +
      "</th></tr></thead><tbody>" +
      rowsHtml +
      "</tbody></table></div></div></div>"
    );
  }

  function applyLayoutZebraPreview() {
    const table = root.querySelector(".tui-layout-table");
    if (!table) {
      return;
    }
    const enabled = !!state.layoutDraft.zebra_enabled;
    const cssValue = draftZebraCss();
    table.style.setProperty("--zebra-color", cssValue);
    if (enabled) {
      table.classList.add("tui-zebra");
    } else {
      table.classList.remove("tui-zebra");
    }
  }

  function isEditReadonly() {
    if (state.editMode === "edit" && state.editSource && state.editSource.isDisable) {
      return true;
    }
    return false;
  }

  function editTitle() {
    const L = labels();
    if (state.editMode === "add") {
      return L.mode_add;
    }
    if (state.editMode === "copy") {
      return L.mode_copy;
    }
    return L.mode_edit;
  }

  function fieldValueForForm(column) {
    if (column.field === "TxId") {
      if (state.editMode === "add" || state.editMode === "copy") {
        return state.previewTxId;
      }
      return state.editSource ? state.editSource.TxId : "";
    }
    if (!state.editSource) {
      return "";
    }
    return state.editSource[column.field];
  }

  function renderEditField(column) {
    const readonly =
      isEditReadonly() ||
      column.auto_gen ||
      column.is_flag ||
      (column.field === "TxId" &&
        (state.editMode === "add" || state.editMode === "copy"));
    const requiredMark =
      column.required && !readonly && !column.auto_gen && !column.is_flag
        ? '<span class="tui-required">*</span>'
        : "";
    let value = fieldValueForForm(column);
    let control = "";
    if (column.is_flag) {
      const text = value
        ? labels().status_disabled
        : labels().status_enabled;
      control =
        '<div class="tui-status ' +
        (value ? "is-disabled" : "is-enabled") +
        '">' +
        escapeHtml(text) +
        "</div>";
    } else if (column.field_type === "select" && !readonly) {
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
        escapeHtml(column.field) +
        '" id="tuiField_' +
        escapeHtml(column.field) +
        '">' +
        optionsHtml +
        "</select>";
    } else if (column.field_type === "select" && readonly) {
      let shown = value;
      (column.options || []).forEach(function (option) {
        if (option.value === value) {
          shown = option.label;
        }
      });
      control =
        '<input type="text" disabled value="' + escapeHtml(shown) + '">';
    } else {
      const inputType = column.field_type === "number" ? "number" : "text";
      control =
        '<input type="' +
        inputType +
        '" data-field="' +
        escapeHtml(column.field) +
        '" id="tuiField_' +
        escapeHtml(column.field) +
        '" value="' +
        escapeHtml(value == null ? "" : value) +
        '"' +
        (readonly ? " disabled" : "") +
        ">";
    }
    return (
      '<label class="tui-form-field"><span>' +
      escapeHtml(column.label) +
      requiredMark +
      "</span>" +
      control +
      "</label>"
    );
  }

  function renderEdit() {
    const L = labels();
    if (!state.editMode) {
      return (
        '<div class="tui-panel"><div class="tui-placeholder">' +
        escapeHtml(L.tab_edit) +
        "</div></div>"
      );
    }
    const readonly = isEditReadonly();
    let fieldsHtml = "";
    state.meta.columns.forEach(function (column) {
      fieldsHtml += renderEditField(column);
    });
    return (
      '<div class="tui-panel"><div class="tui-edit-wrap' +
      (readonly ? " is-readonly" : "") +
      '">' +
      '<div class="tui-edit-toolbar">' +
      iconBtn("tuiSaveBtn", L.icon_save, L.tip_save, !readonly && !state.saving) +
      iconBtn("tuiCancelBtn", L.icon_cancel, L.tip_cancel, !readonly) +
      "</div>" +
      (readonly
        ? '<div class="tui-disabled-banner">' +
          escapeHtml(L.disabled_banner) +
          "</div>"
        : "") +
      '<h3 class="tui-edit-title">' +
      escapeHtml(editTitle()) +
      "</h3>" +
      '<div class="tui-form-grid">' +
      fieldsHtml +
      "</div></div></div>"
    );
  }

  function renderPlaceholderTab(label) {
    return (
      '<div class="tui-panel"><div class="tui-placeholder">' +
      escapeHtml(label) +
      "</div></div>"
    );
  }

  function renderMessage() {
    if (!state.message) {
      return '<div class="tui-message" id="tuiMessage"></div>';
    }
    return (
      '<div class="tui-message' +
      (state.messageError ? " is-error" : " is-ok") +
      '" id="tuiMessage">' +
      escapeHtml(state.message) +
      "</div>"
    );
  }

  function setMessage(text, isError) {
    state.message = text || "";
    state.messageError = !!isError;
    const el = document.getElementById("tuiMessage");
    if (el) {
      el.textContent = state.message;
      el.className =
        "tui-message" +
        (state.message ? (state.messageError ? " is-error" : " is-ok") : "");
    }
  }

  async function loadLayout(forceReload) {
    if (state.layout && !forceReload) {
      return state.layout;
    }
    const layout = await api(
      "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/layout"
    );
    state.layout = layout;
    state.layoutDraft = cloneLayout(layout);
    captureLayoutBaseline();
    syncColumnSortFromLayout(layout);
    return layout;
  }

  async function loadRows() {
    const params = new URLSearchParams();
    if (state.search) {
      params.set("search", state.search);
    }
    if (state.flagFilter !== "") {
      params.set("isDisable", state.flagFilter);
    }
    params.set("sort", JSON.stringify(activeSortSpecs()));
    const query = params.toString();
    const data = await api(
      "/api/table-ui/" +
        encodeURIComponent(state.tableKey) +
        "/rows" +
        (query ? "?" + query : "")
    );
    if (data.layout) {
      state.layout = data.layout;
      if (!state.layoutDraft || state.tab !== "layout" || !state.layoutDirty) {
        state.layoutDraft = cloneLayout(data.layout);
        captureLayoutBaseline();
      }
    }
    const previousTxId =
      state.currentIndex >= 0 && state.rows[state.currentIndex]
        ? state.rows[state.currentIndex].TxId
        : null;
    state.rows = data.rows;
    if (state.rows.length === 0) {
      state.currentIndex = -1;
    } else if (previousTxId != null) {
      const found = state.rows.findIndex(function (row) {
        return Number(row.TxId) === Number(previousTxId);
      });
      state.currentIndex = found >= 0 ? found : 0;
    } else if (state.currentIndex < 0) {
      state.currentIndex = 0;
    } else if (state.currentIndex >= state.rows.length) {
      state.currentIndex = state.rows.length - 1;
    }
    Object.keys(state.selectedIds).forEach(function (txid) {
      const still = state.rows.some(function (row) {
        return String(row.TxId) === String(txid);
      });
      if (!still) {
        delete state.selectedIds[txid];
      }
    });
  }

  function readFormPayload() {
    const payload = {};
    state.meta.columns.forEach(function (column) {
      if (!column.editable) {
        return;
      }
      const input = document.getElementById("tuiField_" + column.field);
      if (input) {
        payload[column.field] = input.value;
      }
    });
    return payload;
  }

  function captureBaseline() {
    if (!state.editMode || isEditReadonly()) {
      state.baseline = null;
      state.dirty = false;
      return;
    }
    state.baseline = JSON.stringify(readFormPayload());
    state.dirty = false;
  }

  function markDirtyIfNeeded() {
    if (!state.editMode || isEditReadonly() || state.baseline == null) {
      return;
    }
    state.dirty = JSON.stringify(readFormPayload()) !== state.baseline;
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

  function showDirtyDialog() {
    return new Promise(function (resolve) {
      const L = labels();
      const backdrop = document.createElement("div");
      backdrop.className = "tui-modal-backdrop";
      backdrop.innerHTML =
        '<div class="tui-modal" role="dialog">' +
        "<p>" +
        escapeHtml(L.dirty_message) +
        "</p>" +
        '<div class="tui-modal-actions">' +
        '<button type="button" class="tui-modal-cancel">' +
        escapeHtml(L.dirty_cancel) +
        "</button>" +
        '<button type="button" class="tui-modal-save">' +
        escapeHtml(L.dirty_save) +
        "</button>" +
        "</div></div>";
      document.body.appendChild(backdrop);
      backdrop.querySelector(".tui-modal-save").addEventListener("click", function () {
        document.body.removeChild(backdrop);
        resolve("save");
      });
      backdrop
        .querySelector(".tui-modal-cancel")
        .addEventListener("click", function () {
          document.body.removeChild(backdrop);
          resolve("cancel");
        });
    });
  }

  async function reloadEditSource() {
    if (state.editMode === "edit" && state.editSource) {
      const row = await api(
        "/api/maint/" +
          encodeURIComponent(state.tableKey) +
          "/rows/" +
          encodeURIComponent(state.editSource.TxId)
      );
      state.editSource = row;
    } else if (state.editMode === "add") {
      state.editSource = emptySource();
      const next = await api(
        "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/next-txid"
      );
      state.previewTxId = next.next_txid;
    } else if (state.editMode === "copy") {
      const next = await api(
        "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/next-txid"
      );
      state.previewTxId = next.next_txid;
    }
  }

  function emptySource() {
    const source = {};
    state.meta.columns.forEach(function (column) {
      if (column.is_flag) {
        source[column.field] = false;
      } else {
        source[column.field] = "";
      }
    });
    return source;
  }

  async function handleDirtyBefore(action) {
    if (!state.dirty) {
      return true;
    }
    const choice = await showDirtyDialog();
    if (choice === "save") {
      const ok = await performSave();
      return ok;
    }
    await reloadEditSource();
    state.dirty = false;
    await render();
    return false;
  }

  async function performSave() {
    if (state.saving || isEditReadonly() || !state.editMode) {
      return false;
    }
    const payload = readFormPayload();
    const missing = validateRequired(payload);
    if (missing.length) {
      setMessage(labels().msg_required + " " + missing.join(", "), true);
      return false;
    }
    state.saving = true;
    try {
      let saved;
      if (state.editMode === "add" || state.editMode === "copy") {
        saved = await api(
          "/api/maint/" + encodeURIComponent(state.tableKey) + "/rows",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ data: payload }),
          }
        );
      } else {
        saved = await api(
          "/api/maint/" +
            encodeURIComponent(state.tableKey) +
            "/rows/" +
            encodeURIComponent(state.editSource.TxId),
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ data: payload }),
          }
        );
      }
      state.saving = false;
      state.dirty = false;
      state.editMode = "edit";
      state.editSource = saved;
      state.previewTxId = null;
      await loadRows();
      const idx = state.rows.findIndex(function (row) {
        return Number(row.TxId) === Number(saved.TxId);
      });
      if (idx >= 0) {
        state.currentIndex = idx;
      }
      await render();
      setMessage(labels().msg_save_ok, false);
      return true;
    } catch (error) {
      state.saving = false;
      setMessage(String(error.message || error), true);
      return false;
    }
  }

  async function enterEditFromCurrent() {
    const row = currentRow();
    if (!row) {
      return;
    }
    const fresh = await api(
      "/api/maint/" +
        encodeURIComponent(state.tableKey) +
        "/rows/" +
        encodeURIComponent(row.TxId)
    );
    state.editMode = "edit";
    state.editSource = fresh;
    state.previewTxId = null;
    state.tab = "edit";
    await render();
  }

  async function enterAdd() {
    const next = await api(
      "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/next-txid"
    );
    state.editMode = "add";
    state.editSource = emptySource();
    state.previewTxId = next.next_txid;
    state.tab = "edit";
    await render();
  }

  async function enterCopy(txid) {
    const fresh = await api(
      "/api/maint/" +
        encodeURIComponent(state.tableKey) +
        "/rows/" +
        encodeURIComponent(txid)
    );
    const next = await api(
      "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/next-txid"
    );
    state.editMode = "copy";
    state.editSource = fresh;
    state.previewTxId = next.next_txid;
    state.tab = "edit";
    await render();
  }

  async function moveToIndex(nextIndex) {
    if (state.rows.length === 0) {
      return;
    }
    if (nextIndex < 0 || nextIndex >= state.rows.length) {
      return;
    }
    if (nextIndex === state.currentIndex) {
      return;
    }
    if (state.tab === "edit" && state.dirty) {
      const ok = await handleDirtyBefore();
      if (!ok) {
        return;
      }
    }
    state.currentIndex = nextIndex;
    if (state.tab === "edit") {
      await enterEditFromCurrent();
      return;
    }
    await render();
  }

  async function moveCurrent(delta) {
    let next = state.currentIndex + delta;
    if (state.currentIndex < 0) {
      next = 0;
    }
    await moveToIndex(next);
  }

  async function handleLayoutDirtyBefore() {
    if (!state.layoutDirty) {
      return true;
    }
    const choice = await showDirtyDialog();
    if (choice === "save") {
      return performLayoutSave();
    }
    state.layoutDraft = cloneLayout(state.layout);
    captureLayoutBaseline();
    await render();
    return false;
  }

  async function performLayoutSave() {
    try {
      const saved = await api(
        "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/layout",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(layoutPayloadFromDraft()),
        }
      );
      state.layout = saved;
      state.layoutDraft = cloneLayout(saved);
      captureLayoutBaseline();
      syncColumnSortFromLayout(saved);
      await loadRows();
      await render();
      setMessage(labels().msg_layout_saved, false);
      return true;
    } catch (error) {
      setMessage(String(error.message || error), true);
      return false;
    }
  }

  function moveVisibleField(fieldKey, delta) {
    const visibleCols = visibleLayoutColumns();
    const index = visibleCols.findIndex(function (col) {
      return col.field_key === fieldKey;
    });
    if (index < 0) {
      return;
    }
    const target = index + delta;
    if (target < 0 || target >= visibleCols.length) {
      return;
    }
    const a = visibleCols[index];
    const b = visibleCols[target];
    const orderA = a.display_order;
    a.display_order = b.display_order;
    b.display_order = orderA;
    reorderLayoutColumns();
    markLayoutDirty();
  }

  async function cycleHeaderSort(field) {
    const current = state.columnSort[field] || "";
    let next = "";
    if (current === "desc") {
      next = "";
    } else if (current === "") {
      next = "asc";
    } else if (current === "asc") {
      next = "desc";
    } else {
      throw new Error("Invalid sort direction: " + current);
    }
    state.columnSort[field] = next;
    await loadRows();
    await render();
  }

  async function switchTab(tabKey) {
    if (tabKey === state.tab) {
      return;
    }
    if (state.tab === "edit" && state.dirty) {
      const ok = await handleDirtyBefore();
      if (!ok) {
        return;
      }
    }
    if (state.tab === "layout" && state.layoutDirty) {
      const ok = await handleLayoutDirtyBefore();
      if (!ok) {
        return;
      }
    }
    if (tabKey === "edit") {
      if (!state.editMode) {
        if (currentRow()) {
          await enterEditFromCurrent();
          return;
        }
      }
    }
    if (tabKey === "layout") {
      await loadLayout(true);
      state.layoutDraft = cloneLayout(state.layout);
      captureLayoutBaseline();
    }
    state.tab = tabKey;
    await render();
  }

  async function render() {
    let body = "";
    if (state.tab === "list") {
      body = renderList();
    } else if (state.tab === "edit") {
      body = renderEdit();
    } else if (state.tab === "attachments") {
      body = renderPlaceholderTab(labels().tab_attachments);
    } else if (state.tab === "messages") {
      body = renderPlaceholderTab(labels().tab_messages);
    } else if (state.tab === "layout") {
      body = renderLayout();
    } else {
      body = renderPlaceholderTab(labels().tab_messages);
    }
    root.innerHTML = renderTabBar() + body + renderMessage();
    bindEvents();
    if (state.tab === "edit" && state.editMode) {
      captureBaseline();
    }
  }

  function bindEvents() {
    root.querySelectorAll("[data-tui-tab]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await switchTab(btn.getAttribute("data-tui-tab"));
      });
    });

    const first = document.getElementById("tuiNavFirst");
    if (first) {
      first.addEventListener("click", async function () {
        await moveToIndex(0);
      });
    }
    const prev = document.getElementById("tuiNavPrev");
    if (prev) {
      prev.addEventListener("click", async function () {
        await moveCurrent(-1);
      });
    }
    const next = document.getElementById("tuiNavNext");
    if (next) {
      next.addEventListener("click", async function () {
        await moveCurrent(1);
      });
    }
    const last = document.getElementById("tuiNavLast");
    if (last) {
      last.addEventListener("click", async function () {
        await moveToIndex(state.rows.length - 1);
      });
    }

    async function runSearch() {
      const searchInput = document.getElementById("tuiSearch");
      state.search = searchInput ? searchInput.value.trim() : "";
      await loadRows();
      await render();
    }

    const searchBtn = document.getElementById("tuiSearchBtn");
    if (searchBtn) {
      searchBtn.addEventListener("click", async function () {
        await runSearch();
      });
    }

    const search = document.getElementById("tuiSearch");
    if (search) {
      search.addEventListener("keydown", async function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          await runSearch();
        }
      });
    }

    const flag = document.getElementById("tuiFlagFilter");
    if (flag) {
      flag.addEventListener("change", async function () {
        state.flagFilter = flag.value;
        await loadRows();
        await render();
      });
    }

    const selectAll = document.getElementById("tuiSelectAll");
    if (selectAll) {
      selectAll.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      selectAll.addEventListener("change", async function () {
        if (selectAll.checked) {
          state.rows.forEach(function (row) {
            state.selectedIds[row.TxId] = true;
          });
        } else {
          state.rows.forEach(function (row) {
            delete state.selectedIds[row.TxId];
          });
        }
        await render();
      });
    }

    const layoutBtn = document.getElementById("tuiLayoutBtn");
    if (layoutBtn) {
      layoutBtn.addEventListener("click", async function () {
        await switchTab("layout");
      });
    }

    const addBtn = document.getElementById("tuiAddBtn");
    if (addBtn) {
      addBtn.addEventListener("click", async function () {
        if (state.tab === "edit" && state.dirty) {
          const ok = await handleDirtyBefore();
          if (!ok) {
            return;
          }
        }
        if (state.tab === "layout" && state.layoutDirty) {
          const ok = await handleLayoutDirtyBefore();
          if (!ok) {
            return;
          }
        }
        await enterAdd();
      });
    }

    root.querySelectorAll(".tui-sortable").forEach(function (th) {
      th.addEventListener("click", async function () {
        await cycleHeaderSort(th.getAttribute("data-sort-field"));
      });
    });

    const zebraEnabled = document.getElementById("tuiZebraEnabled");
    if (zebraEnabled) {
      zebraEnabled.addEventListener("change", function () {
        state.layoutDraft.zebra_enabled = zebraEnabled.checked;
        markLayoutDirty();
        applyLayoutZebraPreview();
      });
    }
    const zebraColor = document.getElementById("tuiZebraColor");
    if (zebraColor) {
      zebraColor.addEventListener("change", function () {
        state.layoutDraft.zebra_color = zebraColor.value;
        const opt = state.layoutDraft.zebra_color_options.find(function (item) {
          return item.color_key === zebraColor.value;
        });
        if (!opt) {
          throw new Error("Unknown zebra_color: " + zebraColor.value);
        }
        zebraColor.style.backgroundColor = opt.css_value;
        markLayoutDirty();
        applyLayoutZebraPreview();
      });
    }

    root.querySelectorAll(".tui-layout-visible").forEach(function (box) {
      box.addEventListener("change", async function () {
        const field = box.getAttribute("data-field");
        const col = state.layoutDraft.columns.find(function (item) {
          return item.field_key === field;
        });
        if (!col) {
          return;
        }
        if (box.checked) {
          const visibleCols = visibleLayoutColumns();
          let maxOrder = 0;
          visibleCols.forEach(function (item) {
            if (item.display_order > maxOrder) {
              maxOrder = item.display_order;
            }
          });
          col.visible = true;
          col.display_order = maxOrder + 1;
        } else {
          col.visible = false;
          col.display_order = 0;
        }
        reorderLayoutColumns();
        markLayoutDirty();
        await renderLayoutKeepDirty();
      });
    });

    root.querySelectorAll(".tui-layout-sort").forEach(function (select) {
      select.addEventListener("change", function () {
        const field = select.getAttribute("data-field");
        const col = state.layoutDraft.columns.find(function (item) {
          return item.field_key === field;
        });
        if (!col) {
          return;
        }
        col.sort_direction = select.value;
        markLayoutDirty();
      });
    });

    async function renderLayoutKeepDirty() {
      const dirty = state.layoutDirty;
      const baseline = state.layoutBaseline;
      await render();
      state.layoutBaseline = baseline;
      state.layoutDirty = dirty;
    }

    root.querySelectorAll(".tui-layout-up").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        moveVisibleField(btn.getAttribute("data-field"), -1);
        await renderLayoutKeepDirty();
      });
    });
    root.querySelectorAll(".tui-layout-down").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        moveVisibleField(btn.getAttribute("data-field"), 1);
        await renderLayoutKeepDirty();
      });
    });

    const layoutSaveBtn = document.getElementById("tuiLayoutSaveBtn");
    if (layoutSaveBtn) {
      layoutSaveBtn.addEventListener("click", async function () {
        await performLayoutSave();
      });
    }
    const layoutCancelBtn = document.getElementById("tuiLayoutCancelBtn");
    if (layoutCancelBtn) {
      layoutCancelBtn.addEventListener("click", async function () {
        if (!state.layoutDirty) {
          return;
        }
        state.layoutDraft = cloneLayout(state.layout);
        captureLayoutBaseline();
        await render();
      });
    }

    let dragField = null;
    root.querySelectorAll(".tui-layout-row[draggable='true']").forEach(function (rowEl) {
      rowEl.addEventListener("dragstart", function () {
        dragField = rowEl.getAttribute("data-field");
      });
      rowEl.addEventListener("dragover", function (event) {
        event.preventDefault();
      });
      rowEl.addEventListener("drop", async function (event) {
        event.preventDefault();
        const targetField = rowEl.getAttribute("data-field");
        if (!dragField || dragField === targetField) {
          return;
        }
        const visibleCols = visibleLayoutColumns();
        const from = visibleCols.findIndex(function (col) {
          return col.field_key === dragField;
        });
        const to = visibleCols.findIndex(function (col) {
          return col.field_key === targetField;
        });
        if (from < 0 || to < 0) {
          return;
        }
        const moved = visibleCols.splice(from, 1)[0];
        visibleCols.splice(to, 0, moved);
        visibleCols.forEach(function (col, index) {
          col.display_order = index + 1;
        });
        reorderLayoutColumns();
        markLayoutDirty();
        dragField = null;
        await renderLayoutKeepDirty();
      });
    });

    root.querySelectorAll(".tui-row-check").forEach(function (box) {
      box.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      box.addEventListener("change", async function () {
        const txid = box.getAttribute("data-txid");
        if (box.checked) {
          state.selectedIds[txid] = true;
        } else {
          delete state.selectedIds[txid];
        }
        await render();
      });
    });

    root.querySelectorAll(".tui-toggle-btn").forEach(function (btn) {
      btn.addEventListener("click", async function (event) {
        event.stopPropagation();
        const txid = btn.getAttribute("data-txid");
        await api(
          "/api/maint/" +
            encodeURIComponent(state.tableKey) +
            "/rows/" +
            encodeURIComponent(txid) +
            "/toggle-disable",
          { method: "POST" }
        );
        await loadRows();
        await render();
      });
    });

    root.querySelectorAll(".tui-copy-btn").forEach(function (btn) {
      btn.addEventListener("click", async function (event) {
        event.stopPropagation();
        if (state.tab === "edit" && state.dirty) {
          const ok = await handleDirtyBefore();
          if (!ok) {
            return;
          }
        }
        await enterCopy(btn.getAttribute("data-txid"));
      });
    });

    root.querySelectorAll(".tui-row").forEach(function (rowEl) {
      function isRowActionTarget(event) {
        return !!(
          event.target.closest(".tui-row-check") ||
          event.target.closest(".tui-toggle-btn") ||
          event.target.closest(".tui-copy-btn")
        );
      }
      rowEl.addEventListener("click", async function (event) {
        if (isRowActionTarget(event)) {
          return;
        }
        state.currentIndex = Number(rowEl.getAttribute("data-index"));
        await render();
      });
      rowEl.addEventListener("dblclick", async function (event) {
        if (isRowActionTarget(event)) {
          return;
        }
        state.currentIndex = Number(rowEl.getAttribute("data-index"));
        await enterEditFromCurrent();
      });
    });

    const saveBtn = document.getElementById("tuiSaveBtn");
    if (saveBtn) {
      saveBtn.addEventListener("click", async function () {
        await performSave();
      });
    }

    const cancelBtn = document.getElementById("tuiCancelBtn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", async function () {
        if (!state.dirty) {
          return;
        }
        await reloadEditSource();
        state.dirty = false;
        await render();
      });
    }

    root.querySelectorAll(".tui-form-grid [data-field]").forEach(function (input) {
      input.addEventListener("input", markDirtyIfNeeded);
      input.addEventListener("change", markDirtyIfNeeded);
    });
  }

  async function onKeyDown(event) {
    if (!state.meta) {
      return;
    }
    if (state.tab === "list") {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        await moveCurrent(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        await moveCurrent(-1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        await enterEditFromCurrent();
      }
      return;
    }
    if (state.tab === "edit" && state.editMode && !isEditReadonly()) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        const fields = Array.prototype.slice.call(
          root.querySelectorAll(".tui-form-grid [data-field]:not([disabled])")
        );
        if (!fields.length) {
          return;
        }
        const active = document.activeElement;
        let index = fields.indexOf(active);
        if (index < 0) {
          index = 0;
          fields[0].focus();
          event.preventDefault();
          return;
        }
        event.preventDefault();
        const next =
          event.key === "ArrowDown"
            ? Math.min(fields.length - 1, index + 1)
            : Math.max(0, index - 1);
        fields[next].focus();
      }
    }
  }

  document.addEventListener("keydown", onKeyDown);

  api("/api/table-ui/" + encodeURIComponent(state.tableKey) + "/meta")
    .then(async function (meta) {
      state.meta = meta;
      await loadLayout(true);
      await loadRows();
      await render();
    })
    .catch(function (error) {
      root.textContent = String(error);
    });
})();
