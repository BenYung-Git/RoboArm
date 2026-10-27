(function () {
  function createTableUi(root, options) {
  options = options || {};
  const state = {
    tableKey: options.tableKey || root.getAttribute("data-table-key"),
    parentFilter: options.parentFilter || null,
    detailController: null,
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
  if (!state.tableKey) {
    throw new Error("Missing table_ui tableKey");
  }
  root.setAttribute("data-table-key", state.tableKey);

  let tableUiSeq = window.__tuiSeq || 0;
  tableUiSeq += 1;
  window.__tuiSeq = tableUiSeq;
  state.uid = "tui" + tableUiSeq;
  state.embedded = !!options.embedded;
  state.embeddedTitle = options.embeddedTitle || "";
  state.embeddedAddLabel = options.embeddedAddLabel || "";
  state.embeddedToolbar = options.embeddedToolbar || null;
  state.expandedIds = {};
  state.expandErrors = {};
  state.detailControllers = {};
  state.onFilteredCountChange = options.onFilteredCountChange || null;
  if (state.embedded) {
    if (!state.embeddedToolbar) {
      throw new Error("Missing embeddedToolbar for embedded table_ui");
    }
    [
      "show_search",
      "show_flag_filter",
      "show_multi_select_controls",
      "layout_save_placement",
      "layout_settings_placement",
    ].forEach(function (key) {
      if (!(key in state.embeddedToolbar)) {
        throw new Error("Missing embeddedToolbar key: " + key);
      }
    });
  }

  function eid(name) {
    return state.uid + "_" + name;
  }

  function byEid(name) {
    return document.getElementById(eid(name));
  }

  function byFieldEid(field) {
    return document.getElementById(eid("Field_" + field));
  }

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
    if (row[field + "_display"] != null && row[field + "_display"] !== "") {
      return row[field + "_display"];
    }
    if (row[field + "_label"] != null && row[field + "_label"] !== "") {
      return row[field + "_label"];
    }
    const column = columnByField(field);
    if (
      column &&
      column.display_decimals != null &&
      row[field] != null &&
      row[field] !== ""
    ) {
      return Number(row[field]).toFixed(Number(column.display_decimals));
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

  function layoutSaveIconBtn(id, tip, enabled) {
    const L = labels();
    return (
      '<button type="button" class="tui-icon-btn tui-btn-layout-save" id="' +
      id +
      '" title="' +
      escapeHtml(tip) +
      '"' +
      (enabled ? "" : " disabled") +
      ">" +
      '<span class="tui-layout-save-main">' +
      escapeHtml(L.icon_layout) +
      "</span>" +
      '<span class="tui-layout-save-badge">' +
      escapeHtml(L.icon_layout_save_badge) +
      "</span></button>"
    );
  }

  function hasExpandDetail() {
    return (
      state.meta &&
      state.meta.detail &&
      state.meta.detail.presentation === "expand_row"
    );
  }

  function hasTabDetail() {
    return (
      state.meta &&
      state.meta.detail &&
      state.meta.detail.presentation === "tab"
    );
  }

  function listColumnCount() {
    let count = listFields().length + 2;
    if (hasExpandDetail()) {
      count += 1;
    }
    return count;
  }

  function renderTabBar() {
    const L = labels();
    const tabs = [
      { key: "list", label: L.tab_list },
      { key: "edit", label: L.tab_edit },
    ];
    if (!state.embedded) {
      if (hasTabDetail()) {
        tabs.push({
          key: state.meta.detail.tab_key,
          label: state.meta.detail.tab_label,
        });
      }
      tabs.push(
        { key: "attachments", label: L.tab_attachments },
        { key: "messages", label: L.tab_messages }
      );
    }
    tabs.push({ key: "layout", label: L.tab_layout });
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
      iconBtn(eid("NavFirst"), L.icon_nav_first, L.tip_nav_first, canFirst) +
      iconBtn(eid("NavPrev"), L.icon_nav_prev, L.tip_nav_prev, canPrev) +
      '<span class="tui-pos">' +
      escapeHtml(positionText()) +
      "</span>" +
      iconBtn(eid("NavNext"), L.icon_nav_next, L.tip_nav_next, canNext) +
      iconBtn(eid("NavLast"), L.icon_nav_last, L.tip_nav_last, canLast) +
      "</div>" +
      "</div>"
    );
  }

  function embedToolbarConfig() {
    if (!state.embedded) {
      return null;
    }
    return state.embeddedToolbar;
  }

  function layoutSaveInChrome() {
    const tb = embedToolbarConfig();
    return !!(tb && tb.layout_save_placement === "chrome");
  }

  function layoutSettingsInChrome() {
    const tb = embedToolbarConfig();
    return !!(tb && tb.layout_settings_placement === "chrome");
  }

  function renderEmbedChrome() {
    if (!state.embedded || state.tab !== "list") {
      return "";
    }
    const L = labels();
    const title = state.embeddedTitle || "";
    const addLabel = state.embeddedAddLabel || L.tip_add;
    let actions =
      '<button type="button" class="tui-btn tui-embed-add" id="' +
      eid("EmbedAddBtn") +
      '">' +
      escapeHtml(addLabel) +
      "</button>";
    if (layoutSaveInChrome()) {
      actions =
        layoutSaveIconBtn(eid("LayoutBtn"), L.tip_layout, true) + actions;
    }
    if (layoutSettingsInChrome()) {
      actions =
        iconBtn(
          eid("OpenLayoutBtn"),
          L.icon_layout,
          L.tip_open_layout,
          true,
          "tui-btn-open-layout"
        ) + actions;
    }
    return (
      '<div class="tui-embed-chrome">' +
      '<div class="tui-embed-title">' +
      escapeHtml(title) +
      "（" +
      escapeHtml(String(filteredTotal())) +
      "）</div>" +
      '<div class="tui-embed-actions">' +
      actions +
      "</div></div>"
    );
  }

  function renderListToolbar() {
    const L = labels();
    const chrome = renderEmbedChrome();
    const tb = embedToolbarConfig();
    const showSearch = !tb || tb.show_search;
    const showFlag = !tb || tb.show_flag_filter;
    const showMulti = !tb || tb.show_multi_select_controls;
    const showLayoutInToolbar = !layoutSaveInChrome();
    const addBtn = state.embedded
      ? ""
      : iconBtn(eid("AddBtn"), L.icon_add, L.tip_add, true);
    if (
      state.embedded &&
      !showSearch &&
      !showFlag &&
      !showMulti &&
      !showLayoutInToolbar &&
      !addBtn
    ) {
      return chrome;
    }
    const selectAllLabel = allFilteredChecked()
      ? L.label_deselect_all
      : L.label_select_all;
    let leftHtml = "";
    if (showSearch) {
      leftHtml +=
        '<div class="tui-search">' +
        "<span>" +
        escapeHtml(L.search) +
        "</span>" +
        '<div class="tui-search-row">' +
        '<input type="text" id="' +
        eid("Search") +
        '" value="' +
        escapeHtml(state.search) +
        '">' +
        iconBtn(
          eid("SearchBtn"),
          L.icon_search,
          L.tip_search,
          true,
          "tui-icon-search"
        ) +
        "</div></div>";
    }
    if (showFlag) {
      leftHtml +=
        '<label class="tui-filter"><span>' +
        escapeHtml(columnByField("isDisable").label) +
        '</span><select id="' +
        eid("FlagFilter") +
        '">' +
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
        "</select></label>";
    }
    let rightHtml = "";
    if (showLayoutInToolbar) {
      rightHtml += layoutSaveIconBtn(eid("LayoutBtn"), L.tip_layout, true);
    }
    if (showMulti) {
      rightHtml +=
        '<label class="tui-check-all">' +
        '<input type="checkbox" id="' +
        eid("SelectAll") +
        '"' +
        (allFilteredChecked() ? " checked" : "") +
        ">" +
        "<span>" +
        escapeHtml(selectAllLabel) +
        "</span></label>" +
        '<span class="tui-check-count">' +
        escapeHtml(checkedCount() + " / " + filteredTotal()) +
        "</span>";
    }
    rightHtml += addBtn;
    if (!leftHtml && !rightHtml) {
      return chrome;
    }
    return (
      chrome +
      '<div class="tui-toolbar">' +
      leftHtml +
      (rightHtml
        ? '<div class="tui-toolbar-right">' + rightHtml + "</div>"
        : "") +
      "</div>"
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
      if (col.is_system) {
        return;
      }
      const direction = state.columnSort[col.field_key] || "";
      if (direction === "asc" || direction === "desc") {
        specs.push({ field: col.field_key, dir: direction });
      }
    });
    return specs;
  }

  function syncDraftSortFromColumnSort() {
    if (!state.layoutDraft || !state.layoutDraft.columns) {
      return;
    }
    state.layoutDraft.columns.forEach(function (col) {
      if (col.is_system) {
        col.sort_direction = "";
        return;
      }
      col.sort_direction = state.columnSort[col.field_key] || "";
    });
  }

  function widthLimitsForField(field) {
    const source = state.layoutDraft || state.layout;
    if (source && source.columns) {
      const col = source.columns.find(function (item) {
        return item.field_key === field;
      });
      if (col && col.width_min != null && col.width_max != null) {
        return { min: Number(col.width_min), max: Number(col.width_max) };
      }
    }
    if (state.layout && state.layout.width_rules) {
      const rules = state.layout.width_rules;
      if (rules.system && rules.system[field]) {
        return {
          min: Number(rules.system[field].min),
          max: Number(rules.system[field].max),
        };
      }
      if (rules.data) {
        return { min: Number(rules.data.min), max: Number(rules.data.max) };
      }
    }
    throw new Error("Missing width rules for field: " + field);
  }

  function clampColumnWidth(field, width) {
    const limits = widthLimitsForField(field);
    const value = Number(width);
    if (!Number.isFinite(value)) {
      throw new Error("Invalid column width: " + width);
    }
    return Math.min(limits.max, Math.max(limits.min, Math.round(value)));
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

  function multiSelectFieldKey() {
    if (
      state.layout &&
      state.layout.width_rules &&
      state.layout.width_rules.system
    ) {
      const keys = Object.keys(state.layout.width_rules.system);
      if (keys.length) {
        return keys[0];
      }
    }
    const col =
      state.layout &&
      state.layout.columns &&
      state.layout.columns.find(function (item) {
        return item.is_system;
      });
    if (!col) {
      throw new Error("Missing multi-select layout column");
    }
    return col.field_key;
  }

  function renderListTablePanel() {
    const L = labels();
    const fields = listFields();
    const zebraEnabled = listZebraEnabled();
    const zebraCss = listZebraCss();
    const multiField = multiSelectFieldKey();
    const multiWidth = columnWidthForField(multiField);
    const expandDetail = hasExpandDetail() ? state.meta.detail : null;
    let head = "<tr>";
    if (expandDetail) {
      head += '<th class="tui-expand-col"></th>';
    }
    head +=
      '<th class="tui-multi-select-col" data-resize-col="' +
      escapeHtml(multiField) +
      '" style="width:' +
      multiWidth +
      "px;min-width:" +
      multiWidth +
      'px;position:relative;">' +
      '<span class="tui-col-resizer" data-resize-field="' +
      escapeHtml(multiField) +
      '"></span></th>';
    fields.forEach(function (field) {
      const width = columnWidthForField(field);
      head +=
        '<th class="tui-sortable" data-sort-field="' +
        escapeHtml(field) +
        '" style="width:' +
        width +
        "px;min-width:" +
        width +
        'px;position:relative;">' +
        escapeHtml(columnByField(field).label + sortMark(field)) +
        '<span class="tui-col-resizer" data-resize-field="' +
        escapeHtml(field) +
        '"></span></th>';
    });
    head +=
      '<th class="tui-actions-col">' + escapeHtml(L.actions) + "</th></tr>";

    let body = "";
    const colCount = listColumnCount();
    state.rows.forEach(function (row, index) {
      const isCurrent = index === state.currentIndex;
      const txKey = String(row.TxId);
      const expanded = !!(expandDetail && state.expandedIds[txKey]);
      body +=
        '<tr class="tui-row' +
        (isCurrent ? " is-current" : "") +
        (zebraEnabled && index % 2 === 1 ? " tui-zebra-row" : "") +
        '" data-index="' +
        index +
        '" data-txid="' +
        escapeHtml(row.TxId) +
        '">';
      if (expandDetail) {
        body +=
          '<td class="tui-expand-col"><button type="button" class="tui-expand-btn" data-txid="' +
          escapeHtml(row.TxId) +
          '" title="' +
          escapeHtml(
            expanded ? expandDetail.tip_collapse : expandDetail.tip_expand
          ) +
          '" aria-expanded="' +
          (expanded ? "true" : "false") +
          '">' +
          escapeHtml(
            expanded
              ? expandDetail.expanded_icon
              : expandDetail.collapsed_icon
          ) +
          "</button></td>";
      }
      body +=
        '<td class="tui-multi-select-col" style="width:' +
        multiWidth +
        "px;min-width:" +
        multiWidth +
        'px;"><input type="checkbox" class="tui-row-check" data-txid="' +
        escapeHtml(row.TxId) +
        '"' +
        (state.selectedIds[row.TxId] ? " checked" : "") +
        "></td>";
      fields.forEach(function (field) {
        const value = displayValue(row, field);
        const width = columnWidthForField(field);
        const style =
          ' style="width:' + width + "px;min-width:" + width + 'px;"';
        if (field === "isDisable") {
          body +=
            "<td" +
            style +
            '><span class="tui-status ' +
            (row.isDisable ? "is-disabled" : "is-enabled") +
            '">' +
            escapeHtml(value) +
            "</span></td>";
        } else {
          body += "<td" + style + ">" + escapeHtml(value) + "</td>";
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
      if (expanded) {
        const err = state.expandErrors[txKey];
        body +=
          '<tr class="tui-expand-row" data-expand-txid="' +
          escapeHtml(row.TxId) +
          '"><td colspan="' +
          colCount +
          '"><div class="tui-expand-panel">';
        if (err) {
          body +=
            '<div class="tui-expand-error">' +
            escapeHtml(err) +
            "</div>";
        } else {
          body +=
            '<div class="tui-expand-host" data-expand-host="' +
            escapeHtml(row.TxId) +
            '"><div class="tui-expand-loading">' +
            escapeHtml(expandDetail.loading_message) +
            "</div></div>";
        }
        body += "</div></td></tr>";
      }
    });

    return (
      '<div class="tui-panel"><div class="tui-table-wrap"><table class="tui-table tui-data-table' +
      (zebraEnabled ? " tui-zebra" : "") +
      (expandDetail ? " tui-has-expand" : "") +
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
    syncDraftSortFromColumnSort();
    return {
      zebra_enabled: !!state.layoutDraft.zebra_enabled,
      zebra_color: state.layoutDraft.zebra_color,
      columns: state.layoutDraft.columns.map(function (col) {
        return {
          field_key: col.field_key,
          visible: col.is_system ? true : !!col.visible,
          sort_direction: col.is_system ? "" : col.sort_direction || "",
          column_width: Number(col.column_width),
        };
      }),
    };
  }

  function layoutPayloadForSave() {
    const payload = layoutPayloadFromDraft();
    payload.columns = payload.columns.map(function (col) {
      return {
        field_key: col.field_key,
        visible: col.visible,
        sort_direction: col.sort_direction,
        column_width: clampColumnWidth(col.field_key, col.column_width),
      };
    });
    return payload;
  }

  function columnWidthForField(field) {
    const source = state.layoutDraft || state.layout;
    if (!source || !source.columns) {
      throw new Error("Missing layout for column width: " + field);
    }
    const col = source.columns.find(function (item) {
      return item.field_key === field;
    });
    if (!col || col.column_width == null || col.column_width === "") {
      throw new Error("Missing column_width for field: " + field);
    }
    return Number(col.column_width);
  }

  function currentCategoryCode() {
    const vis = state.meta && state.meta.field_visibility;
    if (!vis || !vis.depends_on_field) {
      return null;
    }
    const field = vis.depends_on_field;
    const annotateKey = vis.annotate_key || "category_code";
    let value = null;
    if (state.editMode && !isEditReadonly()) {
      const input = byFieldEid(field);
      if (input) {
        value = input.value;
      }
    }
    if ((value == null || value === "") && state.editSource) {
      value = state.editSource[field];
    }
    if (value == null || value === "") {
      return null;
    }
    const column = columnByField(field);
    const options = (column && column.options) || [];
    const hit = options.find(function (option) {
      return String(option.value) === String(value);
    });
    return hit && hit[annotateKey] != null ? hit[annotateKey] : null;
  }

  function hiddenFieldsForCategory(categoryCode) {
    const vis = state.meta && state.meta.field_visibility;
    if (!vis || !vis.rules) {
      return [];
    }
    if (!categoryCode) {
      return [];
    }
    const rule = vis.rules.find(function (item) {
      return item.category_code === categoryCode;
    });
    if (!rule) {
      return [];
    }
    if (rule.hide_fields) {
      return rule.hide_fields.slice();
    }
    if (rule.show_fields) {
      const show = {};
      rule.show_fields.forEach(function (field) {
        show[field] = true;
      });
      const hidden = [];
      vis.rules.forEach(function (other) {
        (other.show_fields || []).forEach(function (field) {
          if (!show[field] && hidden.indexOf(field) < 0) {
            hidden.push(field);
          }
        });
        (other.hide_fields || []).forEach(function (field) {
          if (hidden.indexOf(field) < 0) {
            hidden.push(field);
          }
        });
      });
      return hidden.filter(function (field) {
        return !show[field];
      });
    }
    return [];
  }

  function applyFieldVisibility() {
    const hidden = hiddenFieldsForCategory(currentCategoryCode());
    state.meta.columns.forEach(function (column) {
      const row = root.querySelector(
        '.tui-field-row[data-field="' + column.field + '"]'
      );
      if (!row) {
        return;
      }
      if (hidden.indexOf(column.field) >= 0) {
        row.style.display = "none";
      } else {
        row.style.display = "";
      }
    });
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
        return !col.is_system && col.visible;
      })
      .slice()
      .sort(function (a, b) {
        return a.display_order - b.display_order;
      });
  }

  function reorderLayoutColumns() {
    const draft = state.layoutDraft;
    const system = [];
    const visible = [];
    const hidden = [];
    draft.columns.forEach(function (col) {
      if (col.is_system) {
        system.push(col);
        return;
      }
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
    draft.columns = system.concat(visible).concat(hidden);
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
      const isSystem = !!col.is_system;
      const canMove = !isSystem && !!col.visible && col.can_reorder !== false;
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
      const widthLimits = widthLimitsForField(col.field_key);
      const widthValue = Number(col.column_width);
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
        (isSystem || col.can_hide === false ? " disabled" : "") +
        ">" +
        "</td>" +
        "<td>" +
        escapeHtml(col.field_label) +
        "</td>" +
        "<td>" +
        escapeHtml(col.field_desc) +
        "</td>" +
        "<td>" +
        '<input type="number" class="tui-layout-width" data-field="' +
        escapeHtml(col.field_key) +
        '" value="' +
        escapeHtml(widthValue) +
        '" min="' +
        widthLimits.min +
        '" max="' +
        widthLimits.max +
        '" step="1">' +
        "</td>" +
        "<td>" +
        '<select class="tui-layout-sort" data-field="' +
        escapeHtml(col.field_key) +
        '"' +
        (isSystem || col.sortable === false ? " disabled" : "") +
        ">" +
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
      '<select id="' + eid("ZebraColor") + '"' +
      zebraSelectStyle +
      ">" +
      colorOptions +
      "</select>" +
      '<label class="tui-check-all"><input type="checkbox" id="' + eid("ZebraEnabled") + '"' +
      (draft.zebra_enabled ? " checked" : "") +
      "> <span>" +
      escapeHtml(L.layout_zebra_enabled) +
      "</span></label></div>" +
      '<div class="tui-layout-row3">' +
      "<h4>" +
      escapeHtml(L.layout_columns) +
      "</h4>" +
      '<div class="tui-edit-toolbar">' +
      layoutSaveIconBtn(eid("LayoutSaveBtn"), L.tip_save_layout, true) +
      iconBtn(eid("LayoutCancelBtn"), L.icon_cancel, L.tip_cancel_layout, true) +
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
      escapeHtml(L.layout_column_width) +
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
      !column.editable ||
      column.auto_gen ||
      column.is_flag ||
      column.force_value != null ||
      (column.field === "TxId" &&
        (state.editMode === "add" || state.editMode === "copy"));
    const requiredMark =
      column.required && !readonly && !column.auto_gen && !column.is_flag
        ? '<span class="tui-required">*</span>'
        : "";
    let value = fieldValueForForm(column);
    if (column.force_value != null) {
      value = column.force_value;
    }
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
    } else if (
      (column.field_type === "select" || column.field_type === "relation") &&
      !readonly
    ) {
      let options = (column.options || []).slice();
      if (value != null && String(value) !== "") {
        const found = options.some(function (option) {
          return String(option.value) === String(value);
        });
        if (!found) {
          const currentLabel =
            state.editSource && state.editSource[column.field + "_label"] != null
              ? state.editSource[column.field + "_label"]
              : value;
          options = options.concat([{ value: value, label: currentLabel }]);
        }
      }
      let optionsHtml = '<option value=""></option>';
      options.forEach(function (option) {
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
        '" id="' +
        eid("Field_" + column.field) +
        '">' +
        optionsHtml +
        "</select>";
    } else if (
      (column.field_type === "select" || column.field_type === "relation") &&
      readonly
    ) {
      let shown = value;
      if (
        state.editSource &&
        state.editSource[column.field + "_label"] != null &&
        state.editSource[column.field + "_label"] !== ""
      ) {
        shown = state.editSource[column.field + "_label"];
      } else {
        (column.options || []).forEach(function (option) {
          if (String(option.value) === String(value)) {
            shown = option.label;
          }
        });
      }
      control =
        '<input type="text" disabled value="' + escapeHtml(shown) + '">';
    } else {
      let inputType =
        column.field_type === "number" || column.field_type === "long"
          ? "number"
          : "text";
      let shownValue = value == null ? "" : value;
      if (
        column.display_decimals != null &&
        shownValue !== "" &&
        shownValue != null
      ) {
        shownValue = Number(shownValue).toFixed(
          Number(column.display_decimals)
        );
        if (readonly) {
          inputType = "text";
        }
      }
      control =
        '<input type="' +
        inputType +
        '" data-field="' +
        escapeHtml(column.field) +
        '" id="' +
        eid("Field_" + column.field) +
        '" value="' +
        escapeHtml(shownValue) +
        '"' +
        (readonly ? " disabled" : "") +
        ">";
      if (column.field === "IpAddress" && !readonly) {
        control =
          '<div class="tui-ip-detect-wrap">' +
          control +
          '<button type="button" class="tui-btn tui-detect-ip-btn" id="' + eid("DetectIpBtn") + '">' +
          escapeHtml(labels().btn_detect_network_ip) +
          "</button>" +
          '<div class="tui-ip-detect-list" id="' + eid("DetectIpList") + '"></div></div>';
      }
    }
    return (
      '<label class="tui-form-field tui-field-row" data-field="' +
      escapeHtml(column.field) +
      '"><span>' +
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
      iconBtn(eid("SaveBtn"), L.icon_save, L.tip_save, !readonly && !state.saving) +
      iconBtn(eid("CancelBtn"), L.icon_cancel, L.tip_cancel, !readonly) +
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
      return '<div class="tui-message" id="' + eid("Message") + '"></div>';
    }
    return (
      '<div class="tui-message' +
      (state.messageError ? " is-error" : " is-ok") +
      '" id="' + eid("Message") + '">' +
      escapeHtml(state.message) +
      "</div>"
    );
  }

  function setMessage(text, isError) {
    state.message = text || "";
    state.messageError = !!isError;
    const el = byEid("Message");
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
    if (state.parentFilter) {
      params.set("filter_field", state.parentFilter.field);
      params.set("filter_value", String(state.parentFilter.value));
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
      if (!state.layoutDirty) {
        state.layout = data.layout;
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
    const hidden = hiddenFieldsForCategory(currentCategoryCode());
    state.meta.columns.forEach(function (column) {
      if (!column.editable) {
        return;
      }
      if (hidden.indexOf(column.field) >= 0) {
        payload[column.field] = "";
        return;
      }
      const input = byFieldEid(column.field);
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

  function syncDisplayFieldsFromRelation(relationField) {
    if (!state.meta || !relationField) {
      return;
    }
    const relationCol = columnByField(relationField);
    if (!relationCol || relationCol.field_type !== "relation") {
      return;
    }
    const select = byFieldEid(relationField);
    if (!select) {
      return;
    }
    const selected = (relationCol.options || []).find(function (option) {
      return String(option.value) === String(select.value);
    });
    state.meta.columns.forEach(function (column) {
      if (column.field_type !== "display") {
        return;
      }
      const source = column.display_from_field || "";
      const prefix = relationField + "_";
      if (source.indexOf(prefix) !== 0) {
        return;
      }
      const annotateKey = source.slice(prefix.length);
      const displayEl = byFieldEid(column.field);
      if (!displayEl) {
        return;
      }
      displayEl.value =
        selected && selected[annotateKey] != null ? selected[annotateKey] : "";
    });
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
      } else if (column.default_value != null) {
        source[column.field] = column.default_value;
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
    if (state.parentFilter) {
      payload[state.parentFilter.field] = state.parentFilter.value;
    }
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
      state.previewTxId = null;
      await loadRows();
      const idx = state.rows.findIndex(function (row) {
        return Number(row.TxId) === Number(saved.TxId);
      });
      if (idx >= 0) {
        state.currentIndex = idx;
      }
      if (state.embedded) {
        state.tab = "list";
        state.editMode = null;
        state.editSource = null;
      } else {
        state.editMode = "edit";
        state.editSource = saved;
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
    if (state.parentFilter && !state.parentFilter.value) {
      setMessage(
        (state.meta.detail && state.meta.detail.require_parent_message) ||
          labels().msg_select_row,
        true
      );
      return;
    }
    const next = await api(
      "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/next-txid"
    );
    state.editMode = "add";
    state.editSource = emptySource();
    if (state.parentFilter) {
      state.editSource[state.parentFilter.field] = state.parentFilter.value;
    }
    if (state.parentFilter) {
      const autoCols = state.meta.columns.filter(function (column) {
        return (
          column.auto_gen &&
          column.field !== "TxId" &&
          !column.is_flag &&
          column.field_type === "number"
        );
      });
      for (let i = 0; i < autoCols.length; i += 1) {
        const column = autoCols[i];
        const peeked = await api(
          "/api/table-ui/" +
            encodeURIComponent(state.tableKey) +
            "/peek-auto/" +
            encodeURIComponent(column.field) +
            "?scope_value=" +
            encodeURIComponent(state.parentFilter.value)
        );
        state.editSource[column.field] = peeked.value;
      }
    }
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
    await loadLayout(true);
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
          body: JSON.stringify(layoutPayloadForSave()),
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
    ensureLayoutDraft();
    const draftCol = state.layoutDraft.columns.find(function (item) {
      return item.field_key === field;
    });
    if (!draftCol || draftCol.is_system) {
      throw new Error("Cannot sort field: " + field);
    }
    draftCol.sort_direction = next;
    if (state.layout && state.layout.columns) {
      const liveCol = state.layout.columns.find(function (item) {
        return item.field_key === field;
      });
      if (liveCol) {
        liveCol.sort_direction = next;
      }
    }
    markLayoutDirty();
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
    if (state.layoutDirty && state.tab !== "layout") {
      const ok = await handleLayoutDirtyBefore();
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
      if (!state.layoutDirty) {
        await loadLayout(true);
        state.layoutDraft = cloneLayout(state.layout);
        captureLayoutBaseline();
      } else if (!state.layoutDraft) {
        state.layoutDraft = cloneLayout(state.layout);
      }
    }
    state.tab = tabKey;
    await render();
  }

  function destroyDetailController() {
    if (state.detailController && state.detailController.destroy) {
      state.detailController.destroy();
    }
    state.detailController = null;
  }

  function destroyAllExpandControllers() {
    Object.keys(state.detailControllers).forEach(function (txid) {
      const ctrl = state.detailControllers[txid];
      if (ctrl && ctrl.destroy) {
        ctrl.destroy();
      }
    });
    state.detailControllers = {};
  }

  function isDirty() {
    return !!state.dirty || !!state.layoutDirty;
  }

  async function resolveDirty() {
    if (state.tab === "edit" && state.dirty) {
      const ok = await handleDirtyBefore();
      if (!ok) {
        return false;
      }
    }
    if (state.layoutDirty) {
      const ok = await handleLayoutDirtyBefore();
      if (!ok) {
        return false;
      }
    }
    return true;
  }

  async function ensureExpandChildrenClean() {
    const keys = Object.keys(state.detailControllers);
    for (let i = 0; i < keys.length; i += 1) {
      const ctrl = state.detailControllers[keys[i]];
      if (ctrl && ctrl.isDirty && ctrl.isDirty()) {
        const ok = await ctrl.resolveDirty();
        if (!ok) {
          return false;
        }
      }
    }
    return true;
  }

  function renderDetailTab() {
    const detail = state.meta.detail;
    const parent = currentRow();
    if (!parent || parent.TxId == null || parent.TxId === "") {
      return (
        '<div class="tui-panel"><div class="tui-placeholder">' +
        escapeHtml(detail.require_parent_message) +
        "</div></div>"
      );
    }
    return (
      '<div class="tui-panel"><div id="' + eid("DetailRoot") + '" class="tui-detail-root" data-table-key="' +
      escapeHtml(detail.table_key) +
      '"></div></div>'
    );
  }

  async function mountDetailController() {
    destroyDetailController();
    const host = byEid("DetailRoot");
    if (!host || !state.meta.detail) {
      return;
    }
    const parent = currentRow();
    if (!parent) {
      return;
    }
    state.detailController = createTableUi(host, {
      tableKey: state.meta.detail.table_key,
      parentFilter: {
        field: state.meta.detail.parent_field,
        value: parent.TxId,
      },
    });
    await state.detailController.ready;
  }

  async function remountExpandedDetails() {
    if (!hasExpandDetail() || state.tab !== "list") {
      destroyAllExpandControllers();
      return;
    }
    const detail = state.meta.detail;
    const txids = Object.keys(state.expandedIds).filter(function (txid) {
      return state.expandedIds[txid];
    });
    for (let i = 0; i < txids.length; i += 1) {
      const txid = txids[i];
      if (state.expandErrors[txid]) {
        continue;
      }
      const host = root.querySelector(
        '.tui-expand-host[data-expand-host="' + txid + '"]'
      );
      if (!host) {
        continue;
      }
      host.innerHTML = "";
      try {
        const ctrl = createTableUi(host, {
          tableKey: detail.table_key,
          parentFilter: {
            field: detail.parent_field,
            value: txid,
          },
          embedded: true,
          embeddedTitle: detail.title,
          embeddedAddLabel: detail.add_label,
          embeddedToolbar: detail.embedded_toolbar,
        });
        await ctrl.ready;
        state.detailControllers[txid] = ctrl;
      } catch (error) {
        state.expandErrors[txid] =
          detail.load_error_message +
          " " +
          String(error && error.message ? error.message : error);
        if (state.detailControllers[txid]) {
          state.detailControllers[txid].destroy();
          delete state.detailControllers[txid];
        }
        await render({ skipChildDirtyCheck: true });
        return;
      }
    }
  }

  async function toggleExpandRow(txid) {
    const txKey = String(txid);
    if (state.expandedIds[txKey]) {
      const ctrl = state.detailControllers[txKey];
      if (ctrl && ctrl.isDirty && ctrl.isDirty()) {
        const ok = await ctrl.resolveDirty();
        if (!ok) {
          return;
        }
      }
      if (ctrl && ctrl.destroy) {
        ctrl.destroy();
      }
      delete state.detailControllers[txKey];
      delete state.expandedIds[txKey];
      delete state.expandErrors[txKey];
      await render();
      return;
    }
    state.expandedIds[txKey] = true;
    delete state.expandErrors[txKey];
    await render();
  }

  async function render(renderOptions) {
    renderOptions = renderOptions || {};
    if (!renderOptions.skipChildDirtyCheck) {
      const childrenOk = await ensureExpandChildrenClean();
      if (!childrenOk) {
        return;
      }
    }
    let body = "";
    const detailTabKey =
      hasTabDetail() && state.meta.detail ? state.meta.detail.tab_key : null;
    if (state.tab === "list") {
      body = renderList();
    } else if (state.tab === "edit") {
      body = renderEdit();
    } else if (detailTabKey && state.tab === detailTabKey) {
      body = renderDetailTab();
    } else if (state.tab === "attachments") {
      body = renderPlaceholderTab(labels().tab_attachments);
    } else if (state.tab === "messages") {
      body = renderPlaceholderTab(labels().tab_messages);
    } else if (state.tab === "layout") {
      body = renderLayout();
    } else {
      body = renderPlaceholderTab(labels().tab_messages);
    }
    destroyAllExpandControllers();
    destroyDetailController();
    const showTabs = !state.embedded || state.tab !== "list";
    root.innerHTML =
      (showTabs ? renderTabBar() : "") + body + renderMessage();
    root.classList.toggle("tui-embedded", !!state.embedded);
    bindEvents();
    if (state.tab === "edit" && state.editMode) {
      applyFieldVisibility();
      captureBaseline();
    }
    if (detailTabKey && state.tab === detailTabKey) {
      await mountDetailController();
    } else if (hasExpandDetail() && state.tab === "list") {
      await remountExpandedDetails();
    }
    if (state.onFilteredCountChange) {
      state.onFilteredCountChange(filteredTotal());
    }
  }

  function ensureLayoutDraft() {
    if (!state.layoutDraft) {
      state.layoutDraft = cloneLayout(state.layout);
      captureLayoutBaseline();
    }
  }

  function setDraftColumnWidth(field, width) {
    ensureLayoutDraft();
    const clamped = clampColumnWidth(field, width);
    const draftCol = state.layoutDraft.columns.find(function (item) {
      return item.field_key === field;
    });
    if (!draftCol) {
      throw new Error("Unknown layout field for resize: " + field);
    }
    draftCol.column_width = clamped;
    if (state.layout && state.layout.columns) {
      const liveCol = state.layout.columns.find(function (item) {
        return item.field_key === field;
      });
      if (liveCol) {
        liveCol.column_width = clamped;
      }
    }
    markLayoutDirty();
    return clamped;
  }

  function bindColumnResizers() {
    root.querySelectorAll(".tui-col-resizer").forEach(function (handle) {
      handle.addEventListener("mousedown", function (event) {
        event.preventDefault();
        event.stopPropagation();
        const field = handle.getAttribute("data-resize-field");
        const th = handle.parentElement;
        const startX = event.clientX;
        const startWidth = columnWidthForField(field);
        const limits = widthLimitsForField(field);
        const multiField = multiSelectFieldKey();
        function onMove(moveEvent) {
          const next = Math.min(
            limits.max,
            Math.max(limits.min, startWidth + (moveEvent.clientX - startX))
          );
          th.style.width = next + "px";
          th.style.minWidth = next + "px";
          root.querySelectorAll(".tui-row").forEach(function (rowEl) {
            const cells = rowEl.querySelectorAll("td");
            let cell = null;
            if (field === multiField) {
              cell = cells[0];
            } else {
              const fields = listFields();
              const index = fields.indexOf(field);
              if (index >= 0) {
                cell = cells[index + 1];
              }
            }
            if (cell) {
              cell.style.width = next + "px";
              cell.style.minWidth = next + "px";
            }
          });
          handle.setAttribute("data-current-width", String(next));
        }
        function onUp() {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          const raw = handle.getAttribute("data-current-width");
          const width = raw == null ? startWidth : Number(raw);
          setDraftColumnWidth(field, width);
        }
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  }

  async function detectNetworkIps() {
    const listEl = byEid("DetectIpList");
    if (!listEl) {
      return;
    }
    listEl.innerHTML = "";
    try {
      const result = await api("/api/network/ipv4-detect");
      const items = result.items || [];
      if (!items.length) {
        listEl.textContent = labels().msg_detect_network_ip_empty;
        return;
      }
      items.forEach(function (item) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tui-ip-item";
        const sourceLabel =
          item.source === "local"
            ? labels().label_detect_network_ip_source_local
            : labels().label_detect_network_ip_source_neighbor;
        const iface = item.interface ? " (" + item.interface + ")" : "";
        btn.textContent = item.ip + " · " + sourceLabel + iface;
        btn.addEventListener("click", function () {
          const input = byFieldEid("IpAddress");
          if (input) {
            input.value = item.ip;
            markDirtyIfNeeded();
          }
        });
        listEl.appendChild(btn);
      });
    } catch (error) {
      setMessage(String(error.message || error), true);
    }
  }

  function bindEvents() {
    root.querySelectorAll("[data-tui-tab]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        await switchTab(btn.getAttribute("data-tui-tab"));
      });
    });

    const first = byEid("NavFirst");
    if (first) {
      first.addEventListener("click", async function () {
        await moveToIndex(0);
      });
    }
    const prev = byEid("NavPrev");
    if (prev) {
      prev.addEventListener("click", async function () {
        await moveCurrent(-1);
      });
    }
    const next = byEid("NavNext");
    if (next) {
      next.addEventListener("click", async function () {
        await moveCurrent(1);
      });
    }
    const last = byEid("NavLast");
    if (last) {
      last.addEventListener("click", async function () {
        await moveToIndex(state.rows.length - 1);
      });
    }

    async function runSearch() {
      const searchInput = byEid("Search");
      state.search = searchInput ? searchInput.value.trim() : "";
      await loadRows();
      await render();
    }

    const searchBtn = byEid("SearchBtn");
    if (searchBtn) {
      searchBtn.addEventListener("click", async function () {
        await runSearch();
      });
    }

    const search = byEid("Search");
    if (search) {
      search.addEventListener("keydown", async function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          await runSearch();
        }
      });
    }

    const flag = byEid("FlagFilter");
    if (flag) {
      flag.addEventListener("change", async function () {
        state.flagFilter = flag.value;
        await loadRows();
        await render();
      });
    }

    const selectAll = byEid("SelectAll");
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

    const layoutBtn = byEid("LayoutBtn");
    if (layoutBtn) {
      layoutBtn.addEventListener("click", async function () {
        ensureLayoutDraft();
        await performLayoutSave();
      });
    }
    const openLayoutBtn = byEid("OpenLayoutBtn");
    if (openLayoutBtn) {
      openLayoutBtn.addEventListener("click", async function () {
        await switchTab("layout");
      });
    }

    async function startAdd() {
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
    }

    const addBtn = byEid("AddBtn");
    if (addBtn) {
      addBtn.addEventListener("click", async function () {
        await startAdd();
      });
    }
    const embedAddBtn = byEid("EmbedAddBtn");
    if (embedAddBtn) {
      embedAddBtn.addEventListener("click", async function () {
        await startAdd();
      });
    }

    root.querySelectorAll(":scope .tui-expand-btn").forEach(function (btn) {
      btn.addEventListener("click", async function (event) {
        event.preventDefault();
        event.stopPropagation();
        await toggleExpandRow(btn.getAttribute("data-txid"));
      });
    });

    root.querySelectorAll(".tui-sortable").forEach(function (th) {
      th.addEventListener("click", async function () {
        await cycleHeaderSort(th.getAttribute("data-sort-field"));
      });
    });

    const zebraEnabled = byEid("ZebraEnabled");
    if (zebraEnabled) {
      zebraEnabled.addEventListener("change", function () {
        state.layoutDraft.zebra_enabled = zebraEnabled.checked;
        markLayoutDirty();
        applyLayoutZebraPreview();
      });
    }
    const zebraColor = byEid("ZebraColor");
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
        if (!col || col.is_system) {
          return;
        }
        col.sort_direction = select.value;
        state.columnSort[field] = select.value || "";
        markLayoutDirty();
      });
    });

    root.querySelectorAll(".tui-layout-width").forEach(function (input) {
      input.addEventListener("change", function () {
        const field = input.getAttribute("data-field");
        const clamped = setDraftColumnWidth(field, input.value);
        input.value = String(clamped);
      });
      input.addEventListener("input", function () {
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

    const layoutSaveBtn = byEid("LayoutSaveBtn");
    if (layoutSaveBtn) {
      layoutSaveBtn.addEventListener("click", async function () {
        await performLayoutSave();
      });
    }
    const layoutCancelBtn = byEid("LayoutCancelBtn");
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

    Array.prototype.forEach.call(
      root.querySelectorAll("tr.tui-row"),
      function (rowEl) {
        const expandHost = rowEl.closest(".tui-expand-host");
        if (expandHost && expandHost !== root) {
          return;
        }
        function isRowActionTarget(event) {
          return !!(
            event.target.closest(".tui-row-check") ||
            event.target.closest(".tui-toggle-btn") ||
            event.target.closest(".tui-copy-btn") ||
            event.target.closest(".tui-expand-btn") ||
            event.target.closest(".tui-col-resizer") ||
            event.target.closest("a, button, input, select, textarea")
          );
        }
        rowEl.addEventListener("click", async function (event) {
          if (isRowActionTarget(event)) {
            return;
          }
          event.stopPropagation();
          state.currentIndex = Number(rowEl.getAttribute("data-index"));
          await render();
        });
        rowEl.addEventListener("dblclick", async function (event) {
          if (isRowActionTarget(event)) {
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          state.currentIndex = Number(rowEl.getAttribute("data-index"));
          await enterEditFromCurrent();
        });
      }
    );

    const saveBtn = byEid("SaveBtn");
    if (saveBtn) {
      saveBtn.addEventListener("click", async function () {
        await performSave();
      });
    }

    const cancelBtn = byEid("CancelBtn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", async function () {
        if (state.dirty) {
          await reloadEditSource();
          state.dirty = false;
        }
        if (state.embedded) {
          state.tab = "list";
          state.editMode = null;
          state.editSource = null;
          await loadRows();
        }
        await render();
      });
    }

    root
      .querySelectorAll(".tui-form-grid input[data-field], .tui-form-grid select[data-field]")
      .forEach(function (input) {
        input.addEventListener("input", markDirtyIfNeeded);
        input.addEventListener("change", function () {
          markDirtyIfNeeded();
          if (
            state.meta.field_visibility &&
            input.getAttribute("data-field") ===
              state.meta.field_visibility.depends_on_field
          ) {
            applyFieldVisibility();
          }
          syncDisplayFieldsFromRelation(input.getAttribute("data-field"));
        });
      });

    const detectBtn = byEid("DetectIpBtn");
    if (detectBtn) {
      detectBtn.addEventListener("click", async function () {
        await detectNetworkIps();
      });
    }

    bindColumnResizers();
  }

  async function onKeyDown(event) {
    if (!state.meta) {
      return;
    }
    if (
      document.activeElement &&
      !root.contains(document.activeElement)
    ) {
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

  async function bootstrapTable(tableKey) {
    destroyAllExpandControllers();
    destroyDetailController();
    state.tableKey = tableKey;
    root.setAttribute("data-table-key", tableKey);
    state.tab = "list";
    state.rows = [];
    state.currentIndex = -1;
    state.selectedIds = {};
    state.expandedIds = {};
    state.expandErrors = {};
    state.search = "";
    state.flagFilter = "0";
    state.editMode = null;
    state.editSource = null;
    state.previewTxId = null;
    state.baseline = null;
    state.dirty = false;
    state.saving = false;
    state.pendingAction = null;
    state.message = "";
    state.messageError = false;
    state.layout = null;
    state.layoutDraft = null;
    state.layoutBaseline = null;
    state.layoutDirty = false;
    state.columnSort = {};
    state.meta = await api(
      "/api/table-ui/" + encodeURIComponent(state.tableKey) + "/meta"
    );
    await loadLayout(true);
    await loadRows();
    await render();
  }

  function destroy() {
    destroyAllExpandControllers();
    destroyDetailController();
    document.removeEventListener("keydown", onKeyDown);
    root.innerHTML = "";
  }

  async function switchHostTable(tableKey) {
    if (state.tab === "edit" && state.dirty) {
      const ok = await handleDirtyBefore();
      if (!ok) {
        return false;
      }
    }
    if (state.layoutDirty) {
      const ok = await handleLayoutDirtyBefore();
      if (!ok) {
        return false;
      }
    }
    await bootstrapTable(tableKey);
    return true;
  }

  const ready = bootstrapTable(state.tableKey).catch(function (error) {
    root.textContent = String(error);
    throw error;
  });

  return {
    ready: ready,
    destroy: destroy,
    switchHostTable: switchHostTable,
    isDirty: isDirty,
    resolveDirty: resolveDirty,
  };
  }

  window.TableUi = {
    create: createTableUi,
  };

  const pageRoot = document.getElementById("tableUiRoot");
  if (pageRoot) {
    const mainUi = createTableUi(pageRoot, {
      tableKey: pageRoot.getAttribute("data-table-key"),
    });
    document.querySelectorAll("#tableUiHostTabs .settings-tab").forEach(function (tab) {
      tab.addEventListener("click", async function () {
        const ok = await mainUi.switchHostTable(
          tab.getAttribute("data-table-key")
        );
        if (!ok) {
          return;
        }
        document.querySelectorAll("#tableUiHostTabs .settings-tab").forEach(function (item) {
          item.classList.remove("active");
        });
        tab.classList.add("active");
      });
    });
  }
})();
