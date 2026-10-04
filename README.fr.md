# chatstyle

[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md) | **Français** | [中文](README.zh.md) | [العربية](README.ar.md)

Un outil en ligne de commande (avec une fenêtre de bureau) pour vérifier la paternité de messages
de discussion en russe. Il répond à la question : « les messages d'un expéditeur inconnu ont-ils
été écrits par la même personne que les messages d'un candidat ? », et montre sur quels traits
repose la réponse.

> **Le résultat est une estimation statistique de la similarité de style, pas une preuve de
> paternité.** Il peut être faux, dépend de la quantité de texte et ne doit pas servir de seul
> fondement pour tirer des conclusions sur des personnes. Voir [Limites](#limites) et
> [Éthique et vie privée](#éthique-et-vie-privée).

> **État : version 0.1, avant la version v1.0.** Les résultats de qualité sur des données réelles
> ne sont pas encore publiés, voir [Évaluation de la qualité](#évaluation-de-la-qualité) et
> [État et lacunes connues](#état-et-lacunes-connues).

La sortie de la ligne de commande, les rapports et les messages d'erreur sont en russe (la fenêtre
elle-même est traduite en six langues). Les exemples ci-dessous montrent la sortie réelle telle
quelle.

## Ce que fait l'outil

- **Un ensemble de méthodes fondé sur le style.** Par défaut, les candidats sont classés avec : un
  « squelette » de mots grammaticaux, Burrows Delta et un modèle de langue sur un texte où les mots
  rares sont masqués (le sujet compte donc à peine), avec des poids égaux de scores z. L'option
  `--lexical` ajoute le vocabulaire (voir « Comment lire le résultat »). La vérification sur des
  discussions réelles figure dans « État et lacunes connues ».
- **Trois méthodes de comparaison** (toutes calculées en local) :
  - similarité cosinus de n-grammes de caractères TF-IDF (1-4), la méthode de base, avec une
    explication des n-grammes qui ont coïncidé ;
  - **Burrows Delta** sur des traits de style : habitudes de ponctuation (parenthèses « ) », « )) »,
    points de suspension, « !! », « ?? », virgules et conjonctions, espaces autour des signes,
    tirets, guillemets), casse et orthographe (MAJUSCULES, mots étirés, la graphie « тся/ться »,
    mélange de cyrillique et de latin, doubles espaces, graphies non standard), « ё »/« е »,
    lettres latines, émojis, richesse du vocabulaire, longueur des mots, des phrases et des
    messages, fréquences des mots grammaticaux et des tics de langage (environ 40 traits au total ;
    ils forment aussi le profil de style) ;
  - **General Impostors** : le texte du candidat est-il de façon constante plus proche de
    l'inconnu que les textes d'auteurs extérieurs. Son score (0..1) est le **score final**.
- **Trois sources de données :** un fichier texte, une exportation JSON de Telegram Desktop,
  Telegram via Telethon.
- **Rapports** en Markdown et HTML : un tableau, les principaux traits concordants, les
  différences de style, une description de la méthode.
- **Profil de style** d'un seul auteur : `chatstyle features`.
- Un avertissement si l'un des côtés a moins de 1000 mots.

## Captures d'écran

Fenêtre réelle de l'application sur les données **fictives** de `docs/demo/` : deux discussions
(un voyage au lac et un projet de travail) entre les mêmes quatre personnes inventées. Texte
inconnu : Anya dans la discussion de travail ; candidats : les quatre personnes de la discussion
du voyage. La fenêtre est montrée en anglais (elle parle aussi russe, Español, Français, 中文 et العربية).

![Comparaison](docs/screenshots/compare-en.png)

![Profil de style](docs/screenshots/profile-en.png)

![Discussions importées](docs/screenshots/chats-en.png)

Les discussions fictives existent aussi en anglais, espagnol, français, chinois et arabe
(traduites par l'auteur, pas écrites par des locuteurs natifs) : `python docs/demo_eval.py`
vérifie sur chaque langue que le même auteur est reconnu d'une discussion à l'autre (8 tâches
par langue, 8 sur 8 ici). Les habitudes de leurs personnages sont volontairement marquées, donc ce
contrôle montre que la méthode fonctionne avec ces écritures, mais pas sa précision sur de vraies
personnes.

## Démarrage rapide

Le dépôt contient de petits fichiers fictifs `tests/fixtures/*.txt` (un message par ligne).
Après l'[installation](#installation) :

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

En-têtes de colonnes : « Кандидат » est le candidat, « Слов » les mots, « Сообщений » les
messages, « Сходство » la similarité, « Impostors (итог) » le score final de General Impostors,
« Смесь » l'ensemble de méthodes.

Un tiret signifie que la méthode n'est pas disponible : il y a trop peu de texte (ici 80 à 120
mots par auteur), donc le programme n'invente pas de nombre mais explique ce qui manque. Un
exemple complet avec les trois méthodes se trouve dans [Exemple de rapport](#exemple-de-rapport).

## Prérequis

chatstyle est un cœur C++17 avec une interface Python, donc deux groupes de choses sont
nécessaires : des outils pour **compiler** le cœur une fois (pendant `pip install`) et des
bibliothèques pour **exécuter** le programme.

**À installer soi-même (outils système) :**

| Quoi | Version | Pourquoi | Où l'obtenir |
|---|---|---|---|
| Python | 3.11 ou plus récent (3.12 en CI, 3.14 testé en local) | le programme lui-même | python.org, ou `apt install python3 python3-venv` |
| Un compilateur C++17 | MSVC (Visual Studio 2022 Build Tools), MinGW-w64, GCC ou Clang | compile le cœur | Windows : Build Tools avec la charge de travail « Développement Desktop en C++ » ; Linux : `apt install build-essential` |
| CMake | 3.20 ou plus récent | compile le cœur | cmake.org, `apt install cmake` ou `pip install cmake` |
| En-têtes Python | ceux de votre Python | nécessaires pour compiler le module Python | Linux : `apt install python3-dev` ; sous Windows ils viennent avec Python |
| Ninja | n'importe laquelle (facultatif) | le générateur de compilation pour MinGW-w64 uniquement | `pip install ninja` ou votre gestionnaire de paquets |
| git | n'importe laquelle (facultatif) | uniquement pour cloner le dépôt et télécharger Catch2 lors de la compilation des tests C++ | git-scm.com |

**Installés automatiquement par `pip install .` :**

| Paquet | Utilité |
|---|---|
| `scikit-build-core` (>= 0.10), `pybind11` (>= 3.0) | compiler le cœur (uniquement à la compilation ; récupérés dans un environnement de compilation isolé) |
| `typer` (>= 0.12), `rich` (>= 13) | la ligne de commande et les tableaux |
| `telethon` (>= 1.36) | accès à Telegram (utilisé uniquement sur votre demande) |
| `pywebview` (>= 5) | la fenêtre de l'application |
| `cryptography` (>= 42) | chiffrement AES-256-GCM du coffre et des discussions importées |

Le premier `pip install` nécessite un accès à internet pour télécharger ces paquets ; ensuite le
programme fonctionne hors ligne (sauf Telegram).

**Extras facultatifs** (`pip install ".[nom]"`) :

| Extra | Paquets | Utilité |
|---|---|---|
| `morph` | `pymorphy3`, `pymorphy3-dicts-ru` | parties du discours (`--morph`, russe uniquement) |
| `dev` | `pytest`, `ruff` | tests et analyse du style du code |
| `experiments` | `matplotlib` | graphiques dans `experiments/` |

**Pour la fenêtre uniquement** (`chatstyle gui` ; la ligne de commande n'en a pas besoin) :

- Windows : le runtime Microsoft Edge WebView2 (déjà présent dans Windows 11 et dans un Windows 10
  à jour).
- Linux : GTK avec WebKit (`apt install python3-gi gir1.2-webkit2-4.1`) ou Qt
  (`pip install "pywebview[qt]"`).
- macOS n'a pas été essayé.

Le `chatstyle.exe` déjà compilé pour Windows (voir plus bas) n'a besoin de rien de tout cela : il
embarque Python et toutes les bibliothèques.

## Installation

**Les fichiers déjà compilés** sont joints à chaque version sur la
[page Releases](https://github.com/DomaCKBO3H9K/chatstyle/releases) : `chatstyle.exe` et
`chatstyle-gui.exe` pour Windows (pas besoin de Python ; non signés, SmartScreen peut donc
avertir), `chatstyle-linux.tar.gz` pour Linux (décompresser et lancer `./install.sh`), une
distribution des sources et `SHA256SUMS.txt` pour vérifier les téléchargements. Pour compiler à
partir des sources, lisez la suite.

Il vous faut Python 3.11+ et un compilateur C++17 : le cœur est compilé pendant l'installation
(CMake >= 3.20 ; pybind11 et scikit-build-core sont récupérés automatiquement). Tout le nécessaire
est listé dans [Prérequis](#prérequis).

```bash
git clone https://github.com/DomaCKBO3H9K/chatstyle.git
cd chatstyle
pip install .
```

Vérification :

```bash
chatstyle --version
```

Si le répertoire `Scripts` de votre Python n'est pas dans le `PATH`, appelez
`python -m chatstyle ...`.

### Windows

- Compilateur : **Visual Studio 2022 Build Tools** (la charge de travail « Développement Desktop
  en C++ ») ou **MinGW-w64**. Options de compilation MSVC : `/W4 /utf-8 /permissive-`.
- Avec MinGW-w64, choisissez le générateur Ninja (c'est ainsi que la compilation a été testée sur
  la machine de l'auteur) :

  ```powershell
  $env:CMAKE_GENERATOR = "Ninja"
  pip install .
  ```

- **Un `chatstyle.exe` déjà compilé** (environ 18 Mo, sans Python installé) sera joint aux
  versions. En attendant, vous pouvez le compiler vous-même (Python et un compilateur sont
  nécessaires, comme ci-dessus) :

  ```powershell
  pip install -e .
  powershell -File packaging\build_exe.ps1            # un seul fichier dist\chatstyle.exe
  powershell -File packaging\build_exe.ps1 -OneDir    # un dossier, pour le débogage
  python packaging/check_exe.py                       # vérifier l'exe compilé (Windows)
  dist\chatstyle.exe --version
  ```

  Un double-clic sur `chatstyle.exe` affiche l'aide et attend Entrée pour que la fenêtre ne se
  ferme pas instantanément (depuis `cmd` et PowerShell cela n'arrive pas ; avec
  `CHATSTYLE_NO_PAUSE=1` on désactive la pause). L'exe garde les fichiers de l'utilisateur dans
  `%APPDATA%\chatstyle`, pas à côté de lui. Un exe en un seul fichier est décompressé dans un
  dossier temporaire à chaque démarrage, donc il démarre en quelques secondes.

### Fenêtre de l'application

En plus de la ligne de commande, il y a une fenêtre : vous choisissez le fichier de l'auteur
inconnu et les candidats, vous appuyez sur « Сравнить » (Comparer) et vous voyez une échelle de
similarité avec des explications ; le deuxième onglet montre le profil de style d'un auteur. La
fenêtre n'utilise pas le réseau : la page est dans le paquet et les polices sont celles du
système.

```powershell
chatstyle gui                          # depuis le paquet installé
dist\chatstyle-gui.exe                 # un exe déjà compilé, sans fenêtre de console
dist\chatstyle-gui.exe --selftest r.txt  # une vérification sans afficher la fenêtre, le résultat va dans r.txt
```

La fenêtre repose sur pywebview et sur le moteur Microsoft Edge WebView2 intégré à Windows. Il est
déjà présent dans Windows 11 et dans un Windows 10 à jour ; sinon, un message avec un lien vers
l'installateur apparaît au démarrage. Pour compiler l'exe :
`powershell -File packaging\build_exe.ps1 -Target gui`. Vous pouvez vous connecter à Telegram
depuis la fenêtre (le bouton « Telegram » de l'en-tête, voir « Telegram via Telethon » plus bas) ;
un calcul ne peut pas être annulé. Le thème est clair ou sombre et la langue est russe, English,
العربية, Español, 中文 ou Français : par défaut celle du système, et les sélecteurs de l'en-tête
mémorisent le choix (l'arabe s'affiche de droite à gauche). Toute la fenêtre est traduite ; les
rapports et la sortie de la ligne de commande restent en russe, tout comme le texte détaillé des
erreurs du cœur. Les traductions n'ont pas été relues par des locuteurs natifs, les corrections
sont les bienvenues : les dictionnaires sont dans `python/chatstyle/gui/web/lang/`.

### Linux

Il vous faut `g++` (ou `clang++`), CMake >= 3.20 et les en-têtes Python :

```bash
sudo apt install build-essential cmake python3-dev   # Debian/Ubuntu
pip install .
```

La fenêtre (`chatstyle gui`) nécessite en plus GTK (`python3-gi gir1.2-webkit2-4.1`) ou Qt
(`pip install "pywebview[qt]"`) ; la ligne de commande fonctionne sans eux.

### Développement

```bash
pip install -e ".[dev]"          # pytest, ruff
pytest                           # tests Python
ruff check python tests experiments
cmake -S . -B build -DCHATSTYLE_BUILD_TESTS=ON -DCHATSTYLE_BUILD_PYTHON=OFF
cmake --build build
ctest --test-dir build           # tests du cœur (Catch2 est téléchargé à la configuration de CMake)
```

Pour les graphiques de `experiments/` en plus : `pip install -e ".[experiments]"`.

## Sources de données

Une source s'écrit `schéma:valeur`. Au moins un candidat est nécessaire pour une comparaison ;
`-c` peut être répété.

| Source | Exemple | Ce qui est pris |
|---|---|---|
| `file:` | `file:chat.txt` | Un fichier texte UTF-8, un message par ligne. |
| `tgexport:` | `tgexport:result.json#Anna Petrova` | Une exportation JSON d'une discussion de Telegram Desktop ; après `#` le nom de l'expéditeur, son `from_id` (`user111`) ou un id numérique. |
| `tg:` | `tg:@friend` ou `tg:@group#@person` | Messages via Telethon : une discussion privée avec un utilisateur, ou les messages d'une personne dans un groupe. |
| `chat:` | `chat:777#Anna Petrova` | Une personne d'une **discussion importée** (voir plus bas) : avant `#` l'id ou le titre de la discussion, après le nom du participant ou son `from_id`. |

Seuls les messages texte de l'expéditeur voulu sont pris : les messages transférés et de service
et les médias sans légende sont ignorés. Les liens et les mentions sont remplacés par des
étiquettes ; les messages vides et les marqueurs comme `[Фото]` sont écartés.

### Discussions importées

Pour ne pas avoir à ranger les exportations dans des dossiers à la main, importez l'exportation
d'une discussion une fois et elle reste dans la liste. Le `result.json` d'origine peut ensuite être
supprimé : seuls les textes et les heures des messages des participants sont conservés.

- **Dans la fenêtre :** l'onglet « Чаты » (Discussions), puis le bouton pour importer une
  exportation de discussion ; dans la comparaison et dans le profil il y a des boutons pour
  choisir parmi les discussions importées (on peut cocher plusieurs participants d'une discussion
  à la fois).
- **En ligne de commande :**

  ```
  chatstyle chats add result.json      importer une discussion (réimporter l'étend sans doublons)
  chatstyle chats list                 liste des discussions
  chatstyle chats list Friends         participants d'une discussion (nom, identifiant, nombre de messages)
  chatstyle chats remove Friends       retirer une discussion de la liste
  chatstyle compare -u chat:Friends#Ann -c chat:Friends#Bob -c chat:Friends#Vera
  ```

Une discussion se désigne par l'id de l'exportation ou par son titre (si deux discussions ont le
même titre, l'id est nécessaire), un participant par son nom ou son identifiant (`user111`). C'est
la même analyse que pour `tgexport:`, mais le fichier n'est lu qu'une fois. Les fichiers des
discussions se trouvent dans le répertoire de données (`chats/`) et sont **chiffrés**
(AES-256-GCM) : une clé aléatoire est conservée dans le coffre de secrets commun (le même que
celui qui contient la connexion Telegram : mot de passe maître ou DPAPI), donc le coffre doit être
ouvert avant de travailler avec les discussions. **Ni clés d'API ni connexion à Telegram ne sont
nécessaires pour cela :** dans l'onglet « Чаты » la fenêtre propose elle-même de configurer la
protection (mot de passe maître, DPAPI ou « uniquement pendant que la fenêtre est ouverte ») ou de
l'ouvrir avec le mot de passe maître ; la CLI demande la même chose. Un coffre protégé par mot de
passe maître se verrouille tout seul après 15 minutes d'inactivité dans l'onglet « Чаты ». Dans le
mode « uniquement pendant que la fenêtre est ouverte » les discussions vivent seulement en mémoire
et disparaissent à la fermeture de la fenêtre. Les discussions importées par des versions
antérieures (`*.json` en clair) sont chiffrées à la première ouverture du coffre et les copies en
clair sont écrasées. Un fichier est lié à son id : un fichier substitué ou modifié ne se déchiffre
pas.

### Telegram via Telethon

Le réseau n'est utilisé **qu'ici** et uniquement sur votre ordre explicite.

1. Obtenez un `api_id` et un `api_hash` sur <https://my.telegram.org> (section API development
   tools).
2. Connectez-vous une fois : la commande demande le mode de protection (mot de passe maître ou
   compte Windows), si besoin les clés `api_id`/`api_hash` (on peut aussi les donner par les
   variables d'environnement `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` ou un fichier `.env`), puis le
   téléphone, le code de Telegram et le mot de passe 2FA s'il est activé :

   ```bash
   chatstyle login
   ```

3. Comparez (si le coffre est protégé par un mot de passe maître, la commande le demande sans
   écho) :

   ```bash
   chatstyle compare -u tg:@stranger -c tg:@friend1 -c file:friend2.txt --limit 1000
   ```

**Depuis la fenêtre.** Le bouton « Telegram » de l'en-tête ouvre un assistant : le mode de
protection de la connexion, les clés (`api_id`, `api_hash`), le numéro de téléphone, le code de
Telegram et le mot de passe 2FA s'il est activé. Le code et les mots de passe ne sont jamais
enregistrés et les champs sont vidés juste après l'envoi. Après la connexion, les sources
gagnent « Из Telegram » (une discussion et, si besoin, un expéditeur), et la limite de messages
et « recharger » se trouvent dans « Дополнительно ». La connexion depuis la fenêtre et
`chatstyle login` utilisent le même coffre chiffré. « Выйти из Telegram » efface la session du
coffre et la termine côté Telegram ; « Удалить все данные Telegram » supprime aussi le coffre
lui-même. Les détails de la protection sont dans [Sécurité](#sécurité).

`--limit` (3000 par défaut) est le nombre maximal de messages par auteur ; ce qui est chargé est
mis en cache, une exécution répétée utilise le cache et `--refresh` recharge. Sans connexion,
`compare` avec `tg:` demande d'exécuter `chatstyle login`.

## Utilisation

```bash
chatstyle compare -u file:unknown.txt -c file:a.txt -c file:b.txt \
    --impostors outsider_texts/ --seed 1 --report report.html
chatstyle features file:chat.txt --top 10
chatstyle login
```

| Option de `compare` | Signification |
|---|---|
| `-u, --unknown` | la source de l'auteur inconnu |
| `-c, --candidate` | la source d'un candidat (peut être répétée) |
| `--impostors DIR` | un dossier de textes extérieurs pour General Impostors : **un fichier `.txt` par auteur** (UTF-8, un message par ligne) |
| `--seed N` | la graine de General Impostors (1 par défaut) : la même graine donne le même résultat |
| `--report FILE` | enregistrer un rapport ; le format est choisi par l'extension, `.md` ou `.html` |
| `--style-groups G` | groupes de traits de style pour Burrows Delta : `all` (par défaut), `none`, ou une liste séparée par des virgules de `punctuation`, `orthography`, `words`, `sentences` ; n'affecte pas le score final de General Impostors |
| `--morph` | ajouter une colonne « Части речи » (parties du discours) : similarité de n-grammes de parties du discours (1-4) ; nécessite le complément facultatif `pip install chatstyle[morph]` (pymorphy3), russe uniquement, n'affecte pas le score final |
| `--charlm` | ajouter une colonne « Языковая модель (бит/символ) » (modèle de langue, bits par caractère) : de combien de bits par caractère le texte de l'auteur inconnu est mieux prédit par le modèle de caractères de ce candidat que par le modèle des autres candidats (au-dessus de zéro signifie plus proche du candidat) ; nécessite au moins deux candidats non vides, n'affecte pas le score final |
| `--wordgrams` | ajouter une colonne « Слова (косинус) » (mots, cosinus) : similarité de n-grammes de mots (1-4 mots consécutifs, TF-IDF) ; les mots qu'un seul auteur possède ne sont pas distingués ; n'affecte pas le score final |
| `--emoji` | ajouter une colonne « Эмодзи (косинус) » (émojis, cosinus) : similarité des émojis que l'auteur emploie et de leur ordre (1-4 de suite ; les émojis composés avec teinte de peau et liaisons comptent pour un) ; un auteur sans aucun émoji n'a pas de score ; n'affecte pas le score final |
| `--rhythm` | ajouter une colonne « Ритм (по времени) » (rythme selon le temps) : similarité du rythme d'écriture (séries de messages, pauses, moment de la journée, week-ends) ; nécessite les dates des messages (sources `tgexport:` et `tg:` ; `file:` n'a pas de dates) et au moins 30 messages datés par auteur ; n'affecte pas le score final |
| `--lexical` | ajouter le vocabulaire à l'ensemble de méthodes (un modèle de langue de caractères ordinaire et des n-grammes de mots à la place du modèle de langue sur un texte sans mots rares) : un peu plus précis sur les discussions testées (98 % contre 95 %) mais plus sensible au sujet ; par défaut l'ordre est calculé uniquement d'après le style |
| `-n, --limit N`, `--refresh` | pour `tg:` : la limite de messages et le rafraîchissement du cache |

Quand la sortie est redirigée (`chatstyle compare ... > result.txt`), le texte est écrit en UTF-8.

**Parties du discours.** Dans `chatstyle.exe` et `chatstyle-gui.exe` elles sont incluses par défaut
(pymorphy3, environ +9 Mo ; une compilation sans elles : `powershell -File
packaging\build_exe.ps1 -NoMorph`). À l'exécution depuis les sources, le complément est
nécessaire : `pip install chatstyle[morph]`. La commande `chatstyle compare ... --morph` ajoute la
colonne « Части речи (косинус) », tandis que `chatstyle features ... --morph` et l'onglet « Profil
de style » de la fenêtre (la case « Учитывать части речи ») montrent les parts de noms, de
verbes, de particules et de mots hors dictionnaire. Python se contente d'étiqueter les mots avec
des codes d'une lettre de partie du discours (pymorphy3, en local, sans réseau), et le même cœur
compte les fréquences et les n-grammes sur les codes. L'étiquetage sans contexte est ambigu
(« мыла » est-ce un nom ou un verbe ?), et l'argot et les noms sont inconnus du dictionnaire, donc
le trait est bruité et n'affecte pas le score final. Dans la fenêtre les cases des parties du
discours, du modèle de langue, des n-grammes de mots, des émojis et du rythme sont cochées dès le
début (les parties du discours si elles sont dans la compilation) ; en ligne de commande ces
méthodes s'activent avec `--morph`, `--charlm`, `--wordgrams`, `--emoji`, `--rhythm`.

**Modèle de langue de caractères.** Pour chaque candidat, le cœur entraîne un modèle de caractères
(un contexte jusqu'à trois caractères, lissage Witten-Bell, casse conservée) et compte combien de
bits par caractère sont nécessaires pour « coder » le texte de l'auteur inconnu. On soustrait le
même chiffre pour le modèle des autres candidats : une valeur positive signifie que le texte est
plus proche de ce candidat. La quantité de texte d'entraînement est égalisée entre les candidats
(on ne prend pas plus que ce qu'a le plus court), sinon un long candidat gagnerait simplement par
sa taille. Avec un seul candidat, il n'y a pas de score. La méthode s'active avec `--charlm` ou la
case de la fenêtre et n'affecte pas encore le score final : son utilité sur des données réelles
n'a pas été mesurée.

**N-grammes de mots.** L'option `--wordgrams` (et la case de la fenêtre) calcule la même
similarité cosinus, mais sur des séquences de 1-4 mots plutôt que de caractères : les tournures
stables (« ну вообще », « в принципе ») comptent plus que les lettres isolées. Les mots sont mis en
minuscules ; un mot absent chez au moins deux auteurs de la comparaison ne peut rien confirmer et
est remplacé par une marque commune « mot rare ». Comme pour les parties du discours, Python ne
fait que remplacer les mots par des symboles et le même cœur compte les n-grammes. N'affecte pas
le score final ; son utilité sur des données réelles n'a pas été mesurée.

**Les émojis en détail.** Le trait « part d'émojis » du profil dit seulement s'il y en a beaucoup
ou peu. L'option `--emoji` (et la case de la fenêtre) compare *lesquels exactement* et dans quel
ordre : des messages ne restent que les émojis (les composés comptent pour entiers), chacun reçoit
un symbole, et le même cœur calcule le cosinus sur des n-grammes de 1-4. Un auteur sans émojis n'a
pas de score. N'affecte pas le score final.

**Rythme d'écriture dans le temps.** Si la source sait quand les messages ont été écrits (une
exportation de Telegram Desktop et le chargement `tg:`), le cœur calcule huit traits à partir des
heures de l'auteur : la part des pauses jusqu'à une minute, la longueur des séries de messages, la
pause typique (les pauses de plus de six heures, une coupure de nuit, ne sont pas comptées), les
parts de messages la nuit, le matin, l'après-midi et le soir, et la part des week-ends. L'heure est
« murale », comme à la montre de l'auteur (le fuseau horaire de l'ordinateur), donc il faut comparer
des exportations d'une personne et de son interlocuteur depuis le même appareil. Le profil
(`chatstyle features`, l'onglet « Profil de style ») montre le rythme automatiquement quand il
existe ; dans une comparaison on l'active avec `--rhythm`. Une série est formée des messages de
l'auteur avec des pauses jusqu'à une minute (les messages de l'interlocuteur ne sont pas visibles
dans la source). Les fichiers `file:` n'ont pas de dates, donc pas de rythme. N'affecte pas le
score final ; son utilité sur des données réelles n'a pas été mesurée. Le cache Telegram
conserve désormais aussi l'heure, donc un cache d'une version antérieure n'est pas lu et les
messages sont rechargés.

**Des habitudes, pas des fautes.** Les traits de ponctuation et d'orthographe mesurent les
*habitudes stables* de l'auteur (à quelle fréquence il étire des lettres, met une virgule avant une
conjonction, écrit « щас » ou « тся »), et non si quelque chose est écrit « correctement » : aucun
dictionnaire ni correcteur grammatical n'est utilisé, tout est calculé en local. Ce qui compte
pour la comparaison, c'est que les habitudes des deux textes coïncident. La liste des graphies
non standard (`python/chatstyle/resources/nonstandard_ru.txt`) a été établie à la main et n'a pas
été relue par des locuteurs natifs. Les traits ne servent que dans Burrows Delta et dans le profil
de style ; le score final de General Impostors reste calculé à partir de n-grammes de caractères.
Leur utilité sur des données réelles n'a pas été mesurée : les données synthétiques ne vérifient
que l'exactitude du comptage (voir « État et lacunes connues »).

### Comment lire le résultat

| Colonne | Signification |
|---|---|
| Сходство (similarité) | cosinus de n-grammes TF-IDF, 0..1, plus c'est grand plus c'est proche |
| Delta | Burrows Delta, plus c'est petit plus c'est proche ; comparable seulement entre candidats d'une même exécution |
| Impostors (итог) | le **score final** : la part de 100 itérations aléatoires où le texte du candidat est plus proche de l'inconnu que les textes de tous les extérieurs. Un nombre 0..1, mais **pas une probabilité** |
| Смесь (ensemble de méthodes) | l'**ordre des candidats** : la moyenne des scores z de trois signaux sur des candidats de même taille : le « squelette » de mots grammaticaux, Delta et un modèle de langue de caractères sur un texte sans mots rares (avec `--lexical`, à la place du dernier, un modèle de langue ordinaire et des n-grammes de mots) ; plus c'est grand plus c'est proche ; la valeur est relative à l'ensemble des candidats de cette exécution. Avec deux candidats, c'est la part des « votes » des méthodes : +1 tous pour, -1 tous contre |

S'il y a au moins deux candidats, les lignes sont triées selon l'ensemble de méthodes de style ;
sinon selon Impostors (s'il est disponible pour tous), sinon selon le cosinus TF-IDF. Pour qu'un
grand candidat ne gagne pas uniquement grâce à la taille de son vocabulaire, l'ensemble de méthodes
est calculé sur des candidats de même taille : on prend chez chacun des messages aléatoires
jusqu'à 2500 mots (mais pas moins que ce qu'a le candidat le plus court). Les colonnes « Сходство »,
« Delta » et « Impostors (итог) » restent calculées sur tout le texte. Dans la fenêtre la barre
montre la proximité *relative* des candidats (un softmax de l'ensemble de méthodes à la
température 1,0, les parts totalisent 1) ; ce n'est pas la probabilité de paternité. La ligne
« Лучший по методам » (meilleur selon les méthodes) montre si les méthodes s'accordent. Quand
elles divergent, c'est une information en soi : ne choisissez pas la méthode qui vous plaît.

Quand des méthodes sont indisponibles (un tiret) :

- **Delta :** il faut au moins 6 morceaux de 200 mots pour toute la comparaison (environ 600 mots
  pour deux auteurs).
- **General Impostors :** il faut au moins 3 auteurs extérieurs (les autres candidats plus le
  dossier `--impostors`) et au moins 2 morceaux de 200 mots de l'auteur inconnu et du candidat.
  Dans une exécution « inconnu + 2 candidats » il y a un extérieur par candidat, donc sans
  `--impostors` il n'y aura pas de score final : c'est voulu.

## Exemple de rapport

[`docs/example_report.md`](docs/example_report.md) est un rapport sur des données **fictives** (pas
une vraie conversation). Pour le reproduire :

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

Le rapport (`.md` et un `.html` autonome sans ressources externes) contient : le tableau des
candidats, une explication du score final, les 20 principaux n-grammes concordants (les lettres
isolées et l'espace sont masqués car peu informatifs), les principales différences de style selon
Delta sous des noms lisibles, les paramètres de l'exécution (graine, nombre d'extérieurs), une
description de la méthode et les limites.

## Évaluation de la qualité

**Il n'y a pas encore de résultats.** Des chiffres honnêtes exigent des textes réels étiquetés de
plusieurs auteurs, et le projet n'a pas un tel corpus. Tout nombre obtenu sur des données
inventées ne dirait rien de la qualité sur de vraies conversations, donc il n'y en a volontairement
aucun ici.

**Une vérification sur vos propres discussions.** Si vous avez importé plusieurs discussions
(l'onglet « Чаты » ou `chatstyle chats add`), vous pouvez vérifier sur elles l'ordre des candidats
sans aucun étiquetage :

```bash
python -m experiments.chats_eval            # l'ensemble de méthodes de style (par défaut)
# lit le coffre chiffré (demande le mot de passe maître) ; --chats-dir DOSSIER désigne des fichiers de discussion en clair
python -m experiments.chats_eval --lexical  # l'ensemble de méthodes avec vocabulaire
```

Le même identifiant de participant dans des discussions différentes compte pour une seule
personne ; deux types de tâches sont construits : « entre contextes » (une personne d'une
discussion contre les autres, dont les textes sont pris dans d'autres discussions) et « dans le
temps » (les derniers messages contre le reste). Seuls des nombres sont affichés (la part de
premières places, le MRR, la part en devinant au hasard), ni noms ni textes. Cela ne remplace pas
une évaluation sur un corpus étiqueté (voir les réserves dans « État et lacunes connues »), mais
permet de revérifier le comportement de l'algorithme sur vos propres données.

Les outils d'évaluation sont prêts (`experiments/`) et testés sur des données synthétiques :

```bash
# jeu de données : un dossier, un fichier .txt par auteur, noms anonymes, messages dans l'ordre
python -m experiments.evaluate DATASET --words 1000 --impostors 10 --jobs 4 --output results.json
python -m experiments.volume DATASET --slices 250 500 1000 2000 5000 --jobs 4   # qualité selon le volume, et un graphique
python -m experiments.prepare_tgexport result.json DATASET --min-messages 300   # un jeu de données à partir d'une discussion de groupe
```

Pour chaque méthode on calcule l'ROC AUC (avec un intervalle de confiance, bootstrap sur les
auteurs) et la précision avec un seuil choisi sur d'autres données. Pour le débogage, il existe
`python -m experiments.make_synthetic DOSSIER` ; ces données sont marquées, et les scripts
avertissent deux fois que les nombres ne doivent pas être publiés.

Les nouveaux groupes de traits de style (ponctuation, orthographe, mots, phrases) peuvent être
vérifiés un par un : `python -m experiments.ablation DATASET` calcule l'AUC de Burrows Delta sans
groupes, avec chaque groupe et avec tous, et `python -m experiments.evaluate DATASET
--style-groups words,sentences` lance l'évaluation habituelle avec les groupes choisis. Un jeu de
données avec des auteurs dotés d'habitudes d'écriture intégrées est créé par
`python -m experiments.make_synthetic DOSSIER --habits`. Tant qu'il n'y a pas de corpus, une telle
exécution prouve seulement que les groupes changent réellement le score, pas qu'ils sont utiles
sur des personnes.

Le seuil de l'avertissement « moins de 1000 mots » est provisoire pour l'instant : il sera précisé
d'après les résultats d'une évaluation sur des données réelles.

## Limites

- **L'estimation est probabiliste.** C'est une mesure de la similarité de style, pas une preuve.
  Un score élevé ne signifie pas le même auteur, et un score bas ne signifie pas des auteurs
  différents.
- **La quantité de texte compte beaucoup.** Avec un faible volume (moins de 1000 mots d'un côté ou
  de l'autre) le score peut être aléatoire ; avec un volume très faible, Delta et General
  Impostors ne sont pas disponibles.
- **Le score final dépend des « extérieurs ».** S'ils sont peu nombreux ou s'ils diffèrent de
  l'environnement réel de communication, le score est faussé.
- **Le style dépend du contexte.** Une même personne écrit différemment dans différentes
  discussions, et des personnes différentes d'un même cercle, âge et sujet écrivent de façon
  semblable.
- **Langues.** Les lettres et la casse sont déterminées d'après les tables Unicode 16 (latin avec
  diacritiques, grec, arménien, géorgien, arabe, hébreu, écritures indiennes et autres), donc les
  méthodes fondées sur les caractères (cosinus, modèle de langue, « squelette ») fonctionnent avec
  n'importe quelle écriture ; en chinois et en japonais (idéogrammes et kana) chaque signe compte
  pour un mot. **Mais la précision n'a été vérifiée qu'en russe.** Sur des données synthétiques
  pour neuf langues (anglais, français, allemand, espagnol, polonais, grec, arabe, chinois,
  japonais), des auteurs au vocabulaire différent sont distingués ; c'est une vérification que cela
  fonctionne, pas de la précision. Delta s'appuie sur des listes russes de mots grammaticaux, de
  tics de langage et de « graphies non standard » et sur des traits comme « тся/ться » et « ё/е »,
  donc dans les autres langues il ne reste que les traits indépendants de la langue (ponctuation,
  casse, longueurs) ; les parties du discours (`--morph`) ne concernent que le russe. Dans les
  autres langues il vaut mieux activer `--lexical`. Pour le thaï, le lao, le khmer et le birman
  (écritures sans espaces qui ne sont pas des idéogrammes) un mot reste une suite de lettres. Le
  passage en minuscules suit les règles simples d'Unicode : le İ turc et les cas particuliers
  semblables ne sont pas modifiés.
- **Distorsions des données d'origine :** les comptes partagés, les robots, les citations, les
  messages transférés et le texte collé influent sur le résultat ; les messages transférés de
  Telegram ne sont pas comptés, mais les citations à l'intérieur de messages ordinaires restent.
- **L'imitation délibérée du style d'autrui et la paraphrase du texte n'ont pas été évaluées**
  (prévu pour une version ultérieure).
- **Les horodatages** ne sont nécessaires que pour le rythme (`--rhythm`) : les fichiers texte
  n'en ont pas.
- Les fichiers texte ne sont lus qu'en UTF-8 ; un fichier dans un autre encodage est rejeté avec un
  message clair plutôt que lu de façon déformée.
- La méthode est fermée : elle compare avec les candidats que vous avez nommés. Le véritable auteur
  peut ne pas en faire partie.

## Éthique et vie privée

- **Tout est calculé en local.** Le seul accès au réseau est Telegram (Telethon), et uniquement sur
  ordre explicite : `chatstyle login` et `compare`/`features` avec une source `tg:`. Il n'y a pas
  de télémétrie.
- **Quels fichiers le programme crée.** Dans le répertoire de données (`%APPDATA%\chatstyle` sous
  Windows, `~/.local/share/chatstyle` ou `$XDG_DATA_HOME/chatstyle` sous Linux ; modifiable par la
  variable `CHATSTYLE_HOME`) :
  - `vault.json` est le coffre **chiffré** : les clés de l'API Telegram et la session (qui
    équivaut à un accès à votre compte), voir [Sécurité](#sécurité) ;
  - `cache/` est un cache de messages chargés de **personnes réelles** (non chiffré) ;
  - `chats/` contient les discussions importées (l'onglet « Чаты », `chatstyle chats add`) :
    textes et heures de messages de **personnes réelles**, **chiffrés** avec la clé du coffre
    (`*.chat`) ;
  - `gui-settings.json` est la langue et le thème de la fenêtre ;
  - `.env` contient les clés `api_id` et `api_hash`, uniquement si vous les y avez mises vous-même.

  Pour tout supprimer, supprimez ce répertoire (et terminez la session dans les paramètres de
  Telegram : « Appareils »).
- **Les rapports contiennent des fragments de conversations** (n-grammes) et les noms des sources.
  Ne les publiez pas et ne les transmettez pas sans le consentement des auteurs des messages. Les
  noms de fichiers du dossier `--impostors` n'entrent pas dans le rapport.
- **Les conversations d'autrui sont des données personnelles.** Avant d'analyser une discussion,
  obtenez le consentement de ses participants et vérifiez que les lois de votre pays le permettent.
  Le projet ne donne pas de conseils juridiques.
- **Le dépôt ne doit pas contenir** `.env`, de fichiers `.session`, le cache ni de conversations
  réelles ; ils sont exclus dans `.gitignore`. Ne les ajoutez pas aux commits ni aux exemples.
- **À quoi l'outil n'est pas destiné :** désanonymiser des personnes contre leur gré, la
  surveillance, la pression et le harcèlement, étayer des accusations sans autres preuves, faire
  passer le résultat pour une preuve de paternité.

## Sécurité

**Contre quoi cela protège.** Les autres utilisateurs de cet ordinateur, le vol ou la copie du
disque et du dossier de données, la synchronisation dans le cloud, la publication accidentelle de
fichiers, la falsification de la page de la fenêtre et l'interception du trafic vers Telegram.
**Contre quoi cela ne protège pas.** Un logiciel malveillant exécuté sous votre compte, un
enregistreur de frappe ou un enregistrement d'écran : s'ils sont présents, aucun programme ne peut
garder de secrets. Contre une telle menace, choisissez le mode « uniquement pendant que la fenêtre
est ouverte » et activez la protection à deux facteurs dans Telegram.

- **Trois façons de conserver la connexion** (`chatstyle login` ou l'assistant de la fenêtre) :
  - *mot de passe maître* (recommandé) : les clés et la session sont chiffrées en AES-256-GCM, la
    clé est dérivée du mot de passe avec scrypt (64 Mo, environ 0,3 s par essai), le mot de passe
    n'est stocké nulle part, les essais ralentissent après trois saisies erronées ; le coffre se
    verrouille tout seul après 15 minutes d'inactivité ;
  - *compte Windows* (DPAPI) : pas de mot de passe nécessaire, mais n'importe quel programme sous
    votre compte peut déchiffrer la connexion ;
  - *uniquement pendant que la fenêtre est ouverte* : rien n'est écrit sur le disque, et à la
    fermeture de la fenêtre la session est terminée côté Telegram.
- **Nous n'écrivons pas nous-mêmes de cryptographie :** AES-GCM vient de la bibliothèque
  `cryptography`, scrypt du `hashlib` standard, DPAPI est un appel système de Windows. Le fichier
  du coffre est authentifié : la corruption ou la falsification de l'en-tête est détectée. Un mot
  de passe maître oublié ne peut pas être récupéré : on se reconnecte.
- **Les discussions importées sont chiffrées** par le même coffre : la clé AES-256-GCM (256 bits,
  aléatoire) se trouve dans `vault.json`, pas à côté des fichiers ; sans le coffre ouvert, les
  discussions ne peuvent pas être lues. Supprimer une discussion écrase le fichier avec des zéros
  (sur un SSD cela ne garantit pas l'effacement physique). Si un logiciel malveillant s'exécute
  sous votre compte pendant que le coffre est ouvert, il obtiendra aussi les discussions, comme il
  obtiendrait la session Telegram. Le mode « uniquement pendant que la fenêtre est ouverte » ne
  garde les discussions qu'en mémoire.
- **Droits :** le dossier de données est fermé à tous sauf à votre compte (sous Windows via
  `icacls`, sous Linux avec les droits `0700`/`0600`).
- **La fenêtre :** la page est chargée depuis un fichier à l'intérieur du paquet, pas depuis un
  serveur local : le processus n'a aucun port en écoute (l'autotest le vérifie). Une politique CSP
  interdit toute requête réseau de la page, la navigation vers d'autres adresses est bloquée, le
  stockage du navigateur et la saisie automatique ne sont pas utilisés (mode privé de WebView2) et
  les outils de développement sont désactivés. Les fichiers ne se choisissent que dans les
  dialogues de la fenêtre, seuls les rapports qu'elle a elle-même créés sont ouverts, et tout ce
  qui vient de la page est vérifié en type et en longueur.
- **La compilation :** les dépendances sont figées par version et empreinte
  (`packaging/requirements.lock`, installées avec `pip install --require-hashes`), `pip-audit`
  n'a trouvé aucune vulnérabilité connue au moment de la rédaction, et `dist/SHA256SUMS.txt` est
  créé à côté de l'exe. **L'exe n'est pas signé** (un certificat est nécessaire), donc SmartScreen
  peut avertir au premier démarrage.
- **Fichiers en clair de la version précédente** (`telegram.session`, `telegram.account`) : la
  fenêtre propose de les supprimer quand elle les trouve, car ils ne sont pas chiffrés. Le cache
  des messages Telegram (`cache/`) n'est pas encore chiffré non plus.

## Organisation du projet

- **Le cœur (`core/`, C++17) :** calculs sur le texte comme séquence de points de code Unicode
  (UTF-8 vers `std::u32string`), n-grammes, TF-IDF, cosinus, Burrows Delta, General Impostors,
  explications. Le cœur ne sait rien des fichiers, de Telegram ni des rapports. Le lien avec
  Python est pybind11 (`chatstyle._core`).
- **Python (`python/chatstyle/`) :** collecteurs (txt, exportation Telegram, Telethon),
  prétraitement, le pipeline, la CLI (typer, rich), rapports. Python ne calcule pas lui-même les
  traits.
- **Divers :** `tests/` (pytest), `core/tests/` (Catch2), `experiments/` (évaluation de la qualité,
  ne fait pas partie du paquet), `packaging/` (PyInstaller), `docs/` (l'exemple de rapport et les
  discussions fictives), `.github/workflows/`.

## État et lacunes connues

Cette section est provisoire et doit disparaître avant la v1.0. Une liste honnête de ce qui **n'est
pas vérifié** :

- **La CI** (GitHub Actions) est au vert sous Windows (MSVC, Python 3.12) et Ubuntu (Python 3.11
  et 3.12) : analyse du style du code, tests Python, tests du cœur, et compilation et exécution
  d'un wheel. En local le projet a aussi été vérifié sous Windows 10 avec MinGW-w64 (Python 3.14).
  La fenêtre n'est pas couverte par la CI sous Linux (pas d'écran, et le test de la fenêtre y est
  ignoré) ; l'installation sous Linux (compilation du cœur, exécution de `chatstyle`) a aussi été
  vérifiée à la main sous Kali Linux.
- **Le collecteur Telegram n'a été vérifié que sur des simulations**, sans compte réel.
- **Les exe pour Windows.** Le flux de travail de la version compile `chatstyle.exe` et
  `chatstyle-gui.exe` avec MSVC sur un runner GitHub et y exécute des tests rapides (`--version`,
  `compare`, l'autotest de la fenêtre). Les compilations de la version ont aussi été lancées à la
  main sur la machine Windows 10 de l'auteur et fonctionnent. Une compilation locale MinGW-w64 a
  en plus passé `packaging/check_exe.py` (la version et l'icône dans les propriétés du fichier, un
  `PATH` sans Python, la lecture de `.env` depuis `%APPDATA%\chatstyle`, la sortie dans une vraie
  console de 80 colonnes de large, la pause au démarrage par double-clic) ; sur le runner ce script
  s'exécute sans vraie console, donc son résultat n'est qu'indicatif. **Non vérifié :** un Windows
  10 propre sans Python installé du tout (Windows Sandbox convient : y copier un seul
  `chatstyle.exe` et lancer `chatstyle --version` et `compare`).
- **Le cas qui a lancé le projet (un seul cas, pas une preuve).** Une connaissance a perdu l'accès à son compte Telegram principal et a continué à écrire depuis un second compte, un « jumeau ». L'auteur a comparé les messages du jumeau avec cinq candidats : le compte d'origine, l'auteur lui-même et trois autres connaissances. La première version, brute, de l'outil (seulement la similarité cosinus, Burrows Delta et General Impostors) a placé le véritable auteur **3e**. Après l'ajout des autres méthodes (parties du discours, modèle de langue de caractères, n-grammes de mots, émojis, rythme d'écriture et l'ensemble de méthodes de style), le véritable auteur est arrivé **1er**. C'est un seul cas, et les méthodes ont été mises au point en regardant ces mêmes données et des données semblables ; il montre donc pourquoi les méthodes supplémentaires ont été ajoutées, pas que l'outil fera pareil pour vous.
- **L'évaluation sur des données réelles est un seul environnement de conversation, et le choix de
  la méthode a été ajusté dessus.** La vérification a porté sur les discussions d'un utilisateur :
  deux groupes (202 et 16 participants) et des discussions privées. Tâches : une personne d'un
  contexte (discussion) contre les autres personnes dont les textes sont pris dans d'autres
  discussions (25 tâches), une coupure dans le temps au sein d'un groupe (16) et un cas réel de
  « compte jumeau » (2) ; tous les candidats ont 2500 mots, le texte inconnu a 600-1400 mots et il
  y a 10 à 36 candidats. Première place du véritable auteur : l'ensemble complet avec vocabulaire
  (modèle de langue, mots, « squelette », Delta) 95 % (MRR 0,97), l'ensemble de style (celui par
  défaut : « squelette », Delta, modèle de langue sans mots rares) 91 % (MRR 0,93) ; sur les
  tâches « entre contextes » c'est 92 % contre 84 % : l'ensemble de style paie quelques points
  pour son indépendance vis-à-vis du sujet (sur 129 exécutions « le véritable auteur et 3 rivaux »
  l'ensemble complet obtient 98 %, celui de style 95 %) ; séparément le modèle de langue 88 %, les
  n-grammes de mots 88 %, Delta 72 %, « squelette » 72 %, Impostors avec les autres candidats
  comme extérieurs 58 %, le cosinus TF-IDF 56 %. Si l'on garde le véritable auteur et 3 rivaux
  au hasard (129 exécutions, le hasard donne 25 %) : l'ensemble complet 98 %, Delta 88 %, cosinus
  84 %, Impostors 75 %. Les poids ajustés de l'ensemble n'ont pas été meilleurs que des poids égaux
  (une vérification « laisser une personne de côté », la différence dans le bruit), et l'ajout d'un
  « fond » de dizaines d'auteurs extérieurs pour les scores z n'a rien changé, donc les poids sont
  égaux et il n'y a pas de fond.
  **Comment le prendre :** c'est un seul environnement (discussions en russe d'un même cercle, avec
  beaucoup de mots et de sujets communs), les tâches dépendent les unes des autres, et les quatre
  méthodes ont été choisies parmi une dizaine sur les mêmes données, donc les chiffres sont
  optimistes et peuvent ne pas se transposer à d'autres personnes, langues et volumes. Le modèle de
  langue et les n-grammes de mots sont sensibles au vocabulaire et au sujet (en partie compensé par
  le fait que l'inconnu et les candidats sont pris dans des discussions différentes) ; le
  « squelette » et Delta dépendent peu du sujet.
  **De combien de texte a-t-on besoin** (tâches « entre contextes » et réelles, 27 tâches, bruit
  d'environ ±7 points). Le texte de l'auteur inconnu, première place de l'ensemble de style / de
  l'ensemble avec vocabulaire : 300 mots 67 % / 70 %, 600 70 % / 93 %, 1000 85 % / 96 %, 2000
  81 % / 96 %, 4000 89 % / 93 %. L'ensemble de style ne progresse guère avec plus de texte (sur ces
  données il plafonne à 85-90 %), alors que le vocabulaire donne déjà plus de 93 % à 600 mots : si
  l'auteur inconnu a moins de 1000 mots, utilisez `--lexical` (le programme le rappelle lui-même
  par une indication dans le tableau, les rapports et la fenêtre). Volume des candidats (égal pour
  tous) : 2500 mots chacun 93 % / 98 %, 5000 86 % / 93 %, 10000 88 % / 95 % ; plus les volumes sont
  mal égalisés, plus le résultat est mauvais, c'est pourquoi le plafond par défaut est de 2500 mots
  (mais pas moins que ce qu'a le plus court). Différents échantillons aléatoires de messages du
  même volume donnent une dispersion supplémentaire de 2-3 points. Une première vérification sur 5
  candidats favorisait la « Delta cosinus » ; sur 36 candidats cela ne s'est pas confirmé : la
  conclusion tirée d'un petit échantillon s'est révélée fausse et cette méthode n'est plus dans le
  programme.

## Références

- Burrows J. *Delta: a Measure of Stylistic Difference and a Guide to Likely Authorship.*
  Literary and Linguistic Computing, 17(3), 2002.
- Koppel M., Winter Y. *Determining if two documents are written by the same author.*
  Journal of the Association for Information Science and Technology, 65(1), 2014.

## Licence

MIT, voir [`LICENSE`](LICENSE).
