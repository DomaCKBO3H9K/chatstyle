# Changelog

## 0.1.0

First public pre-release. Not yet v1.0: see "Status and known gaps" in the README.

- Comparison of a chat author's messages with candidates: TF-IDF character n-grams, Burrows Delta,
  General Impostors, and a style-based ensemble (function-word skeleton, Delta, masked character
  language model) with an optional `--lexical` mode.
- Extra signals: parts of speech, character language model, word n-grams, emoji, writing rhythm.
- Sources: text files, Telegram Desktop exports, Telegram via Telethon, uploaded chats.
- Encrypted storage for the Telegram login and for uploaded chats (master password, DPAPI or
  memory-only mode).
- Desktop window (pywebview) in six languages; Markdown and HTML reports.
- Unicode-aware core: letters and case for many scripts (accuracy verified on Russian only).
- Windows exe (`chatstyle.exe`, `chatstyle-gui.exe`, unsigned), Linux source archive with
  `install.sh`, source distribution.
