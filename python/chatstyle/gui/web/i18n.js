"use strict";

// Перевод окна. Словари лежат в lang/*.js и регистрируются через registerLanguage.
// Подписи, пояснения и ошибки из Python приходят кодами с параметрами: см. gui/api.py.

const LANGUAGES = [
  { code: "ru", name: "Русский", dir: "ltr" },
  { code: "en", name: "English", dir: "ltr" },
  { code: "ar", name: "العربية", dir: "rtl" },
  { code: "es", name: "Español", dir: "ltr" },
  { code: "zh", name: "中文", dir: "ltr" },
  { code: "fr", name: "Français", dir: "ltr" },
];
const FALLBACK_LANGUAGE = "en";
const DICTIONARIES = {};
let currentLanguage = FALLBACK_LANGUAGE;

function registerLanguage(code, words) {
  DICTIONARIES[code] = words;
}

function languageByCode(code) {
  return LANGUAGES.find((language) => language.code === code) || null;
}

// Язык системы: первый из navigator.languages, который есть среди поддерживаемых (zh-CN -> zh).
function detectLanguage() {
  for (const tag of navigator.languages || [navigator.language || ""]) {
    const found = languageByCode(String(tag).toLowerCase().split("-")[0]);
    if (found) return found.code;
  }
  return FALLBACK_LANGUAGE;
}

function lookup(key) {
  for (const code of [currentLanguage, FALLBACK_LANGUAGE]) {
    const words = DICTIONARIES[code];
    if (words && Object.prototype.hasOwnProperty.call(words, key)) return words[key];
  }
  return key;
}

function fill(template, params) {
  return template.replace(/\{(\w+)\}/g, (whole, name) => (name in params ? String(params[name]) : whole));
}

// Перевод строки с подстановкой {параметров}.
function t(key, params = {}) {
  return fill(lookup(key), params);
}

// Перевод, в котором часть параметров вставляется как узлы (например, подсвеченное имя).
function tNodes(key, params = {}) {
  const parts = lookup(key).split(/(\{\w+\})/);
  return parts
    .filter((part) => part !== "")
    .map((part) => {
      const name = /^\{(\w+)\}$/.exec(part);
      if (!name || !(name[1] in params)) return part;
      return params[name[1]];
    });
}

// Подпись метода, подписи списка, ошибка и т. п. по коду из Python.
function translateError(error) {
  const known = lookup(`error.${error.code}`) !== `error.${error.code}`;
  return known ? t(`error.${error.code}`, error.params || {}) : t("error.unexpected", { message: error.code });
}

function setLanguage(code) {
  const language = languageByCode(code) || languageByCode(FALLBACK_LANGUAGE);
  currentLanguage = language.code;
  const root = document.documentElement;
  root.lang = language.code;
  root.dir = language.dir;
  applyStaticTexts();
}

function applyStaticTexts() {
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  }
  for (const node of document.querySelectorAll("[data-i18n-aria]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAria));
  }
}
