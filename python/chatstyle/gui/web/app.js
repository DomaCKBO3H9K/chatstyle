"use strict";

// Окно ничего не считает: оно вызывает методы Python (window.pywebview.api) и рисует ответ.
// Любой текст из файлов вставляется только через textContent, чужое имя не станет разметкой.
// Все фразы идут через t() из i18n.js; Python присылает коды с параметрами.

const $ = (id) => document.getElementById(id);
const state = {
  unknown: null,
  candidates: [],
  profile: null,
  busy: null, // null | "compare" | "profile"
  errors: null, // список ошибок {code, params} или null
  result: null,
  profileView: null,
  animate: false,
  tg: { step: "logged_out", name: null, has_keys: true },
};

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) node.append(child);
  return node;
}

const api = () => window.pywebview.api;

// Вызов метода Python: сбой самого вызова превращается в ошибку для показа, а не в тишину.
async function call(method, ...args) {
  try {
    return await api()[method](...args);
  } catch (exception) {
    showErrors([{ code: "unexpected", params: { message: String(exception && exception.message || exception) } }]);
    return null;
  }
}

// --- тема и язык: по умолчанию как в системе, выбор запоминается ---

const THEME_KEY = "chatstyle-theme";
const LANGUAGE_KEY = "chatstyle-language";

function readSaved(key) {
  try {
    return localStorage.getItem(key);
  } catch (error) {
    return null; // хранилище может быть недоступно: тогда работаем по системным настройкам
  }
}

function writeSaved(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    // выбор действует до закрытия окна
  }
}

function systemIsDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function currentTheme() {
  return document.documentElement.dataset.theme || (systemIsDark() ? "dark" : "light");
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme").textContent = t(theme === "dark" ? "theme.to_light" : "theme.to_dark");
}

function initTheme() {
  const saved = readSaved(THEME_KEY);
  applyTheme(saved === "dark" || saved === "light" ? saved : currentTheme());
  $("theme").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    writeSaved(THEME_KEY, next);
  });
}

function initLanguage() {
  const select = $("lang");
  select.replaceChildren(...LANGUAGES.map((language) => el("option", { value: language.code, text: language.name })));
  const saved = readSaved(LANGUAGE_KEY);
  const code = languageByCode(saved) ? saved : detectLanguage();
  select.value = code;
  setLanguage(code);
  select.addEventListener("change", () => {
    setLanguage(select.value);
    writeSaved(LANGUAGE_KEY, select.value);
    refreshAll();
  });
}

// --- вкладки ---

function selectTab(name) {
  for (const id of ["compare", "profile"]) {
    $(`tab-${id}`).setAttribute("aria-selected", String(id === name));
    $(`view-${id}`).hidden = id !== name;
  }
}

// --- выбор источников ---

function showSource(boxId, nameId, source) {
  $(boxId).classList.toggle("filled", Boolean(source));
  const label = $(nameId);
  label.textContent = source ? source.label : t("source.none");
  if (source) label.append(" ", el("small", { text: t("source.selected") }));
}

async function chooseFile() {
  return call("pick_file");
}

async function chooseTelegram() {
  const picked = await call("pick_tg_export");
  if (!picked) return null;
  if (picked.error) {
    showErrors([picked.error]);
    return null;
  }
  const key = await askSender(picked.senders);
  if (key === null) return null;
  const source = await call("tg_source", picked.path, key);
  if (source && source.error) {
    showErrors([source.error]);
    return null;
  }
  return source;
}

// Источник напрямую из Telegram: нужен вход, иначе открывается окно подключения.
async function chooseTelegramLive() {
  if (state.tg.step !== "logged_in") {
    openTelegramDialog();
    return null;
  }
  const dialog = $("tgsrc");
  $("tgsrc-chat").value = "";
  $("tgsrc-sender").value = "";
  return new Promise((resolve) => {
    let answer = null;
    const add = () => {
      const chat = $("tgsrc-chat").value.trim();
      const sender = $("tgsrc-sender").value.trim();
      if (!chat) return;
      answer = {
        spec: sender ? `tg:${chat}#${sender}` : `tg:${chat}`,
        label: sender ? `${chat} › ${sender}` : chat,
      };
      dialog.close();
    };
    $("tgsrc-add").onclick = add;
    $("tgsrc-cancel").onclick = () => dialog.close();
    dialog.addEventListener("close", () => resolve(answer), { once: true });
    dialog.showModal();
  });
}

function askSender(senders) {
  const dialog = $("senders");
  const list = $("senders-list");
  list.replaceChildren();
  return new Promise((resolve) => {
    let answer = null;
    for (const sender of senders) {
      const button = el("button", {}, [
        el("span", { text: sender.name, dir: "auto" }),
        el("small", { text: t("senders.count", { n: sender.messages }) }),
      ]);
      button.addEventListener("click", () => {
        answer = sender.key;
        dialog.close();
      });
      list.append(el("li", {}, button));
    }
    dialog.addEventListener("close", () => resolve(answer), { once: true });
    dialog.showModal();
  });
}

// --- состояние формы и подписи, зависящие от языка ---

function refreshCompare() {
  showSource("unknown-box", "unknown-name", state.unknown);
  showSource("profile-box", "profile-name", state.profile);
  const chips = $("chips");
  chips.replaceChildren(
    ...state.candidates.map((candidate, index) => {
      const remove = el("button", { class: "x", "aria-label": t("btn.remove", { name: candidate.label }), text: "×" });
      remove.addEventListener("click", () => {
        state.candidates.splice(index, 1);
        refreshCompare();
      });
      remove.disabled = Boolean(state.busy);
      return el("li", {}, [el("span", { text: candidate.label, title: candidate.label, dir: "auto" }), remove]);
    })
  );
  const busy = Boolean(state.busy);
  const ready = Boolean(state.unknown) && state.candidates.length > 0 && !busy;
  $("go").disabled = !ready;
  $("go").classList.toggle("busy", state.busy === "compare");
  $("go-text").textContent = t(state.busy === "compare" ? "go.busy" : "go.compare");
  $("go-hint").hidden = ready || busy;
  $("go-hint").textContent = t(state.unknown ? "hint.need_candidate" : "hint.need_unknown");
  $("go-profile").disabled = !state.profile || busy;
  $("go-profile").classList.toggle("busy", state.busy === "profile");
  $("go-profile-text").textContent = t(state.busy === "profile" ? "go.busy" : "go.profile");
  for (const control of document.querySelectorAll("main .btn, main input")) control.disabled = busy;
  $("theme").textContent = t(currentTheme() === "dark" ? "theme.to_light" : "theme.to_dark");
  refreshTelegramChip();
}

// --- ошибки ---

function showErrors(errors) {
  state.errors = errors;
  renderPanels();
}

function clearErrors() {
  state.errors = null;
  renderPanels();
}

function errorBox(errors) {
  return [
    el("strong", { text: t("error.title") }),
    ...errors.map((item) => el("div", { text: translateError(item), dir: "auto" })),
  ];
}

// Какая из трёх картин видна в каждой панели: ошибка, результат или подсказка.
function renderPanels() {
  for (const [prefix, view, render] of [
    ["", state.result, renderResult],
    ["profile-", state.profileView, renderProfile],
  ]) {
    const empty = $(`${prefix}empty`);
    const box = $(`${prefix}error`);
    const out = $(`${prefix}out`);
    empty.hidden = Boolean(state.errors) || Boolean(view);
    box.hidden = !state.errors;
    out.hidden = Boolean(state.errors) || !view;
    if (state.errors) box.replaceChildren(...errorBox(state.errors));
    else if (view) render(view, out);
  }
  state.animate = false;
}

// --- запуск и опрос ---

async function launch(kind, payload) {
  clearErrors();
  const answer = await call(kind === "profile" ? "start_profile" : "start_compare", payload);
  if (!answer) return;
  if (!answer.ok) {
    showErrors(answer.errors);
    return;
  }
  state.busy = kind;
  refreshCompare();
  const timer = setInterval(async () => {
    const status = await call("poll");
    if (status && status.state === "running") return;
    clearInterval(timer);
    state.busy = null;
    refreshCompare();
    if (!status) return;
    if (status.state === "error") {
      showErrors([status.error]);
    } else if (kind === "profile") {
      state.profileView = status.view;
      state.animate = true;
      renderPanels();
    } else {
      state.result = status.view;
      state.animate = true;
      renderPanels();
    }
  }, 150);
}

function compareForm() {
  return {
    unknown: state.unknown.spec,
    candidates: state.candidates.map((candidate) => candidate.spec),
    impostors_dir: $("impostors").value.trim(),
    seed: $("seed").value.trim(),
    report_path: $("save-report").checked ? $("report").value.trim() : "",
    limit: $("limit").value.trim(),
    refresh: $("refresh").checked,
  };
}

// --- результат ---

function noteText(note) {
  if (note.code === "ranking") return t(`note.ranking.${note.method}`);
  if (note.code === "best_methods") {
    const parts = note.parts
      .map((part) => t("note.part", { method: t(`method.${part.method}`), labels: part.labels.join(", ") }))
      .join("; ");
    return t("note.best_methods", { parts, verdict: t(note.agree ? "note.agree" : "note.disagree") });
  }
  return t(`note.${note.code}`, { ...note, labels: note.labels.join(", ") });
}

function warningText(warning) {
  const sides = warning.sides
    .map((side) =>
      side.who === null
        ? t("warning.unknown", { words: side.words })
        : t("warning.candidate", { label: side.who, words: side.words })
    )
    .join("; ");
  return t("warning.low_volume", { min: warning.min, sides });
}

function renderResult(view, out) {
  const top = view.candidates[0];
  const children = [
    el("h1", { class: "verdict" }, tNodes("result.verdict", { name: el("mark", { text: top.label, dir: "auto" }) })),
    el("p", { class: "sub", text: t(`result.summary.${view.metric}`) }),
  ];
  view.candidates.forEach((candidate, index) => {
    const fill = el("div", { class: "fill" });
    fill.dataset.width = String(Math.round(candidate.value * 100));
    if (!state.animate) fill.style.width = `${fill.dataset.width}%`;
    const block = el("div", { class: index === 0 ? "cand top" : "cand" }, [
      el("div", { class: "cand-head" }, [
        el("span", { class: "name", text: candidate.label, dir: "auto" }),
        el("span", { class: "size", text: t("result.counts", candidate) }),
        el("span", { class: "score", text: candidate.value_text }),
      ]),
      el(
        "div",
        { class: "track", role: "img", "aria-label": t("result.track", { metric: t(`metric.${view.metric}`), value: candidate.value_text }) },
        fill
      ),
    ]);
    if (index === 0 && candidate.why.length) {
      block.append(
        el("div", { class: "why" }, [
          t("result.why"),
          ...candidate.why.map((feature) => el("mark", { text: feature, dir: "auto" })),
        ])
      );
    }
    block.append(
      el("div", { class: "methods" }, [
        el("span", {}, [`${t("result.cosine")} `, el("b", { text: candidate.cosine })]),
        el("span", {}, [`${t("result.delta")} `, el("b", { text: candidate.delta })]),
        el("span", {}, [`${t("result.final")} `, el("b", { text: candidate.final })]),
      ])
    );
    children.push(block);
  });
  if (view.notes.length) {
    children.push(el("ul", { class: "notes" }, view.notes.map((note) => el("li", { text: noteText(note), dir: "auto" }))));
  }
  if (view.warning) children.push(el("div", { class: "warn", text: warningText(view.warning), dir: "auto" }));
  const actions = el("div", { class: "actions" });
  if (view.report_path) {
    const open = el("button", { class: "btn", text: t("btn.open_report") });
    open.addEventListener("click", async () => {
      const answer = await call("open_report", view.report_path);
      if (answer && answer.error) showErrors([answer.error]);
    });
    actions.append(open, el("span", { class: "size path", text: view.report_path }));
  }
  children.push(actions);
  out.replaceChildren(...children);
  if (state.animate) {
    const grow = () => out.querySelectorAll(".fill").forEach((f) => (f.style.width = `${f.dataset.width}%`));
    requestAnimationFrame(() => requestAnimationFrame(grow));
  }
}

function renderProfile(view, out) {
  out.replaceChildren(
    el("h1", { class: "verdict compact", text: t("profile.header", view), dir: "auto" }),
    el(
      "div",
      { class: "features" },
      view.features.map((item) =>
        el("div", { class: "feature" }, [
          el("div", { class: "value", text: item.value }),
          el("div", { class: "name", text: t(`feature.${item.key}`) }),
        ])
      )
    ),
    el(
      "div",
      { class: "words" },
      view.word_lists.map((group) =>
        el("p", {
          dir: "auto",
          text: t("list.format", {
            title: t(`profile.${group.kind}`),
            items: group.items.length ? group.items.map((item) => `${item.word} ${item.value}`).join(", ") : t("profile.none"),
          }),
        })
      )
    )
  );
}

// --- Telegram: подключение по шагам. Код и пароли нигде не сохраняются, поля очищаются сразу ---

const tgUi = { busy: false, error: null, notice: null, changingKeys: false };

function refreshTelegramChip() {
  const connected = state.tg.step === "logged_in";
  $("tg-chip").textContent = connected ? t("tg.chip.on", { name: state.tg.name || "" }) : t("tg.chip.off");
  $("tg-chip").classList.toggle("on", connected);
}

async function loadTelegramStatus() {
  const status = await call("telegram_status");
  if (status) state.tg = status;
  refreshTelegramChip();
}

function tgStep() {
  if (state.tg.step === "logged_in") return "done";
  if (state.tg.step === "need_code") return "code";
  if (state.tg.step === "need_password") return "password";
  return state.tg.has_keys && !tgUi.changingKeys ? "phone" : "keys";
}

function tgField(id, labelKey, options = {}) {
  const input = el("input", {
    type: options.type || "text",
    id,
    autocomplete: "off",
    spellcheck: "false",
    ...(options.inputmode ? { inputmode: options.inputmode } : {}),
    ...(options.placeholderKey ? { placeholder: t(options.placeholderKey) } : {}),
  });
  input.disabled = tgUi.busy;
  return el("label", { class: "field" }, [el("span", { class: "label", text: t(labelKey) }), input]);
}

function tgButton(textKey, handler, primary = false) {
  const button = el("button", { class: primary ? "btn primary" : "btn", type: "button", text: t(textKey) });
  button.disabled = tgUi.busy;
  button.addEventListener("click", handler);
  return button;
}

// Прочитать поле и сразу очистить его: секреты не остаются на странице.
function takeValue(id) {
  const input = $(id);
  const value = input.value;
  input.value = "";
  return value;
}

async function tgRun(method, ...args) {
  tgUi.busy = true;
  tgUi.error = null;
  tgUi.notice = null;
  renderTelegramDialog();
  const answer = await call(method, ...args);
  tgUi.busy = false;
  if (answer && answer.ok) {
    state.tg = answer.state;
    tgUi.changingKeys = false;
    if (answer.state.remote_failed) tgUi.notice = "tg.logout_remote_failed";
  } else if (answer && answer.error) {
    tgUi.error = answer.error;
    const status = await call("telegram_status");
    if (status) state.tg = status;
  }
  refreshTelegramChip();
  renderTelegramDialog();
}

function renderTelegramDialog() {
  const step = tgStep();
  const body = [];
  if (step === "keys") {
    body.push(
      el("p", { class: "tg-note", text: t("tg.keys.intro") }),
      tgButton("tg.keys.open_site", () => call("telegram_open_site")),
      tgField("tg-api-id", "tg.keys.api_id", { inputmode: "numeric" }),
      tgField("tg-api-hash", "tg.keys.api_hash", { type: "password" }),
      el("p", { class: "tg-note", text: t("tg.keys.note") }),
      tgButton("tg.keys.save", () => tgRun("telegram_save_keys", takeValue("tg-api-id"), takeValue("tg-api-hash")), true)
    );
  } else if (step === "phone") {
    body.push(
      tgField("tg-phone", "tg.phone.label", { inputmode: "tel", placeholderKey: "tg.phone.placeholder" }),
      el("p", { class: "tg-note", text: t("tg.phone.note") }),
      el("div", { class: "row" }, [
        tgButton("tg.phone.send", () => tgRun("telegram_begin", $("tg-phone").value), true),
        tgButton("tg.keys.change", () => {
          tgUi.changingKeys = true;
          renderTelegramDialog();
        }),
      ])
    );
  } else if (step === "code") {
    body.push(
      tgField("tg-code", "tg.code.label", { inputmode: "numeric" }),
      el("p", { class: "tg-note", text: t("tg.code.note") }),
      el("div", { class: "row" }, [
        tgButton("tg.code.send", () => tgRun("telegram_code", takeValue("tg-code")), true),
        tgButton("tg.cancel", () => tgRun("telegram_cancel")),
      ])
    );
  } else if (step === "password") {
    body.push(
      tgField("tg-password", "tg.password.label", { type: "password" }),
      el("div", { class: "row" }, [
        tgButton("tg.password.send", () => tgRun("telegram_password", takeValue("tg-password")), true),
        tgButton("tg.cancel", () => tgRun("telegram_cancel")),
      ])
    );
  } else {
    body.push(
      el("p", { class: "tg-ok", text: t("tg.done", { name: state.tg.name || "" }), dir: "auto" }),
      tgButton("tg.logout", () => tgRun("telegram_logout"))
    );
  }
  if (tgUi.busy) body.push(el("p", { class: "tg-note", text: t("tg.busy") }));
  if (tgUi.notice) body.push(el("p", { class: "warn", text: t(tgUi.notice) }));
  if (tgUi.error) {
    body.unshift(el("div", { class: "error", role: "alert" }, [el("div", { text: translateError(tgUi.error), dir: "auto" })]));
  }
  $("tg-body").replaceChildren(...body);
  const first = $("tg-body").querySelector("input");
  if (first && $("tg").open && !tgUi.busy) first.focus();
}

function openTelegramDialog() {
  tgUi.error = null;
  tgUi.notice = null;
  tgUi.changingKeys = false;
  renderTelegramDialog();
  if (!$("tg").open) $("tg").showModal();
}

// --- перерисовка при смене языка ---

function refreshAll() {
  refreshCompare();
  renderPanels();
  if ($("tg").open) renderTelegramDialog();
}

// --- запуск окна ---

function bind() {
  $("tab-compare").addEventListener("click", () => selectTab("compare"));
  $("tab-profile").addEventListener("click", () => selectTab("profile"));

  $("unknown-file").addEventListener("click", async () => {
    state.unknown = (await chooseFile()) || state.unknown;
    refreshCompare();
  });
  $("unknown-tg").addEventListener("click", async () => {
    state.unknown = (await chooseTelegram()) || state.unknown;
    refreshCompare();
  });
  const addCandidate = async (picker) => {
    const picked = await picker();
    if (picked && !state.candidates.some((c) => c.spec === picked.spec)) state.candidates.push(picked);
    refreshCompare();
  };
  $("add-file").addEventListener("click", () => addCandidate(chooseFile));
  $("add-tg").addEventListener("click", () => addCandidate(chooseTelegram));

  $("impostors-pick").addEventListener("click", async () => {
    const folder = await call("pick_folder");
    if (folder) $("impostors").value = folder;
  });
  $("save-report").addEventListener("change", () => {
    $("report-row").hidden = !$("save-report").checked;
  });
  $("report-pick").addEventListener("click", async () => {
    const path = await call("pick_report_path");
    if (path) $("report").value = path;
  });
  $("go").addEventListener("click", () => launch("compare", compareForm()));
  $("unknown-tg-live").addEventListener("click", async () => {
    state.unknown = (await chooseTelegramLive()) || state.unknown;
    refreshCompare();
  });
  $("add-tg-live").addEventListener("click", () => addCandidate(chooseTelegramLive));
  $("profile-tg-live").addEventListener("click", async () => {
    state.profile = (await chooseTelegramLive()) || state.profile;
    refreshCompare();
  });
  $("tg-chip").addEventListener("click", openTelegramDialog);
  $("tg-close").addEventListener("click", () => $("tg").close());

  $("profile-file").addEventListener("click", async () => {
    state.profile = (await chooseFile()) || state.profile;
    refreshCompare();
  });
  $("profile-tg").addEventListener("click", async () => {
    state.profile = (await chooseTelegram()) || state.profile;
    refreshCompare();
  });
  $("go-profile").addEventListener("click", () => launch("profile", state.profile.spec));
  $("senders-cancel").addEventListener("click", () => $("senders").close());
}

// Язык нужен до первого показа текстов: страница по умолчанию показывает подписи сразу после загрузки,
// а методы Python становятся доступны позже, по событию pywebviewready.
initLanguage();
initTheme();
bind();
refreshAll();
// Методы Python доступны после события pywebviewready; в простом браузере (макет) их может не быть.
if (window.pywebview && window.pywebview.api) loadTelegramStatus();
else window.addEventListener("pywebviewready", loadTelegramStatus, { once: true });
