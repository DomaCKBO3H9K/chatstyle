"use strict";

// Окно ничего не считает: оно вызывает методы Python (window.pywebview.api) и рисует ответ.
// Любой текст из файлов вставляется только через textContent, чужое имя не станет разметкой.

const $ = (id) => document.getElementById(id);
const state = { unknown: null, candidates: [], profile: null, busy: false };

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

// --- тема: по умолчанию как в системе, кнопка в шапке переключает и запоминает выбор ---

const THEME_KEY = "chatstyle-theme";

function systemIsDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function currentTheme() {
  return document.documentElement.dataset.theme || (systemIsDark() ? "dark" : "light");
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme").textContent = theme === "dark" ? "Светлая тема" : "Тёмная тема";
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch (error) {
    saved = null; // хранилище может быть недоступно: тогда работаем по системной теме
  }
  applyTheme(saved === "dark" || saved === "light" ? saved : currentTheme());
  $("theme").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (error) {
      // выбор действует до закрытия окна
    }
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
  label.textContent = source ? source.label : "Файл ещё не выбран";
  if (source) label.append(" ", el("small", { text: "выбрано" }));
}

async function chooseFile() {
  return api().pick_file();
}

async function chooseTelegram() {
  const picked = await api().pick_tg_export();
  if (!picked) return null;
  if (picked.error) {
    showError(picked.error);
    return null;
  }
  const key = await askSender(picked.senders);
  return key === null ? null : api().tg_source(picked.path, key);
}

function askSender(senders) {
  const dialog = $("senders");
  const list = $("senders-list");
  list.replaceChildren();
  return new Promise((resolve) => {
    let answer = null;
    for (const sender of senders) {
      const button = el("button", {}, [
        el("span", { text: sender.name }),
        el("small", { text: `${sender.messages} сообщ.` }),
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

function refreshCompare() {
  showSource("unknown-box", "unknown-name", state.unknown);
  const chips = $("chips");
  chips.replaceChildren(
    ...state.candidates.map((candidate, index) => {
      const remove = el("button", { class: "x", "aria-label": `Убрать ${candidate.label}`, text: "×" });
      remove.addEventListener("click", () => {
        state.candidates.splice(index, 1);
        refreshCompare();
      });
      return el("li", {}, [el("span", { text: candidate.label, title: candidate.label }), remove]);
    })
  );
  const ready = Boolean(state.unknown) && state.candidates.length > 0 && !state.busy;
  $("go").disabled = !ready;
  $("go-hint").hidden = ready || state.busy;
  $("go-hint").textContent = !state.unknown
    ? "Сначала выберите сообщения, которые нужно проверить."
    : "Добавьте хотя бы одного кандидата.";
  $("go-profile").disabled = !state.profile || state.busy;
}

// --- ошибки и занятость ---

function showError(text) {
  for (const id of ["error", "profile-error"]) {
    const box = $(id);
    box.replaceChildren(el("strong", { text: "Не получилось" }), text);
    box.hidden = false;
  }
  for (const id of ["empty", "out", "profile-empty", "profile-out"]) $(id).hidden = true;
}

function clearError() {
  $("error").hidden = true;
  $("profile-error").hidden = true;
}

function setBusy(busy, kind) {
  state.busy = busy;
  const button = kind === "profile" ? $("go-profile") : $("go");
  const text = kind === "profile" ? $("go-profile-text") : $("go-text");
  button.classList.toggle("busy", busy);
  text.textContent = busy ? "Считаем…" : kind === "profile" ? "Показать профиль" : "Сравнить";
  for (const control of document.querySelectorAll("main .btn, main input, .chips .x")) control.disabled = busy;
  refreshCompare();
}

// --- запуск и опрос ---

async function launch(kind, payload) {
  clearError();
  const answer = kind === "profile" ? await api().start_profile(payload) : await api().start_compare(payload);
  if (!answer.ok) {
    showError(answer.errors.join("\n"));
    return;
  }
  setBusy(true, kind);
  const timer = setInterval(async () => {
    const status = await api().poll();
    if (status.state === "running") return;
    clearInterval(timer);
    setBusy(false, kind);
    if (status.state === "error") showError(status.message);
    else if (kind === "profile") renderProfile(status.view);
    else renderResult(status.view);
  }, 150);
}

function compareForm() {
  const seedText = $("seed").value.trim();
  return {
    unknown: state.unknown.spec,
    candidates: state.candidates.map((candidate) => candidate.spec),
    impostors_dir: $("impostors").value.trim(),
    seed: seedText,
    report_path: $("save-report").checked ? $("report").value.trim() : "",
  };
}

// --- результат ---

function renderResult(view) {
  $("empty").hidden = true;
  const out = $("out");
  out.hidden = false;
  const top = view.candidates[0];
  const children = [
    el("h1", { class: "verdict" }, ["Ближе всего к ", el("mark", { text: top.label })]),
    el("p", { class: "sub", text: view.summary }),
  ];
  view.candidates.forEach((candidate, index) => {
    const fill = el("div", { class: "fill" });
    fill.dataset.width = String(Math.round(candidate.value * 100));
    const block = el("div", { class: index === 0 ? "cand top" : "cand" }, [
      el("div", { class: "cand-head" }, [
        el("span", { class: "name", text: candidate.label }),
        el("span", { class: "size", text: `${candidate.words} слов, ${candidate.messages} сообщений` }),
        el("span", { class: "score", text: candidate.value_text }),
      ]),
      el("div", { class: "track", role: "img", "aria-label": `${view.metric_name}: ${candidate.value_text}` }, fill),
    ]);
    if (index === 0 && candidate.why.length) {
      block.append(
        el("div", { class: "why" }, [
          "Сближают:",
          ...candidate.why.map((feature) => el("mark", { text: feature })),
        ])
      );
    }
    block.append(
      el("div", { class: "methods" }, [
        el("span", {}, ["Косинус ", el("b", { text: candidate.cosine })]),
        el("span", {}, ["Delta ", el("b", { text: candidate.delta })]),
        el("span", {}, ["Итоговая оценка ", el("b", { text: candidate.final })]),
      ])
    );
    children.push(block);
  });
  if (view.notes.length) {
    children.push(el("ul", { class: "notes" }, view.notes.map((note) => el("li", { text: note }))));
  }
  if (view.warning) children.push(el("div", { class: "warn", text: view.warning }));
  const actions = el("div", { class: "actions" });
  if (view.report_path) {
    const open = el("button", { class: "btn", text: "Открыть отчёт" });
    open.addEventListener("click", () => api().open_report(view.report_path));
    actions.append(open, el("span", { class: "size", text: view.report_path }));
  }
  children.push(actions);
  out.replaceChildren(...children);
  const grow = () => out.querySelectorAll(".fill").forEach((f) => (f.style.width = `${f.dataset.width}%`));
  requestAnimationFrame(() => requestAnimationFrame(grow));
}

function renderProfile(view) {
  $("profile-empty").hidden = true;
  const out = $("profile-out");
  out.hidden = false;
  out.replaceChildren(
    el("h1", { class: "verdict compact", text: view.header }),
    el(
      "div",
      { class: "features" },
      view.features.map((item) =>
        el("div", { class: "feature" }, [
          el("div", { class: "value", text: item.value }),
          el("div", { class: "name", text: item.name }),
        ])
      )
    ),
    el("div", { class: "words" }, view.word_lines.map((line) => el("p", { text: line })))
  );
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
    const folder = await api().pick_folder();
    if (folder) $("impostors").value = folder;
  });
  $("save-report").addEventListener("change", () => {
    $("report-row").hidden = !$("save-report").checked;
  });
  $("report-pick").addEventListener("click", async () => {
    const path = await api().pick_report_path();
    if (path) $("report").value = path;
  });
  $("go").addEventListener("click", () => launch("compare", compareForm()));

  $("profile-file").addEventListener("click", async () => {
    state.profile = (await chooseFile()) || state.profile;
    showSource("profile-box", "profile-name", state.profile);
    refreshCompare();
  });
  $("profile-tg").addEventListener("click", async () => {
    state.profile = (await chooseTelegram()) || state.profile;
    showSource("profile-box", "profile-name", state.profile);
    refreshCompare();
  });
  $("go-profile").addEventListener("click", () => launch("profile", state.profile.spec));
  $("senders-cancel").addEventListener("click", () => $("senders").close());
}

window.addEventListener("pywebviewready", async () => {
  const info = await api().init();
  $("disclaimer").textContent = info.disclaimer;
  bind();
  initTheme();
  refreshCompare();
});
