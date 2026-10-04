# chatstyle

**English** | [Русский](README.ru.md)

A command-line tool (with a desktop window) for verifying the authorship of Russian-language chat
messages. It answers the question: "were the messages of an unknown sender written by the same
person as the messages of a candidate?" and shows which features the answer is based on.

> **The result is a statistical estimate of style similarity, not proof of authorship.** It can be
> wrong, depends on the amount of text, and must not be used as the only basis for conclusions
> about people. See [Limitations](#limitations) and [Ethics and privacy](#ethics-and-privacy).

> **Status: version 0.1, before the v1.0 release.** Quality results on real data are not yet
> published, see [Quality evaluation](#quality-evaluation) and
> [Status and known gaps](#status-and-known-gaps).

The command-line output, reports and error messages are in Russian (the window itself is
translated into six languages). Examples below show the real output as it is.

## What it does

- **A style-based ensemble of methods.** By default candidates are ranked by: a "skeleton" of
  function words, Burrows Delta, and a language model over text in which rare words are masked
  (so the topic barely matters), with equal weights of z-scores. The `--lexical` flag adds
  vocabulary (see "How to read the result"). The check on real chats is in "Status and known gaps".
- **Three comparison methods** (all computed locally):
  - cosine similarity of TF-IDF character n-grams (1-4), the baseline, with an explanation of
    which n-grams matched;
  - **Burrows Delta** over style features: punctuation habits (brackets ")", "))", ellipses, "!!",
    "??", commas and conjunctions, spaces around marks, dashes, quotes), case and spelling (ALL
    CAPS, stretched words, the "тся/ться" spelling, mixed Cyrillic and Latin, double spaces,
    non-standard spellings), "ё"/"е", Latin letters, emoji, vocabulary richness, lengths of words,
    sentences and messages, frequencies of function words and filler words (about 40 features in
    total; they also make up the style profile);
  - **General Impostors**: whether the candidate's text is consistently closer to the unknown text
    than the texts of outside authors. Its score (0..1) is the **final score**.
- **Three data sources:** a text file, a Telegram Desktop JSON export, Telegram via Telethon.
- **Reports** in Markdown and HTML: a table, the top matching features, style differences, a
  description of the method.
- **Style profile** of a single author: `chatstyle features`.
- A warning if either side has fewer than 1000 words.

## Quick start

The repository contains small fictional files `tests/fixtures/*.txt` (one message per line).
After [installing](#installation):

```bash
chatstyle compare -u file:tests/fixtures/unknown.txt -c file:tests/fixtures/same.txt -c file:tests/fixtures/other.txt
```

```
Неизвестный автор: file:tests/fixtures/unknown.txt — 81 слов, 19 сообщений
┌───────────────────────────────┬──────┬───────────┬──────────┬───────┬──────────────────┬───────┐
│ Кандидат                      │ Слов │ Сообщений │ Сходство │ Delta │ Impostors (итог) │ Смесь │
├───────────────────────────────┼──────┼───────────┼──────────┼───────┼──────────────────┼───────┤
│ file:tests/fixtures/same.txt  │   79 │        19 │    0.643 │     — │                — │ +1.00 │
│ file:tests/fixtures/other.txt │  116 │        14 │    0.257 │     — │                — │ -1.00 │
└───────────────────────────────┴──────┴───────────┴──────────┴───────┴──────────────────┴───────┘
Порядок: по стилевой смеси (каркас служебных слов, Delta, языковая модель без тем).
Лучший по методам: косинус — file:tests/fixtures/same.txt; Смесь — file:tests/fixtures/same.txt (методы согласны).
Burrows Delta недоступна (file:tests/fixtures/same.txt, file:tests/fixtures/other.txt): слишком мало текста для оценки разброса признаков (нужно не меньше 6 кусков по 200 слов на всё сравнение).
General Impostors недоступен (file:tests/fixtures/same.txt, file:tests/fixtures/other.txt): посторонних авторов 1 из 3; добавьте папку с чужими текстами: --impostors DIR.
Подсказка: у неизвестного автора 81 слов (меньше 1000). На коротком тексте стилевая смесь заметно слабее, лексика точнее: добавьте --lexical.
Внимание: мало текста (меньше 1000 слов): неизвестный автор — 81; file:tests/fixtures/same.txt — 79; file:tests/fixtures/other.txt — 116. Оценка может быть ненадёжной.
Результат — статистическая оценка сходства стиля, а не доказательство авторства.
```

Column headings: "Кандидат" is the candidate, "Слов" words, "Сообщений" messages, "Сходство" similarity,
"Impostors (итог)" the final General Impostors score, "Смесь" the ensemble.

A dash means the method is unavailable: there is too little text (here 80-120 words each), so the
program does not invent a number but explains what is missing. A full example with all three
methods is in [Example report](#example-report).

## Requirements

chatstyle is a C++17 core with a Python interface, so two groups of things are needed: tools to
**build** the core once (during `pip install`), and libraries to **run** the program.

**You install yourself (system tools):**

| What | Version | Why | Where to get it |
|---|---|---|---|
| Python | 3.11 or newer (3.12 is used in CI, 3.14 tested locally) | the program itself | python.org, or `apt install python3 python3-venv` |
| A C++17 compiler | MSVC (Visual Studio 2022 Build Tools), MinGW-w64, GCC or Clang | builds the core | Windows: Build Tools with the "Desktop development with C++" workload; Linux: `apt install build-essential` |
| CMake | 3.20 or newer | builds the core | cmake.org, `apt install cmake`, or `pip install cmake` |
| Python headers | the same as your Python | needed to build the Python module | Linux: `apt install python3-dev`; on Windows they come with Python |
| Ninja | any (optional) | the build generator for MinGW-w64 only | `pip install ninja` or your package manager |
| git | any (optional) | only to clone the repository and to download Catch2 when building the C++ tests | git-scm.com |

**Installed automatically by `pip install .`:**

| Package | Used for |
|---|---|
| `scikit-build-core` (>= 0.10), `pybind11` (>= 3.0) | building the core (build time only; fetched into an isolated build environment) |
| `typer` (>= 0.12), `rich` (>= 13) | the command line and the tables |
| `telethon` (>= 1.36) | Telegram access (used only on your command) |
| `pywebview` (>= 5) | the application window |
| `cryptography` (>= 42) | AES-256-GCM encryption of the store and the uploaded chats |

The first `pip install` needs internet access to download these packages; after that the program
works offline (except Telegram).

**Optional extras** (`pip install ".[name]"`):

| Extra | Packages | Used for |
|---|---|---|
| `morph` | `pymorphy3`, `pymorphy3-dicts-ru` | parts of speech (`--morph`, Russian only) |
| `dev` | `pytest`, `ruff` | tests and linting |
| `experiments` | `matplotlib` | plots in `experiments/` |

**For the window only** (`chatstyle gui`; the command line does not need this):

- Windows: the Microsoft Edge WebView2 runtime (already in Windows 11 and up-to-date Windows 10).
- Linux: GTK with WebKit (`apt install python3-gi gir1.2-webkit2-4.1`) or Qt
  (`pip install "pywebview[qt]"`).
- macOS has not been tried.

The ready-made `chatstyle.exe` for Windows (see below) needs none of this: it bundles Python and all
the libraries.

## Installation

You need Python 3.11+ and a C++17 compiler: the core is built during installation (CMake >= 3.20;
pybind11 and scikit-build-core are fetched automatically). Everything needed is listed in
[Requirements](#requirements).

```bash
git clone <repository URL>
cd chatstyle
pip install .
```

Check:

```bash
chatstyle --version
```

If your Python's `Scripts` directory is not on `PATH`, call `python -m chatstyle ...`.

### Windows

- Compiler: **Visual Studio 2022 Build Tools** (the "Desktop development with C++" workload) or
  **MinGW-w64**. MSVC build flags: `/W4 /utf-8 /permissive-`.
- With MinGW-w64 select the Ninja generator (this is how the build was tested on the author's
  machine):

  ```powershell
  $env:CMAKE_GENERATOR = "Ninja"
  pip install .
  ```

- **A ready-made `chatstyle.exe`** (about 18 MB, no installed Python required) will be attached to
  releases. Until then you can build it yourself (Python and a compiler are needed, as above):

  ```powershell
  pip install -e .
  powershell -File packaging\build_exe.ps1            # a single file dist\chatstyle.exe
  powershell -File packaging\build_exe.ps1 -OneDir    # a folder, for debugging
  python packaging/check_exe.py                       # check the built exe (Windows)
  dist\chatstyle.exe --version
  ```

  Double-clicking `chatstyle.exe` prints the help and waits for Enter so the window does not close
  instantly (this does not happen from `cmd` or PowerShell; set `CHATSTYLE_NO_PAUSE=1` to turn the
  pause off). The exe keeps user files in `%APPDATA%\chatstyle`, not next to itself. A single-file
  exe is unpacked into a temporary folder on every start, so it starts in a couple of seconds.

### Application window

Besides the command line there is a window: you pick the unknown author's file and the
candidates, press "Сравнить" (Compare) and see a similarity scale with explanations; the second
tab shows the style profile of one author. The window uses no network: the page is inside the
package, fonts are the system ones.

```powershell
chatstyle gui                          # from the installed package
dist\chatstyle-gui.exe                 # a ready exe, no console window
dist\chatstyle-gui.exe --selftest r.txt  # a check without showing the window, the result goes to r.txt
```

The window is built on pywebview and the Microsoft Edge WebView2 engine built into Windows. It is
already present in Windows 11 and in up-to-date Windows 10; if not, a message with a link to the
installer appears at start. To build the exe: `powershell -File packaging\build_exe.ps1 -Target gui`.
You can sign in to Telegram from the window (the "Telegram" button in the header, see "Telegram via
Telethon" below); a calculation cannot be cancelled. The theme is light or dark, the language is
Russian, English, العربية, Español, 中文 or Français: by default as in the system, and the switches
in the header remember the choice (Arabic is shown right to left). The whole window is
translated; reports and command-line output stay in Russian, as do the detailed core error
messages. The translations were not proofread by native speakers, corrections are welcome: the
dictionaries are in `python/chatstyle/gui/web/lang/`.

### Linux

You need `g++` (or `clang++`), CMake >= 3.20 and the Python headers:

```bash
sudo apt install build-essential cmake python3-dev   # Debian/Ubuntu
pip install .
```

The window (`chatstyle gui`) additionally needs GTK (`python3-gi gir1.2-webkit2-4.1`) or Qt
(`pip install "pywebview[qt]"`); the command line works without them.

### Development

```bash
pip install -e ".[dev]"          # pytest, ruff
pytest                           # Python tests
ruff check python tests experiments
cmake -S . -B build -DCHATSTYLE_BUILD_TESTS=ON -DCHATSTYLE_BUILD_PYTHON=OFF
cmake --build build
ctest --test-dir build           # core tests (Catch2 is downloaded when CMake is configured)
```

For the plots in `experiments/` additionally: `pip install -e ".[experiments]"`.

## Data sources

A source is given as `scheme:value`. At least one candidate is required for a comparison; `-c`
can be repeated.

| Source | Example | What is taken |
|---|---|---|
| `file:` | `file:chat.txt` | A UTF-8 text file, one message per line. |
| `tgexport:` | `tgexport:result.json#Anna Petrova` | A JSON export of one Telegram Desktop chat; after `#` the sender's name, their `from_id` (`user111`) or a numeric id. |
| `tg:` | `tg:@friend` or `tg:@group#@person` | Messages via Telethon: a private chat with a user, or one person's messages in a group. |
| `chat:` | `chat:777#Anna Petrova` | A person from an **uploaded chat** (see below): before `#` the chat's id or title, after it the participant's name or `from_id`. |

Only text messages of the required sender are taken: forwarded and service messages and media
without a caption are skipped. Links and mentions are replaced with tags; empty messages and
placeholders such as `[Фото]` are dropped.

### Uploaded chats

So that you do not have to sort exports into folders by hand, upload a chat export once and it stays
in the list. The original `result.json` can then be deleted: only the texts and times of the
participants' messages are kept.

- **In the window:** the "Чаты" (Chats) tab, then the button to upload a chat export; in the
  comparison and the profile there are buttons to pick from the uploaded chats (several
  participants of a chat can be ticked at once).
- **On the command line:**

  ```
  chatstyle chats add result.json      upload a chat (uploading again extends it without duplicates)
  chatstyle chats list                 list the chats
  chatstyle chats list Friends         participants of one chat (name, identifier, message count)
  chatstyle chats remove Friends       remove a chat from the list
  chatstyle compare -u chat:Friends#Ann -c chat:Friends#Bob -c chat:Friends#Vera
  ```

A chat is given by the id from the export or by its title (if two chats share a title, the id is
needed), a participant by name or identifier (`user111`). This is the same parsing as in
`tgexport:`, but the file is read only once. Chat files live in the data directory (`chats/`) and
are **encrypted** (AES-256-GCM): a random key is kept in the common secret store (the same one that
holds the Telegram login: a master password or DPAPI), so the store must be opened before working
with chats. **API keys and a Telegram login are not needed for this:** in the "Чаты" tab the window
itself offers to set up protection (a master password, DPAPI, or "only while the window is open") or
to open it with the master password; the CLI asks the same. A store protected by a master password
locks itself after 15 minutes of inactivity in the "Чаты" tab. In the "only while the window is
open" mode chats live only in memory and disappear when the window closes. Chats uploaded by
earlier versions (plain `*.json`) are encrypted when the store is first opened, and the plain
copies are overwritten. A file is bound to its id: a substituted or modified file will not decrypt.

### Telegram via Telethon

The network is used **only** here and only on your explicit command.

1. Get an `api_id` and `api_hash` at <https://my.telegram.org> (the API development tools
   section).
2. Sign in once: the command asks for a protection method (a master password or the Windows
   account), if needed for the `api_id`/`api_hash` keys (they can also be given by the environment
   variables `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` or a `.env` file), then the phone number, the
   code from Telegram and the 2FA password if it is enabled:

   ```bash
   chatstyle login
   ```

3. Compare (if the store is protected by a master password, the command asks for it without echo):

   ```bash
   chatstyle compare -u tg:@stranger -c tg:@friend1 -c file:friend2.txt --limit 1000
   ```

**From the window.** The "Telegram" button in the header opens a wizard: the sign-in protection
method, the keys (`api_id`, `api_hash`), the phone number, the code from Telegram and the 2FA
password if it is enabled. The code and passwords are never saved, and the fields are cleared right
after sending. After signing in, the sources get "From Telegram" (a chat and, if needed, a sender),
and the message limit and "load again" are under "Advanced". Signing in from the window and
`chatstyle login` use the same encrypted store. "Sign out of Telegram" erases the session from the
store and ends it on Telegram's side; "Delete all Telegram data" also deletes the store itself.
Details of the protection are in [Security](#security).

`--limit` (3000 by default) is the maximum number of messages per author; what is loaded is
cached, a repeated run uses the cache, and `--refresh` loads again. Without signing in, `compare`
with `tg:` asks you to run `chatstyle login`.

## Usage

```bash
chatstyle compare -u file:unknown.txt -c file:a.txt -c file:b.txt \
    --impostors outsider_texts/ --seed 1 --report report.html
chatstyle features file:chat.txt --top 10
chatstyle login
```

| `compare` option | Meaning |
|---|---|
| `-u, --unknown` | the unknown author's source |
| `-c, --candidate` | a candidate's source (can be repeated) |
| `--impostors DIR` | a folder with outside texts for General Impostors: **one `.txt` file per author** (UTF-8, one message per line) |
| `--seed N` | the General Impostors seed (1 by default): the same seed gives the same result |
| `--report FILE` | save a report; the format is chosen by the extension, `.md` or `.html` |
| `--style-groups G` | groups of style features for Burrows Delta: `all` (default), `none`, or a comma-separated list of `punctuation`, `orthography`, `words`, `sentences`; does not affect the final General Impostors score |
| `--morph` | add a "Части речи" (parts of speech) column: similarity of part-of-speech n-grams (1-4); needs the optional add-on `pip install chatstyle[morph]` (pymorphy3), Russian only, does not affect the final score |
| `--charlm` | add a "Языковая модель (бит/символ)" (language model, bits per character) column: by how many bits per character the unknown author's text is predicted better by this candidate's character model than by the model of the other candidates (above zero means closer to the candidate); needs at least two non-empty candidates, does not affect the final score |
| `--wordgrams` | add a "Слова (косинус)" (words, cosine) column: similarity of word n-grams (1-4 consecutive words, TF-IDF); words that only one author has are not distinguished; does not affect the final score |
| `--emoji` | add an "Эмодзи (косинус)" (emoji, cosine) column: similarity of which emoji the author uses and in what order (1-4 in a row; composite emoji with skin tone and joiners count as one); an author without any emoji gets no score; does not affect the final score |
| `--rhythm` | add a "Ритм (по времени)" (rhythm by time) column: similarity of writing rhythm (message series, pauses, time of day, weekends); needs message dates (sources `tgexport:` and `tg:`; `file:` has no dates) and at least 30 dated messages per author; does not affect the final score |
| `--lexical` | add vocabulary to the ensemble (a plain character language model and word n-grams instead of the language model over text without rare words): slightly more accurate on the chats tested (98% against 95%) but more sensitive to the topic; by default the order is computed from style only |
| `-n, --limit N`, `--refresh` | for `tg:`: the message limit and cache refresh |

When the output is redirected (`chatstyle compare ... > result.txt`) the text is written in UTF-8.

**Parts of speech.** In `chatstyle.exe` and `chatstyle-gui.exe` they are included by default
(pymorphy3, about +9 MB; a build without them: `powershell -File packaging\build_exe.ps1
-NoMorph`). When running from source the add-on is needed: `pip install chatstyle[morph]`. The
command `chatstyle compare ... --morph` adds the "Части речи (косинус)" column, while
`chatstyle features ... --morph` and the "Style profile" tab of the window (the "Учитывать части
речи" checkbox) show the shares of nouns, verbs, particles and out-of-dictionary words. Python only
tags words with one-letter part-of-speech codes (pymorphy3, locally, no network), and the same core
counts the frequencies and n-grams over the codes. Tagging without context is ambiguous ("мыла" is
a noun or a verb?), and slang and names are unknown to the dictionary, so the feature is noisy and
does not affect the final score. In the window the checkboxes for parts of speech, the language
model, word n-grams, emoji and rhythm are on from the start (parts of speech if they are in the
build); on the command line these methods are switched on with `--morph`, `--charlm`,
`--wordgrams`, `--emoji`, `--rhythm`.

**Character language model.** For each candidate the core trains a character model (a context of
up to three characters, Witten-Bell smoothing, case preserved) and counts how many bits per
character are needed to "encode" the unknown author's text. The same figure for the model of the
other candidates is subtracted: a positive value means the text is closer to this candidate. The
amount of training text is equalized across candidates (no more than the shortest has is taken),
otherwise a long candidate would win simply by size. With one candidate there is no score. The
method is switched on with `--charlm` or the checkbox in the window and does not affect the final
score yet: its usefulness on real data has not been measured.

**Word n-grams.** The `--wordgrams` flag (and the checkbox in the window) computes the same cosine
similarity, but over sequences of 1-4 words rather than characters: stable turns of phrase ("ну
вообще", "в принципе") contribute more than single letters. Words are lowercased; a word that is
absent from at least two authors of the comparison cannot confirm anything and is replaced with a
common "rare word" mark. As with parts of speech, Python only replaces words with symbols, and the
same core counts the n-grams. It does not affect the final score; its usefulness on real data has
not been measured.

**Emoji in more detail.** The "emoji share" feature of the profile only says whether there are many
or few of them. The `--emoji` flag (and the checkbox in the window) compares *which exactly* emoji
and in what order: only the emoji remain from the messages (composite ones count as whole), each is
given a symbol, and the same core computes the cosine over 1-4 n-grams. An author without emoji
gets no score. It does not affect the final score.

**Writing rhythm over time.** If the source knows when the messages were written (a Telegram
Desktop export and `tg:` loading), the core counts eight features from the author's times: the
share of pauses up to a minute, the length of message series, the typical pause (pauses longer than
six hours, a night break, are not counted), the shares of messages at night, in the morning, in the
afternoon and in the evening, and the share of weekends. The time is "wall-clock", as on the
author's watch (the computer's time zone), so you should compare exports of one person and their
interlocutor from the same device. The profile (`chatstyle features`, the "Style profile" tab) shows
the rhythm automatically when it exists; in a comparison it is switched on with `--rhythm`. A series
is the author's messages with pauses up to a minute (the interlocutor's messages are not visible in
the source). `file:` files have no dates, so they have no rhythm. It does not affect the final
score; its usefulness on real data has not been measured. The Telegram cache now stores the time
too, so a cache from an earlier version is not read and the messages are loaded again.

**Habits, not mistakes.** The punctuation and spelling features measure the author's *stable
habits* (how often they stretch letters, put a comma before a conjunction, write "щас" or "тся"),
not whether something is written "correctly": no dictionary or grammar checker is used, everything
is computed locally. What matters for the comparison is that the habits of the two texts coincide.
The list of non-standard spellings (`python/chatstyle/resources/nonstandard_ru.txt`) was compiled
by hand and not proofread by native speakers. The features work only in Burrows Delta and in the
style profile; the final General Impostors score is still computed from character n-grams. Their
usefulness on real data has not been measured: synthetic data only checks that the counting is
correct (see "Status and known gaps").

### How to read the result

| Column | Meaning |
|---|---|
| Сходство (similarity) | cosine of TF-IDF n-grams, 0..1, more is closer |
| Delta | Burrows Delta, less is closer; comparable only between candidates of one run |
| Impostors (итог) | the **final score**: the share of 100 random iterations in which the candidate's text is closer to the unknown one than the texts of all outsiders. A number 0..1, but **not a probability** |
| Смесь (ensemble) | the **order of candidates**: the mean of the z-scores of three signals across candidates of equal size: the function-word "skeleton", Delta, and a character language model over text without rare words (with `--lexical`, instead of the last one, a plain language model and word n-grams); more is closer; the value is relative to the set of candidates of this run. With two candidates it is the share of the methods' "votes": +1 all for, -1 all against |

If there are at least two candidates, the rows are sorted by the style ensemble; otherwise by
Impostors (if it is available for all), otherwise by TF-IDF cosine. So that a large candidate does
not win by the size of its vocabulary alone, the ensemble is computed over candidates of equal
size: random messages up to 2500 words are taken from each (but no fewer than the shortest
candidate has). The "Сходство", "Delta" and "Impostors (итог)" columns are still computed over the
whole text. In the window the bar shows the *relative* closeness of the candidates (a softmax of
the ensemble with temperature 1.0, the shares sum to 1); this is not the probability of authorship.
The "Лучший по методам" (best by methods) line shows whether the methods agree. When they
disagree, that is information in itself: do not pick the method you like.

When methods are unavailable (a dash):

- **Delta:** at least 6 chunks of 200 words are needed for the whole comparison (about 600 words
  for two authors).
- **General Impostors:** at least 3 outside authors are needed (the other candidates plus the
  `--impostors` folder) and at least 2 chunks of 200 words from the unknown author and from the
  candidate. In a run "unknown + 2 candidates" there is one outsider per candidate, so without
  `--impostors` there will be no final score: this is deliberate.

## Example report

[`docs/example_report.md`](docs/example_report.md) is a report on **fictional** data (not a real
conversation). To reproduce it:

```bash
python docs/make_example_data.py example_data
cd example_data
chatstyle compare -u file:unknown.txt -c file:candidate_same.txt -c file:candidate_other.txt \
    --impostors impostors --report report.md
```

```
┌──────────────────────────┬──────┬───────────┬──────────┬───────┬──────────────────┬───────┐
│ Кандидат                 │ Слов │ Сообщений │ Сходство │ Delta │ Impostors (итог) │ Смесь │
├──────────────────────────┼──────┼───────────┼──────────┼───────┼──────────────────┼───────┤
│ file:candidate_same.txt  │ 2727 │       300 │    0.848 │  0.31 │             0.65 │ +1.00 │
│ file:candidate_other.txt │ 2990 │       300 │    0.820 │  0.51 │             0.09 │ -1.00 │
└──────────────────────────┴──────┴───────────┴──────────┴───────┴──────────────────┴───────┘
Порядок: по стилевой смеси (каркас служебных слов, Delta, языковая модель без тем).
Лучший по методам: косинус — file:candidate_same.txt; Delta — file:candidate_same.txt; Смесь — file:candidate_same.txt; Impostors — file:candidate_same.txt (методы согласны).
```

The report (`.md` and a self-contained `.html` with no external resources) contains: the candidate
table, an explanation of the final score, the top 20 matching n-grams (single letters and the space
are hidden as uninformative), the main style differences by Delta under readable names, the run
parameters (seed, number of outsiders), a description of the method and the limitations.

## Quality evaluation

**There are no results yet.** Honest figures need labelled real texts by several authors, and the
project has no such corpus. Any number obtained on made-up data would say nothing about quality on
real conversations, so there is none here on purpose.

**A check on your own chats.** If you have uploaded several chats (the "Чаты" tab or
`chatstyle chats add`), you can check the order of candidates on them without any labelling:

```bash
python -m experiments.chats_eval            # the style ensemble (default)
# reads the encrypted store (asks for the master password); --chats-dir FOLDER means plain chat files
python -m experiments.chats_eval --lexical  # the ensemble with vocabulary
```

The same participant identifier in different chats counts as one person; two kinds of tasks are
built: "across contexts" (a person from one chat against the others, whose texts are taken from
other chats) and "by time" (the latest messages against the rest). Only numbers are printed (the
share of first places, MRR, the share under random guessing), no names or texts. This does not
replace an evaluation on a labelled corpus (see the caveats in "Status and known gaps"), but lets
you re-check how the algorithm behaves on your own data.

The evaluation tooling is ready (`experiments/`) and tested on synthetic data:

```bash
# dataset: a folder, one .txt file per author, anonymous names, messages in order
python -m experiments.evaluate DATASET --words 1000 --impostors 10 --jobs 4 --output results.json
python -m experiments.volume DATASET --slices 250 500 1000 2000 5000 --jobs 4   # quality by volume, and a plot
python -m experiments.prepare_tgexport result.json DATASET --min-messages 300   # a dataset from a group chat
```

For each method the ROC AUC is computed (with a confidence interval, bootstrapped over authors)
and the accuracy at a threshold chosen on different data. For debugging there is
`python -m experiments.make_synthetic FOLDER`; such data is marked, and the scripts warn twice that
the numbers must not be published.

The new groups of style features (punctuation, orthography, words, sentences) can be checked one at a
time: `python -m experiments.ablation DATASET` computes the Burrows Delta AUC without groups, with
each group and with all of them, and `python -m experiments.evaluate DATASET --style-groups
words,sentences` runs the usual evaluation with the chosen groups. A dataset with authors who have
built-in writing habits is created by `python -m experiments.make_synthetic FOLDER --habits`. While
there is no corpus, such a run only proves that the groups really change the score, not that they
are useful on people.

The "fewer than 1000 words" warning threshold is provisional for now: it will be refined from the
results of an evaluation on real data.

## Limitations

- **The estimate is probabilistic.** It is a measure of style similarity, not proof. A high score
  does not mean the same author, and a low one does not mean different authors.
- **The amount of text matters a lot.** With a small volume (fewer than 1000 words on either side)
  the score may be random; with a very small one Delta and General Impostors are unavailable.
- **The final score depends on the "outsiders".** If there are few of them or they differ from the
  real environment of communication, the score is distorted.
- **Style depends on context.** One person writes differently in different chats, and different
  people of the same circle, age and topic write alike.
- **Languages.** Letters and case are determined from the Unicode 16 tables (Latin with diacritics,
  Greek, Armenian, Georgian, Arabic, Hebrew, Indic scripts and others), so the character-based
  methods (cosine, language model, "skeleton") work with any script; in Chinese and Japanese
  (ideographs and kana) each sign counts as a word. **But accuracy has been verified only on
  Russian.** On synthetic data for nine languages (English, French, German, Spanish, Polish, Greek,
  Arabic, Chinese, Japanese) authors with different vocabularies are told apart; this is a check
  that it works, not of accuracy. Delta relies on Russian lists of function words, filler words and
  "non-standard spellings" and on features such as "тся/ться" and "ё/е", so in other languages only
  the language-independent features remain (punctuation, case, lengths); parts of speech
  (`--morph`) are Russian only. In other languages it is better to turn on `--lexical`. For Thai,
  Lao, Khmer and Burmese (scripts without spaces that are not ideographs) a word is still a run of
  letters. Case folding follows the simple Unicode rules: the Turkish İ and similar special cases
  are not changed.
- **Distortions of the source data:** shared accounts, bots, quotes, forwarded messages and pasted
  text affect the result; forwarded Telegram messages are not counted, but quotes inside ordinary
  messages remain.
- **Deliberate imitation of someone else's style and paraphrasing of the text have not
  been evaluated** (planned for a later version).
- **Timestamps** are needed only for the rhythm (`--rhythm`): text files have none.
- Text files are read only as UTF-8; a file in another encoding is rejected with a clear message
  rather than read with distortion.
- The method is closed-set: it compares with the candidates you named. The real author may not be
  among them.

## Ethics and privacy

- **Everything is computed locally.** The only network access is Telegram (Telethon), and only on
  an explicit command: `chatstyle login` and `compare`/`features` with a `tg:` source. There is no
  telemetry.
- **Which files the program creates.** In the data directory (`%APPDATA%\chatstyle` on Windows,
  `~/.local/share/chatstyle` or `$XDG_DATA_HOME/chatstyle` on Linux; it can be overridden with the
  `CHATSTYLE_HOME` variable):
  - `vault.json` is the **encrypted** store: the Telegram API keys and the session (which is
    equivalent to access to your account), see [Security](#security);
  - `cache/` is a cache of loaded messages of **real people** (not encrypted);
  - `chats/` holds uploaded chats (the "Чаты" tab, `chatstyle chats add`): texts and times of
    messages of **real people**, **encrypted** with the key from the store (`*.chat`);
  - `gui-settings.json` is the window's language and theme;
  - `.env` holds the `api_id` and `api_hash` keys, only if you put them there yourself.

  To delete everything, delete this directory (and end the session in Telegram's settings:
  "Devices").
- **Reports contain fragments of conversations** (n-grams) and the names of the sources. Do not
  publish them or pass them on without the consent of the message authors. The file names of the
  `--impostors` folder do not get into the report.
- **Other people's conversations are personal data.** Before analysing a chat, obtain the consent
  of its participants and check that it is permitted by the laws of your country. The project does
  not give legal advice.
- **The repository must not contain** `.env`, `.session` files, the cache or any real
  conversations; they are excluded in `.gitignore`. Do not add them to commits or examples.
- **What the tool is not intended for:** de-anonymizing people against their will, surveillance,
  pressure and harassment, backing up accusations without other evidence, passing the result off as
  proof of authorship.

## Security

**What it protects against.** Other users of this computer, theft or a copy of the disk and the data
folder, cloud synchronization, accidental publication of files, tampering with the window's page,
and interception of the traffic to Telegram. **What it does not protect against.** Malware running
under your account, and a keylogger or screen recording: if they are present, no program can keep
secrets. Against such a threat choose the "only while the window is open" mode and enable two-factor
protection in Telegram.

- **Three ways to store the login** (`chatstyle login` or the wizard in the window):
  - *master password* (recommended): the keys and the session are encrypted with AES-256-GCM, the
    key is derived from the password with scrypt (64 MB, about 0.3 s per attempt), the password is
    stored nowhere, attempts slow down after three wrong entries; the store locks itself after 15
    minutes of inactivity;
  - *Windows account* (DPAPI): no password is needed, but any program under your account can
    decrypt the login;
  - *only while the window is open*: nothing is written to disk, and when the window closes the
    session is ended on Telegram's side.
- **We do not write cryptography ourselves:** AES-GCM comes from the `cryptography` library, scrypt
  from the standard `hashlib`, DPAPI is a Windows system call. The store file is authenticated:
  corruption or tampering with the header is detected. A forgotten master password cannot be
  recovered: you sign in again.
- **Uploaded chats are encrypted** by the same store: the AES-256-GCM key (256 bits, random) is in
  `vault.json`, not next to the files; without the store open the chats cannot be read. Removing a
  chat overwrites the file with zeros (on an SSD this does not guarantee physical erasure). If
  malware runs under your account while the store is open, it will get the chats too, just as it
  would the Telegram session. The "only while the window is open" mode keeps chats in memory only.
- **Permissions:** the data folder is closed to everyone but your account (on Windows through
  `icacls`, on Linux with permissions `0700`/`0600`).
- **The window:** the page is loaded from a file inside the package, not from a local server: the
  process has no listening ports (the self-test checks this). A CSP policy forbids any network
  requests from the page, navigation to other addresses is blocked, browser storage and autofill
  are not used (WebView2 private mode), and developer tools are disabled. Files are chosen only in
  the window's dialogs, only reports it created itself are opened, and everything coming from the
  page is checked for type and length.
- **The build:** dependencies are pinned by version and hash (`packaging/requirements.lock`,
  installed with `pip install --require-hashes`), `pip-audit` found no known vulnerabilities at the
  time of writing, and `dist/SHA256SUMS.txt` is created next to the exe. **The exe is not signed**
  (a certificate is needed), so SmartScreen may warn on the first start.
- **Plain files of the earlier version** (`telegram.session`, `telegram.account`) are offered for
  deletion by the window when found: they are not encrypted. The Telegram message cache (`cache/`)
  is not encrypted yet either.

## How the project is organized

- **The core (`core/`, C++17):** computations over text as a sequence of Unicode code points
  (UTF-8 to `std::u32string`), n-grams, TF-IDF, cosine, Burrows Delta, General Impostors,
  explanations. The core knows nothing about files, Telegram or reports. The link to Python is
  pybind11 (`chatstyle._core`).
- **Python (`python/chatstyle/`):** collectors (txt, Telegram export, Telethon), preprocessing, the
  pipeline, the CLI (typer, rich), reports. Python does not compute features itself.
- **Other:** `tests/` (pytest), `core/tests/` (Catch2), `experiments/` (quality evaluation, not part
  of the package), `packaging/` (PyInstaller), `docs/` (the example report),
  `.github/workflows/ci.yml`.

## Status and known gaps

This section is temporary and must disappear by v1.0. An honest list of what is **not verified**:

- **CI on GitHub has not been run** (the repository is not published), so the build on Windows
  (MSVC) and Linux is not confirmed automatically. Locally it was checked on Windows 10 with
  MinGW-w64 (Python 3.14); the MSVC `/W4` flags have never been applied to the core. Installation
  on Linux (building the core, running `chatstyle`) was checked manually by the project owner on
  Kali Linux; the tests and the window were not run there.
- **The Telegram collector was verified only on stubs**, with no live account.
- **`chatstyle.exe`** was built locally (MinGW-w64). The script `packaging/check_exe.py` checked it
  on this machine: the version and icon in the file properties, working with a `PATH` without
  Python, reading `.env` from `%APPDATA%\chatstyle`, output in a real console 80 columns wide, the
  pause on a double-click start. **Not verified:** a clean Windows 10 with no Python at all
  (Windows Sandbox will do: copy a single `chatstyle.exe` there and run `chatstyle --version` and
  `compare`), and an exe built with MSVC.
- **The evaluation on real data is a single conversation environment, and the choice of method was
  tuned to it.** The check ran on one user's chats: two groups (202 and 16 participants) and
  private chats. Tasks: a person from one context (chat) against the other people whose texts are
  taken from other chats (25 tasks), a time split inside a group (16), and one real "twin account"
  case (2); all candidates have 2500 words each, the unknown text has 600-1400 words, and there
  are 10-36 candidates. First place of the true author: the full ensemble with vocabulary (language
  model, words, "skeleton", Delta) 95% (MRR 0.97), the style ensemble (the default: "skeleton",
  Delta, language model without rare words) 91% (MRR 0.93); on the "across contexts" tasks that is
  92% against 84%: the style ensemble pays a few points for independence from the topic (on 129 runs
  "the true author and 3 rivals" the full one gets 98%, the style one 95%); separately the language
  model 88%, word n-grams 88%, Delta 72%, "skeleton" 72%, Impostors with the other candidates as
  outsiders 58%, TF-IDF cosine 56%. If you keep the true author and 3 random rivals (129 runs,
  random guessing is 25%): the full ensemble 98%, Delta 88%, cosine 84%, Impostors 75%. Fitted
  ensemble weights were not better than equal ones (a "leave one person out" check, the difference
  within noise), and adding a "background" of dozens of outside authors for the z-scores changed
  nothing, so the weights are equal and there is no background.
  **How to treat this:** this is one environment (Russian-language chats of one circle, many shared
  words and topics), the tasks depend on each other, and the four methods were chosen from about ten
  on the same data, so the figures are optimistic and may not carry over to other people,
  languages and volumes. The language model and word n-grams are sensitive to vocabulary and topic
  (partly offset by the unknown text and the candidates being taken from different chats); the
  "skeleton" and Delta depend on the topic weakly.
  **How much text is needed** ("across contexts" and real tasks, 27 tasks, noise about ±7 points).
  The unknown author's text, first place for the style ensemble / the ensemble with vocabulary:
  300 words 67% / 70%, 600 70% / 93%, 1000 85% / 96%, 2000 81% / 96%, 4000 89% / 93%. The style
  ensemble hardly grows with more text (on this data it tops out at 85-90%), while vocabulary
  already gives 93%+ at 600 words: if the unknown author has fewer than 1000 words, use `--lexical`
  (the program reminds you of this itself with a hint in the table, the reports and the window).
  Candidate volume (equal for all): 2500 words each 93% / 98%, 5000 86% / 93%, 10000 88% / 95%;
  the worse the volumes are equalized, the worse the result, so the default cap is 2500 words (but
  no fewer than the shortest has). Different random samples of messages of the same volume give a
  further spread of 2-3 points. A first check on 5 candidates favoured "cosine Delta"; on 36
  candidates this was not confirmed: the conclusion from a small sample turned out wrong, and that
  method is no longer in the program.

## References

- Burrows J. *Delta: a Measure of Stylistic Difference and a Guide to Likely Authorship.*
  Literary and Linguistic Computing, 17(3), 2002.
- Koppel M., Winter Y. *Determining if two documents are written by the same author.*
  Journal of the Association for Information Science and Technology, 65(1), 2014.

## License

MIT, see [`LICENSE`](LICENSE).
