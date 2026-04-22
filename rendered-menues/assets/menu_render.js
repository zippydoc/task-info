/* Render an assembled task-info menu into interactive HTML.
 *
 *   MenuRender.render(taskInfo, rootElement)
 *
 * Reads `taskInfo.menu`, which is an array of one-key objects whose values are
 * top-level fieldsets. Each field definition follows the task-info schema:
 * type (fieldset/select/text/textarea/checkbox/button/hidden/password/number/
 * date/radio), optional `show_if` expression, `fields` for nested sets, and
 * `repeat: true` for row-style sets whose children can be duplicated.
 */
(function (global) {
  "use strict";

  const SAMPLE_BIND = {
    TABLES: ["Sample Table A", "Sample Table B", "Sample Table C"],
    COLUMNS: ["Column 1", "Column 2", "Column 3", "Column 4"],
    TAGS: ["tag-red", "tag-blue", "tag-green"],
    SCRIPTS: ["Script 1", "Script 2"],
  };

  // ---------------- expression engine ----------------

  function tokenize(src) {
    const tokens = [];
    let i = 0;
    while (i < src.length) {
      const ch = src[i];
      if (/\s/.test(ch)) {
        let j = i;
        while (j < src.length && /\s/.test(src[j])) j++;
        tokens.push({ kind: "ws", raw: src.slice(i, j) });
        i = j;
        continue;
      }
      if (ch === "'" || ch === '"') {
        let j = i + 1;
        while (j < src.length && src[j] !== ch) {
          if (src[j] === "\\") j++;
          j++;
        }
        tokens.push({ kind: "str", raw: src.slice(i, j + 1) });
        i = j + 1;
        continue;
      }
      if (/[a-zA-Z_$]/.test(ch)) {
        let j = i;
        while (j < src.length && /[a-zA-Z0-9_.$]/.test(src[j])) j++;
        tokens.push({ kind: "ident", raw: src.slice(i, j) });
        i = j;
        continue;
      }
      if (/[0-9]/.test(ch)) {
        let j = i;
        while (j < src.length && /[0-9.]/.test(src[j])) j++;
        tokens.push({ kind: "num", raw: src.slice(i, j) });
        i = j;
        continue;
      }
      const two = src.slice(i, i + 2);
      if (["==", "!=", "&&", "||", "<=", ">="].includes(two)) {
        tokens.push({ kind: "op", raw: two });
        i += 2;
        continue;
      }
      tokens.push({ kind: "op", raw: ch });
      i++;
    }
    return tokens;
  }

  const RESERVED = new Set([
    "true",
    "false",
    "null",
    "undefined",
  ]);

  function compileShowIf(expr) {
    if (expr === undefined || expr === null) return null;
    if (typeof expr !== "string") return () => !!expr;
    const trimmed = expr.trim();
    if (trimmed === "") return null;
    if (trimmed === "true") return () => true;
    if (trimmed === "false") return () => false;

    const tokens = tokenize(trimmed);
    const pieces = tokens.map((t) => {
      if (t.kind !== "ident") return t.raw;
      const name = t.raw;
      if (RESERVED.has(name)) return name;
      if (name === "$index") return "_index";
      if (name.startsWith("this.")) {
        return "_row(" + JSON.stringify(name.slice(5)) + ")";
      }
      return "_get(" + JSON.stringify(name) + ")";
    });
    const body = "return (" + pieces.join("") + ");";
    try {
      // eslint-disable-next-line no-new-func
      return new Function("_get", "_row", "_index", body);
    } catch (err) {
      console.warn("Failed to compile show_if:", expr, err);
      return () => true;
    }
  }

  // ---------------- runtime state ----------------

  function createState() {
    return {
      form: Object.create(null),
      bindings: [],
    };
  }

  function getter(state) {
    return function (key) {
      const v = state.form[key];
      return v === undefined ? "" : v;
    };
  }

  function refreshAll(state) {
    const get = getter(state);
    for (const b of state.bindings) {
      if (!b.element.isConnected) continue;
      let visible = true;
      try {
        visible = !!b.fn(
          get,
          (k) => (b.rowData ? (b.rowData[k] === undefined ? "" : b.rowData[k]) : ""),
          b.rowIndex
        );
      } catch (err) {
        console.warn("show_if failed:", b.expr, err);
      }
      b.element.classList.toggle("hidden", !visible);
    }
  }

  function setValue(state, key, value) {
    state.form[key] = value;
    refreshAll(state);
  }

  function registerShowIf(state, element, expr, rowData, rowIndex) {
    if (!expr) return;
    const fn = compileShowIf(expr);
    if (!fn) return;
    state.bindings.push({ element, fn, expr, rowData, rowIndex });
  }

  // ---------------- DOM helpers ----------------

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === "class") node.className = attrs[k];
        else if (k === "style") node.setAttribute("style", attrs[k]);
        else if (k === "text") node.textContent = attrs[k];
        else if (k === "html") node.innerHTML = attrs[k];
        else if (attrs[k] === true) node.setAttribute(k, "");
        else if (attrs[k] !== false && attrs[k] !== undefined && attrs[k] !== null)
          node.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (const c of children) {
        if (c === null || c === undefined) continue;
        node.appendChild(c);
      }
    }
    return node;
  }

  function labelWrap(def, control) {
    const wrap = el("div", { class: "field field--" + (def.type || "text") });
    if (def.style) wrap.setAttribute("style", def.style);
    if (def.label) {
      const lab = el("label", { class: "field__label", text: def.label });
      wrap.appendChild(lab);
    }
    wrap.appendChild(control);
    if (def.breakLine) wrap.classList.add("break-line");
    return wrap;
  }

  // ---------------- renderers ----------------

  function renderTopLevel(name, def, state) {
    return renderFieldset(name, def, state, { rowData: null, rowIndex: null });
  }

  function renderFieldset(name, def, state, ctx) {
    const legend = def.label ? el("legend", { text: def.label }) : null;
    const body = el("div", { class: "fieldset__body" });
    const wrap = el("fieldset", { class: "fieldset" }, [legend, body].filter(Boolean));
    if (def.style) wrap.setAttribute("style", def.style);
    if (!def.label) wrap.classList.add("fieldset--unlabeled");

    if (def.repeat) {
      const rows = el("div", { class: "repeat__rows" });
      body.appendChild(rows);
      const add = el("button", {
        type: "button",
        class: "repeat__add",
        text: "+ Add row",
      });
      add.addEventListener("click", () => appendRow(def, rows, state, 0));
      body.appendChild(add);
      appendRow(def, rows, state, 0);
    } else {
      if (def.fields) {
        for (const childKey in def.fields) {
          const child = renderField(childKey, def.fields[childKey], state, ctx);
          if (child) body.appendChild(child);
        }
      }
    }

    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function appendRow(def, container, state, _ignored) {
    const rowData = Object.create(null);
    const index = container.children.length;
    const row = el("div", { class: "repeat__row" });
    row.dataset.index = index;
    if (def.fields) {
      for (const childKey in def.fields) {
        const child = renderField(childKey, def.fields[childKey], state, {
          rowData,
          rowIndex: index,
          row,
        });
        if (child) row.appendChild(child);
      }
    }
    container.appendChild(row);
    refreshAll(state);
  }

  function renderField(name, def, state, ctx) {
    const type = def.type || "text";
    switch (type) {
      case "fieldset":
        return renderFieldset(name, def, state, ctx);
      case "select":
        return renderSelect(name, def, state, ctx);
      case "text":
      case "password":
        return renderText(name, def, state, ctx);
      case "textarea":
        return renderTextarea(name, def, state, ctx);
      case "checkbox":
        return renderCheckbox(name, def, state, ctx);
      case "number":
        return renderNumber(name, def, state, ctx);
      case "date":
        return renderDate(name, def, state, ctx);
      case "radio":
        return renderRadio(name, def, state, ctx);
      case "button":
        return renderButton(name, def, state, ctx);
      case "hidden":
        return renderHidden(name, def, state, ctx);
      case "debug":
        return null;
      default:
        return renderText(name, def, state, ctx);
    }
  }

  function optionEntries(def) {
    if (def.options && typeof def.options === "object") {
      return Object.entries(def.options).map(([val, meta]) => [
        val,
        meta && meta.label ? meta.label : val,
      ]);
    }
    if (Array.isArray(def.values)) {
      return def.values.map((v) => [String(v), String(v)]);
    }
    if (def.bind && SAMPLE_BIND[def.bind]) {
      return SAMPLE_BIND[def.bind].map((v) => [v, v]);
    }
    if (def.bind) {
      return [["", "[" + def.bind + "]"]];
    }
    return [];
  }

  function initialValue(def) {
    if (def.val !== undefined && def.val !== null) return def.val;
    if (def.values && def.values.length) return def.values[0];
    return "";
  }

  function storeValue(state, ctx, name, value) {
    if (ctx.rowData) ctx.rowData[name] = value;
    else state.form[name] = value;
  }

  function renderSelect(name, def, state, ctx) {
    const sel = el("select", {
      class: "field__control field__select",
      name,
      multiple: !!def.multiple,
    });
    if (def.empty !== undefined) {
      sel.appendChild(el("option", { value: "", text: def.empty || "" }));
    }
    const entries = optionEntries(def);
    let val = initialValue(def);
    if (def.multiple && !Array.isArray(val)) val = val ? [val] : [];
    for (const [v, label] of entries) {
      const opt = el("option", { value: v, text: label });
      const match = def.multiple
        ? Array.isArray(val) && val.includes(v)
        : String(val) === String(v);
      if (match) opt.setAttribute("selected", "");
      sel.appendChild(opt);
    }
    storeValue(state, ctx, name, def.multiple ? val : val);
    sel.addEventListener("change", () => {
      const v = def.multiple
        ? Array.from(sel.selectedOptions).map((o) => o.value)
        : sel.value;
      storeValue(state, ctx, name, v);
      refreshAll(state);
    });
    const wrap = labelWrap(def, sel);
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderText(name, def, state, ctx) {
    const input = el("input", {
      class: "field__control field__text",
      type: def.type === "password" ? "password" : "text",
      name,
      value: initialValue(def),
      placeholder: def.placeholder || "",
      minlength: def.minLength,
      maxlength: def.maxLength,
      required: !!def.required,
    });
    if (def.width) input.style.width = def.width;
    storeValue(state, ctx, name, initialValue(def));
    input.addEventListener("input", () => {
      storeValue(state, ctx, name, input.value);
      refreshAll(state);
    });
    const wrap = labelWrap(def, input);
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderTextarea(name, def, state, ctx) {
    const area = el("textarea", {
      class: "field__control field__textarea",
      name,
      rows: def.rows || 3,
      placeholder: def.placeholder || "",
      required: !!def.required,
    });
    area.value = initialValue(def);
    storeValue(state, ctx, name, initialValue(def));
    area.addEventListener("input", () => {
      storeValue(state, ctx, name, area.value);
      refreshAll(state);
    });
    const wrap = labelWrap(def, area);
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderCheckbox(name, def, state, ctx) {
    const on = def.isOn !== undefined ? def.isOn : "true";
    const off = def.isOff !== undefined ? def.isOff : "false";
    const initial = def.val !== undefined ? def.val : off;
    const input = el("input", {
      class: "field__control field__checkbox",
      type: "checkbox",
      name,
    });
    if (String(initial) === String(on)) input.setAttribute("checked", "");
    storeValue(state, ctx, name, initial);
    input.addEventListener("change", () => {
      const v = input.checked ? on : off;
      storeValue(state, ctx, name, v);
      refreshAll(state);
    });
    const wrap = el("div", { class: "field field--checkbox" });
    if (def.style) wrap.setAttribute("style", def.style);
    const lab = el("label", { class: "field__label field__label--inline" });
    lab.appendChild(input);
    lab.appendChild(document.createTextNode(" " + (def.label || name)));
    wrap.appendChild(lab);
    if (def.breakLine) wrap.classList.add("break-line");
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderNumber(name, def, state, ctx) {
    const input = el("input", {
      class: "field__control field__number",
      type: "number",
      name,
      value: initialValue(def),
      min: def.minVal,
      max: def.maxVal,
      required: !!def.required,
    });
    storeValue(state, ctx, name, initialValue(def));
    input.addEventListener("input", () => {
      storeValue(state, ctx, name, input.value);
      refreshAll(state);
    });
    const wrap = labelWrap(def, input);
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderDate(name, def, state, ctx) {
    const input = el("input", {
      class: "field__control field__date",
      type: "date",
      name,
      value: initialValue(def),
      required: !!def.required,
    });
    storeValue(state, ctx, name, initialValue(def));
    input.addEventListener("input", () => {
      storeValue(state, ctx, name, input.value);
      refreshAll(state);
    });
    const wrap = labelWrap(def, input);
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderRadio(name, def, state, ctx) {
    const wrap = el("div", { class: "field field--radio" });
    if (def.label)
      wrap.appendChild(el("div", { class: "field__label", text: def.label }));
    const entries = optionEntries(def);
    const initial = initialValue(def);
    storeValue(state, ctx, name, initial);
    for (const [v, label] of entries) {
      const id = `${name}-${v}`.replace(/[^a-zA-Z0-9_-]/g, "_");
      const input = el("input", {
        type: "radio",
        id,
        name,
        value: v,
      });
      if (String(initial) === String(v)) input.setAttribute("checked", "");
      input.addEventListener("change", () => {
        if (input.checked) {
          storeValue(state, ctx, name, v);
          refreshAll(state);
        }
      });
      const lab = el("label", { class: "field__label--inline", for: id });
      lab.appendChild(input);
      lab.appendChild(document.createTextNode(" " + label));
      wrap.appendChild(lab);
    }
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderButton(name, def, state, ctx) {
    const btn = el("button", {
      type: "button",
      class: "field__control field__button",
      text: def.label || name,
    });
    if (def.function === "DELETE_ROW") {
      btn.classList.add("field__button--delete");
      btn.addEventListener("click", () => {
        const row = ctx.row || btn.closest(".repeat__row");
        if (!row) return;
        const parent = row.parentElement;
        row.remove();
        Array.from(parent.children).forEach((r, i) => (r.dataset.index = i));
        refreshAll(state);
      });
    }
    const wrap = el("div", { class: "field field--button" });
    if (def.style) wrap.setAttribute("style", def.style);
    wrap.appendChild(btn);
    if (def.breakLine) wrap.classList.add("break-line");
    registerShowIf(state, wrap, def.show_if, ctx.rowData, ctx.rowIndex);
    return wrap;
  }

  function renderHidden(name, def, state, ctx) {
    storeValue(state, ctx, name, initialValue(def));
    return null;
  }

  // ---------------- public ----------------

  function render(taskInfo, root) {
    root.innerHTML = "";
    const state = createState();
    const menu = (taskInfo && taskInfo.menu) || [];
    for (const item of menu) {
      for (const key in item) {
        const node = renderTopLevel(key, item[key], state);
        if (node) root.appendChild(node);
      }
    }
    refreshAll(state);
    return state;
  }

  global.MenuRender = { render };
})(typeof window !== "undefined" ? window : this);
