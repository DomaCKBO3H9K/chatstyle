# chatstyle

[English](README.md) | [Русский](README.ru.md) | **Español** | [Français](README.fr.md) | [中文](README.zh.md) | [العربية](README.ar.md)

Una herramienta de línea de comandos (con ventana de escritorio) para verificar la autoría de
mensajes de chat en ruso. Responde a la pregunta: «¿los mensajes de un remitente desconocido los
escribió la misma persona que los mensajes de un candidato?», y muestra en qué rasgos se basa la
respuesta.

> **El resultado es una estimación estadística de la similitud de estilo, no una prueba de
> autoría.** Puede equivocarse, depende de la cantidad de texto y no debe usarse como único
> fundamento para sacar conclusiones sobre personas. Véanse [Limitaciones](#limitaciones) y
> [Ética y privacidad](#ética-y-privacidad).

> **Estado: versión 0.1, antes del lanzamiento v1.0.** Todavía no hay resultados de calidad sobre
> datos reales, véanse [Evaluación de la calidad](#evaluación-de-la-calidad) y
> [Estado y lagunas conocidas](#estado-y-lagunas-conocidas).

La salida de la línea de comandos, los informes y los mensajes de error están en ruso (la propia
ventana está traducida a seis idiomas). Los ejemplos siguientes muestran la salida real tal cual.

## Qué hace

- **Un conjunto de métodos basado en el estilo.** Por defecto los candidatos se ordenan con: un
  «esqueleto» de palabras funcionales, Burrows Delta y un modelo de lenguaje sobre un texto en el
  que las palabras raras están enmascaradas (así el tema apenas influye), con pesos iguales de
  puntuaciones z. La opción `--lexical` añade el vocabulario (véase «Cómo leer el resultado»). La
  comprobación con chats reales está en «Estado y lagunas conocidas».
- **Tres métodos de comparación** (todos se calculan en local):
  - similitud coseno de n-gramas de caracteres TF-IDF (1-4), el método base, con una explicación
    de qué n-gramas coincidieron;
  - **Burrows Delta** sobre rasgos de estilo: hábitos de puntuación (paréntesis «)», «))», puntos
    suspensivos, «!!», «??», comas y conjunciones, espacios alrededor de los signos, rayas,
    comillas), mayúsculas y ortografía (MAYÚSCULAS SOSTENIDAS, palabras alargadas, la grafía
    «тся/ться», mezcla de cirílico y latino, espacios dobles, grafías no estándar), «ё»/«е»,
    letras latinas, emoji, riqueza de vocabulario, longitud de palabras, frases y mensajes,
    frecuencias de palabras funcionales y muletillas (unos 40 rasgos en total; también forman el
    perfil de estilo);
  - **General Impostors**: si el texto del candidato está de forma constante más cerca del
    desconocido que los textos de autores ajenos. Su puntuación (0..1) es la **puntuación final**.
- **Tres fuentes de datos:** un archivo de texto, una exportación JSON de Telegram Desktop,
  Telegram mediante Telethon.
- **Informes** en Markdown y HTML: una tabla, los rasgos coincidentes principales, diferencias de
  estilo, una descripción del método.
- **Perfil de estilo** de un solo autor: `chatstyle features`.
- Una advertencia si alguno de los lados tiene menos de 1000 palabras.

## Inicio rápido

El repositorio contiene pequeños archivos ficticios `tests/fixtures/*.txt` (un mensaje por línea).
Tras la [instalación](#instalación):

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

Encabezados de columna: «Кандидат» es el candidato, «Слов» palabras, «Сообщений» mensajes,
«Сходство» similitud, «Impostors (итог)» la puntuación final de General Impostors, «Смесь» el
conjunto de métodos.

Un guion significa que el método no está disponible: hay muy poco texto (aquí entre 80 y 120
palabras por autor), así que el programa no inventa un número, sino que explica qué falta. Un
ejemplo completo con los tres métodos está en [Informe de ejemplo](#informe-de-ejemplo).

## Requisitos

chatstyle es un núcleo en C++17 con una interfaz en Python, así que hacen falta dos grupos de
cosas: herramientas para **compilar** el núcleo una vez (durante `pip install`) y bibliotecas para
**ejecutar** el programa.

**Se instalan a mano (herramientas del sistema):**

| Qué | Versión | Para qué | Dónde conseguirlo |
|---|---|---|---|
| Python | 3.11 o superior (3.12 en CI, 3.14 probado en local) | el propio programa | python.org, o `apt install python3 python3-venv` |
| Un compilador C++17 | MSVC (Visual Studio 2022 Build Tools), MinGW-w64, GCC o Clang | compila el núcleo | Windows: Build Tools con la carga de trabajo «Desarrollo para el escritorio con C++»; Linux: `apt install build-essential` |
| CMake | 3.20 o superior | compila el núcleo | cmake.org, `apt install cmake` o `pip install cmake` |
| Cabeceras de Python | las de tu versión de Python | hacen falta para compilar el módulo de Python | Linux: `apt install python3-dev`; en Windows vienen con Python |
| Ninja | cualquiera (opcional) | el generador de compilación solo para MinGW-w64 | `pip install ninja` o tu gestor de paquetes |
| git | cualquiera (opcional) | solo para clonar el repositorio y descargar Catch2 al compilar las pruebas de C++ | git-scm.com |

**Se instalan automáticamente con `pip install .`:**

| Paquete | Para qué |
|---|---|
| `scikit-build-core` (>= 0.10), `pybind11` (>= 3.0) | compilar el núcleo (solo en tiempo de compilación; se descargan a un entorno de compilación aislado) |
| `typer` (>= 0.12), `rich` (>= 13) | la línea de comandos y las tablas |
| `telethon` (>= 1.36) | acceso a Telegram (solo se usa cuando tú lo ordenas) |
| `pywebview` (>= 5) | la ventana de la aplicación |
| `cryptography` (>= 42) | cifrado AES-256-GCM del almacén y de los chats cargados |

El primer `pip install` necesita acceso a internet para descargar estos paquetes; después el
programa funciona sin conexión (salvo Telegram).

**Extras opcionales** (`pip install ".[nombre]"`):

| Extra | Paquetes | Para qué |
|---|---|---|
| `morph` | `pymorphy3`, `pymorphy3-dicts-ru` | categorías gramaticales (`--morph`, solo ruso) |
| `dev` | `pytest`, `ruff` | pruebas y análisis de estilo del código |
| `experiments` | `matplotlib` | gráficos en `experiments/` |

**Solo para la ventana** (`chatstyle gui`; la línea de comandos no lo necesita):

- Windows: el runtime Microsoft Edge WebView2 (ya incluido en Windows 11 y en Windows 10 al día).
- Linux: GTK con WebKit (`apt install python3-gi gir1.2-webkit2-4.1`) o Qt
  (`pip install "pywebview[qt]"`).
- macOS no se ha probado.

El `chatstyle.exe` ya compilado para Windows (véase más abajo) no necesita nada de esto: incluye
Python y todas las bibliotecas.

## Instalación

**Los archivos ya compilados** están adjuntos a cada versión en la
[página de Releases](https://github.com/DomaCKBO3H9K/chatstyle/releases): `chatstyle.exe` y
`chatstyle-gui.exe` para Windows (no hace falta Python; no están firmados, así que SmartScreen
puede avisar), `chatstyle-linux.tar.gz` para Linux (descomprimir y ejecutar `./install.sh`), una
distribución de código fuente y `SHA256SUMS.txt` para verificar las descargas. Para compilar desde
el código fuente, sigue leyendo.

Necesitas Python 3.11+ y un compilador C++17: el núcleo se compila durante la instalación
(CMake >= 3.20; pybind11 y scikit-build-core se descargan solos). Todo lo necesario está en
[Requisitos](#requisitos).

```bash
git clone https://github.com/DomaCKBO3H9K/chatstyle.git
cd chatstyle
pip install .
```

Comprobación:

```bash
chatstyle --version
```

Si el directorio `Scripts` de tu Python no está en el `PATH`, llama a `python -m chatstyle ...`.

### Windows

- Compilador: **Visual Studio 2022 Build Tools** (la carga de trabajo «Desarrollo para el
  escritorio con C++») o **MinGW-w64**. Opciones de compilación de MSVC: `/W4 /utf-8 /permissive-`.
- Con MinGW-w64 elige el generador Ninja (así se probó la compilación en la máquina del autor):

  ```powershell
  $env:CMAKE_GENERATOR = "Ninja"
  pip install .
  ```

- **Un `chatstyle.exe` ya compilado** (unos 18 MB, no necesita Python instalado) se adjuntará a
  las versiones. Mientras tanto puedes compilarlo tú (hacen falta Python y un compilador, como
  arriba):

  ```powershell
  pip install -e .
  powershell -File packaging\build_exe.ps1            # un solo archivo dist\chatstyle.exe
  powershell -File packaging\build_exe.ps1 -OneDir    # una carpeta, para depurar
  python packaging/check_exe.py                       # comprobar el exe compilado (Windows)
  dist\chatstyle.exe --version
  ```

  Al hacer doble clic en `chatstyle.exe` se muestra la ayuda y se espera a Enter para que la
  ventana no se cierre al instante (desde `cmd` y PowerShell no ocurre; con
  `CHATSTYLE_NO_PAUSE=1` se desactiva la pausa). El exe guarda los archivos del usuario en
  `%APPDATA%\chatstyle`, no junto a sí mismo. Un exe de un solo archivo se descomprime en una
  carpeta temporal en cada arranque, así que arranca en un par de segundos.

### Ventana de la aplicación

Además de la línea de comandos hay una ventana: eliges el archivo del autor desconocido y los
candidatos, pulsas «Сравнить» (Comparar) y ves una escala de similitud con explicaciones; la
segunda pestaña muestra el perfil de estilo de un autor. La ventana no usa la red: la página está
dentro del paquete y las fuentes son las del sistema.

```powershell
chatstyle gui                          # desde el paquete instalado
dist\chatstyle-gui.exe                 # un exe ya compilado, sin ventana de consola
dist\chatstyle-gui.exe --selftest r.txt  # una comprobación sin mostrar la ventana, el resultado va a r.txt
```

La ventana se basa en pywebview y en el motor Microsoft Edge WebView2 integrado en Windows. Ya
está presente en Windows 11 y en Windows 10 al día; si no, al arrancar aparece un mensaje con un
enlace al instalador. Para compilar el exe: `powershell -File packaging\build_exe.ps1 -Target gui`.
Puedes iniciar sesión en Telegram desde la ventana (el botón «Telegram» de la cabecera, véase
«Telegram mediante Telethon» más abajo); un cálculo no se puede cancelar. El tema es claro u
oscuro y el idioma es ruso, English, العربية, Español, 中文 o Français: por defecto el del sistema,
y los selectores de la cabecera recuerdan la elección (el árabe se muestra de derecha a
izquierda). Toda la ventana está traducida; los informes y la salida de la línea de comandos
siguen en ruso, igual que el texto detallado de los errores del núcleo. Las traducciones no las
han revisado hablantes nativos, se agradecen correcciones: los diccionarios están en
`python/chatstyle/gui/web/lang/`.

### Linux

Necesitas `g++` (o `clang++`), CMake >= 3.20 y las cabeceras de Python:

```bash
sudo apt install build-essential cmake python3-dev   # Debian/Ubuntu
pip install .
```

La ventana (`chatstyle gui`) necesita además GTK (`python3-gi gir1.2-webkit2-4.1`) o Qt
(`pip install "pywebview[qt]"`); la línea de comandos funciona sin ellos.

### Desarrollo

```bash
pip install -e ".[dev]"          # pytest, ruff
pytest                           # pruebas de Python
ruff check python tests experiments
cmake -S . -B build -DCHATSTYLE_BUILD_TESTS=ON -DCHATSTYLE_BUILD_PYTHON=OFF
cmake --build build
ctest --test-dir build           # pruebas del núcleo (Catch2 se descarga al configurar CMake)
```

Para los gráficos de `experiments/` además: `pip install -e ".[experiments]"`.

## Fuentes de datos

Una fuente se indica como `esquema:valor`. Para comparar hace falta al menos un candidato; `-c`
se puede repetir.

| Fuente | Ejemplo | Qué se toma |
|---|---|---|
| `file:` | `file:chat.txt` | Un archivo de texto UTF-8, un mensaje por línea. |
| `tgexport:` | `tgexport:result.json#Anna Petrova` | Una exportación JSON de un chat de Telegram Desktop; tras `#` el nombre del remitente, su `from_id` (`user111`) o un id numérico. |
| `tg:` | `tg:@friend` o `tg:@group#@person` | Mensajes mediante Telethon: un chat privado con un usuario, o los mensajes de una persona en un grupo. |
| `chat:` | `chat:777#Anna Petrova` | Una persona de un **chat cargado** (véase más abajo): antes de `#` el id o el título del chat, después el nombre del participante o su `from_id`. |

Solo se toman los mensajes de texto del remitente indicado: se omiten los mensajes reenviados y de
servicio y los archivos multimedia sin pie de foto. Los enlaces y las menciones se sustituyen por
etiquetas; los mensajes vacíos y los marcadores como `[Фото]` se descartan.

### Chats cargados

Para no tener que clasificar las exportaciones en carpetas a mano, carga la exportación de un chat
una vez y quedará en la lista. Después se puede borrar el `result.json` original: solo se
conservan los textos y las horas de los mensajes de los participantes.

- **En la ventana:** la pestaña «Чаты» (Chats) y después el botón para cargar una exportación de
  chat; en la comparación y en el perfil hay botones para elegir entre los chats cargados (se
  pueden marcar varios participantes de un chat a la vez).
- **En la línea de comandos:**

  ```
  chatstyle chats add result.json      cargar un chat (volver a cargarlo lo amplía sin duplicados)
  chatstyle chats list                 lista de chats
  chatstyle chats list Friends         participantes de un chat (nombre, identificador, número de mensajes)
  chatstyle chats remove Friends       quitar un chat de la lista
  chatstyle compare -u chat:Friends#Ann -c chat:Friends#Bob -c chat:Friends#Vera
  ```

Un chat se indica con el id de la exportación o con su título (si dos chats comparten título,
hace falta el id), un participante con su nombre o identificador (`user111`). Es el mismo análisis
que en `tgexport:`, pero el archivo se lee una sola vez. Los archivos de los chats están en el
directorio de datos (`chats/`) y están **cifrados** (AES-256-GCM): una clave aleatoria se guarda
en el almacén común de secretos (el mismo que contiene el inicio de sesión de Telegram:
contraseña maestra o DPAPI), así que hay que abrir el almacén antes de trabajar con chats. **Para
esto no hacen falta claves de API ni iniciar sesión en Telegram:** en la pestaña «Чаты» la propia
ventana ofrece configurar la protección (contraseña maestra, DPAPI o «solo mientras la ventana
esté abierta») o abrirla con la contraseña maestra; la CLI pregunta lo mismo. Un almacén
protegido con contraseña maestra se bloquea solo tras 15 minutos de inactividad en la pestaña
«Чаты». En el modo «solo mientras la ventana esté abierta» los chats viven solo en memoria y
desaparecen al cerrar la ventana. Los chats cargados por versiones anteriores (`*.json` sin
cifrar) se cifran al abrir el almacén por primera vez y las copias sin cifrar se sobrescriben. Un
archivo está ligado a su id: un archivo sustituido o modificado no se descifra.

### Telegram mediante Telethon

La red se usa **solo** aquí y solo cuando tú lo ordenas explícitamente.

1. Consigue un `api_id` y un `api_hash` en <https://my.telegram.org> (sección API development
   tools).
2. Inicia sesión una vez: el comando pregunta el método de protección (contraseña maestra o la
   cuenta de Windows), si hace falta las claves `api_id`/`api_hash` (también se pueden dar con las
   variables de entorno `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` o un archivo `.env`), después el
   teléfono, el código de Telegram y la contraseña 2FA si está activada:

   ```bash
   chatstyle login
   ```

3. Compara (si el almacén está protegido con contraseña maestra, el comando la pide sin eco):

   ```bash
   chatstyle compare -u tg:@stranger -c tg:@friend1 -c file:friend2.txt --limit 1000
   ```

**Desde la ventana.** El botón «Telegram» de la cabecera abre un asistente: el método de
protección del inicio de sesión, las claves (`api_id`, `api_hash`), el número de teléfono, el
código de Telegram y la contraseña 2FA si está activada. El código y las contraseñas no se
guardan nunca y los campos se vacían justo después de enviarlos. Tras iniciar sesión, las fuentes
ganan «Из Telegram» (un chat y, si hace falta, un remitente), y el límite de mensajes y «cargar de
nuevo» están en «Дополнительно». Iniciar sesión desde la ventana y `chatstyle login` usan el mismo
almacén cifrado. «Выйти из Telegram» borra la sesión del almacén y la cierra en el lado de
Telegram; «Удалить все данные Telegram» borra además el propio almacén. Los detalles de la
protección están en [Seguridad](#seguridad).

`--limit` (3000 por defecto) es el máximo de mensajes por autor; lo descargado se guarda en caché,
una ejecución repetida usa la caché y `--refresh` vuelve a descargar. Sin haber iniciado sesión,
`compare` con `tg:` pide ejecutar `chatstyle login`.

## Uso

```bash
chatstyle compare -u file:unknown.txt -c file:a.txt -c file:b.txt \
    --impostors outsider_texts/ --seed 1 --report report.html
chatstyle features file:chat.txt --top 10
chatstyle login
```

| Opción de `compare` | Significado |
|---|---|
| `-u, --unknown` | la fuente del autor desconocido |
| `-c, --candidate` | la fuente de un candidato (se puede repetir) |
| `--impostors DIR` | una carpeta con textos ajenos para General Impostors: **un archivo `.txt` por autor** (UTF-8, un mensaje por línea) |
| `--seed N` | la semilla de General Impostors (1 por defecto): la misma semilla da el mismo resultado |
| `--report FILE` | guardar un informe; el formato lo da la extensión, `.md` o `.html` |
| `--style-groups G` | grupos de rasgos de estilo para Burrows Delta: `all` (por defecto), `none` o una lista separada por comas de `punctuation`, `orthography`, `words`, `sentences`; no afecta a la puntuación final de General Impostors |
| `--morph` | añadir una columna «Части речи» (categorías gramaticales): similitud de n-gramas de categorías gramaticales (1-4); necesita el complemento opcional `pip install chatstyle[morph]` (pymorphy3), solo ruso, no afecta a la puntuación final |
| `--charlm` | añadir una columna «Языковая модель (бит/символ)» (modelo de lenguaje, bits por carácter): en cuántos bits por carácter el texto del autor desconocido lo predice mejor el modelo de caracteres de este candidato que el modelo de los demás candidatos (por encima de cero significa más cerca del candidato); necesita al menos dos candidatos no vacíos, no afecta a la puntuación final |
| `--wordgrams` | añadir una columna «Слова (косинус)» (palabras, coseno): similitud de n-gramas de palabras (1-4 palabras consecutivas, TF-IDF); las palabras que solo tiene un autor no se distinguen; no afecta a la puntuación final |
| `--emoji` | añadir una columna «Эмодзи (косинус)» (emoji, coseno): similitud de qué emoji usa el autor y en qué orden (1-4 seguidos; los emoji compuestos con tono de piel y uniones cuentan como uno); un autor sin ningún emoji no recibe puntuación; no afecta a la puntuación final |
| `--rhythm` | añadir una columna «Ритм (по времени)» (ritmo según el tiempo): similitud del ritmo de escritura (series de mensajes, pausas, hora del día, fines de semana); necesita fechas de los mensajes (fuentes `tgexport:` y `tg:`; `file:` no tiene fechas) y al menos 30 mensajes con fecha por autor; no afecta a la puntuación final |
| `--lexical` | añadir el vocabulario al conjunto de métodos (un modelo de lenguaje de caracteres normal y n-gramas de palabras en lugar del modelo de lenguaje sobre texto sin palabras raras): algo más preciso en los chats probados (98 % frente a 95 %) pero más sensible al tema; por defecto el orden se calcula solo con el estilo |
| `-n, --limit N`, `--refresh` | para `tg:`: el límite de mensajes y la actualización de la caché |

Cuando la salida se redirige (`chatstyle compare ... > result.txt`) el texto se escribe en UTF-8.

**Categorías gramaticales.** En `chatstyle.exe` y `chatstyle-gui.exe` vienen incluidas por defecto
(pymorphy3, unos +9 MB; una compilación sin ellas: `powershell -File packaging\build_exe.ps1
-NoMorph`). Al ejecutar desde el código fuente hace falta el complemento: `pip install
chatstyle[morph]`. El comando `chatstyle compare ... --morph` añade la columna «Части речи
(косинус)», mientras que `chatstyle features ... --morph` y la pestaña «Perfil de estilo» de la
ventana (la casilla «Учитывать части речи») muestran las proporciones de sustantivos, verbos,
partículas y palabras fuera del diccionario. Python solo etiqueta las palabras con códigos de una
letra de categoría gramatical (pymorphy3, en local, sin red), y el mismo núcleo cuenta las
frecuencias y los n-gramas sobre los códigos. El etiquetado sin contexto es ambiguo («мыла» ¿es
un sustantivo o un verbo?), y la jerga y los nombres no están en el diccionario, así que el rasgo
es ruidoso y no afecta a la puntuación final. En la ventana las casillas de categorías
gramaticales, modelo de lenguaje, n-gramas de palabras, emoji y ritmo están activadas desde el
principio (las categorías gramaticales si están en la compilación); en la línea de comandos estos
métodos se activan con `--morph`, `--charlm`, `--wordgrams`, `--emoji`, `--rhythm`.

**Modelo de lenguaje de caracteres.** Para cada candidato el núcleo entrena un modelo de
caracteres (un contexto de hasta tres caracteres, suavizado Witten-Bell, se conservan las
mayúsculas) y cuenta cuántos bits por carácter hacen falta para «codificar» el texto del autor
desconocido. Se resta la misma cifra del modelo de los demás candidatos: un valor positivo
significa que el texto está más cerca de este candidato. La cantidad de texto de entrenamiento se
iguala entre los candidatos (se toma como máximo lo que tiene el más corto), porque si no un
candidato largo ganaría solo por tamaño. Con un solo candidato no hay puntuación. El método se
activa con `--charlm` o la casilla de la ventana y todavía no afecta a la puntuación final: su
utilidad con datos reales no se ha medido.

**N-gramas de palabras.** La opción `--wordgrams` (y la casilla de la ventana) calcula la misma
similitud coseno, pero sobre secuencias de 1-4 palabras en lugar de caracteres: las expresiones
fijas («ну вообще», «в принципе») aportan más que las letras sueltas. Las palabras se pasan a
minúsculas; una palabra que falta al menos en dos autores de la comparación no puede confirmar
nada y se sustituye por una marca común de «palabra rara». Igual que con las categorías
gramaticales, Python solo sustituye palabras por símbolos y el mismo núcleo cuenta los n-gramas.
No afecta a la puntuación final; su utilidad con datos reales no se ha medido.

**Los emoji con más detalle.** El rasgo «proporción de emoji» del perfil solo dice si hay muchos o
pocos. La opción `--emoji` (y la casilla de la ventana) compara *cuáles exactamente* y en qué
orden: de los mensajes solo quedan los emoji (los compuestos cuentan enteros), a cada uno se le
asigna un símbolo y el mismo núcleo calcula el coseno sobre n-gramas de 1-4. Un autor sin emoji
no recibe puntuación. No afecta a la puntuación final.

**Ritmo de escritura en el tiempo.** Si la fuente sabe cuándo se escribieron los mensajes (una
exportación de Telegram Desktop y la carga `tg:`), el núcleo calcula ocho rasgos a partir de las
horas del autor: la proporción de pausas de hasta un minuto, la longitud de las series de
mensajes, la pausa típica (las pausas de más de seis horas, un descanso nocturno, no se cuentan),
las proporciones de mensajes por la noche, por la mañana, por la tarde y al anochecer, y la
proporción de fines de semana. La hora es la «de pared», como en el reloj del autor (la zona
horaria del ordenador), así que conviene comparar exportaciones de una persona y de su
interlocutor desde el mismo dispositivo. El perfil (`chatstyle features`, la pestaña «Perfil de
estilo») muestra el ritmo automáticamente cuando existe; en una comparación se activa con
`--rhythm`. Una serie son los mensajes del autor con pausas de hasta un minuto (los mensajes del
interlocutor no se ven en la fuente). Los archivos `file:` no tienen fechas, así que no tienen
ritmo. No afecta a la puntuación final; su utilidad con datos reales no se ha medido. La caché de
Telegram ahora guarda también la hora, así que una caché de una versión anterior no se lee y los
mensajes se vuelven a descargar.

**Hábitos, no errores.** Los rasgos de puntuación y ortografía miden los *hábitos estables* del
autor (con qué frecuencia alarga letras, pone una coma antes de una conjunción, escribe «щас» o
«тся»), no si algo está escrito «correctamente»: no se usa ningún diccionario ni corrector
gramatical, todo se calcula en local. Lo que importa para la comparación es que los hábitos de los
dos textos coincidan. La lista de grafías no estándar
(`python/chatstyle/resources/nonstandard_ru.txt`) se hizo a mano y no la han revisado hablantes
nativos. Los rasgos funcionan solo en Burrows Delta y en el perfil de estilo; la puntuación final
de General Impostors se sigue calculando con n-gramas de caracteres. Su utilidad con datos reales
no se ha medido: los datos sintéticos solo comprueban que el recuento es correcto (véase «Estado
y lagunas conocidas»).

### Cómo leer el resultado

| Columna | Significado |
|---|---|
| Сходство (similitud) | coseno de n-gramas TF-IDF, 0..1, más es más cerca |
| Delta | Burrows Delta, menos es más cerca; solo es comparable entre candidatos de una misma ejecución |
| Impostors (итог) | la **puntuación final**: la proporción de 100 iteraciones aleatorias en las que el texto del candidato está más cerca del desconocido que los textos de todos los ajenos. Un número 0..1, pero **no una probabilidad** |
| Смесь (conjunto de métodos) | el **orden de los candidatos**: la media de las puntuaciones z de tres señales entre candidatos del mismo tamaño: el «esqueleto» de palabras funcionales, Delta y un modelo de lenguaje de caracteres sobre texto sin palabras raras (con `--lexical`, en lugar de la última, un modelo de lenguaje normal y n-gramas de palabras); más es más cerca; el valor es relativo al conjunto de candidatos de esta ejecución. Con dos candidatos es la proporción de «votos» de los métodos: +1 todos a favor, -1 todos en contra |

Si hay al menos dos candidatos, las filas se ordenan por el conjunto de métodos de estilo; si no,
por Impostors (si está disponible para todos) y si no, por el coseno TF-IDF. Para que un candidato
grande no gane solo por el tamaño de su vocabulario, el conjunto de métodos se calcula con
candidatos del mismo tamaño: de cada uno se toman mensajes aleatorios hasta 2500 palabras (pero no
menos de las que tiene el candidato más corto). Las columnas «Сходство», «Delta» e «Impostors
(итог)» se siguen calculando sobre todo el texto. En la ventana la barra muestra la cercanía
*relativa* de los candidatos (un softmax del conjunto de métodos con temperatura 1,0, las
proporciones suman 1); no es la probabilidad de autoría. La línea «Лучший по методам» (mejor
según los métodos) muestra si los métodos coinciden. Cuando discrepan, eso es información en sí
misma: no elijas el método que más te guste.

Cuando los métodos no están disponibles (un guion):

- **Delta:** hacen falta al menos 6 fragmentos de 200 palabras para toda la comparación (unas 600
  palabras para dos autores).
- **General Impostors:** hacen falta al menos 3 autores ajenos (los demás candidatos más la
  carpeta de `--impostors`) y al menos 2 fragmentos de 200 palabras del autor desconocido y del
  candidato. En una ejecución «desconocido + 2 candidatos» hay un ajeno por candidato, así que sin
  `--impostors` no habrá puntuación final: es deliberado.

## Informe de ejemplo

[`docs/example_report.md`](docs/example_report.md) es un informe sobre datos **ficticios** (no una
conversación real). Para reproducirlo:

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

El informe (`.md` y un `.html` autónomo sin recursos externos) contiene: la tabla de candidatos,
una explicación de la puntuación final, los 20 n-gramas coincidentes principales (las letras
sueltas y el espacio se ocultan por poco informativos), las principales diferencias de estilo
según Delta con nombres legibles, los parámetros de la ejecución (semilla, número de ajenos), una
descripción del método y las limitaciones.

## Evaluación de la calidad

**Todavía no hay resultados.** Unas cifras honestas necesitan textos reales etiquetados de varios
autores, y el proyecto no tiene ese corpus. Cualquier número obtenido con datos inventados no
diría nada sobre la calidad en conversaciones reales, así que a propósito aquí no hay ninguno.

**Una comprobación con tus propios chats.** Si has cargado varios chats (la pestaña «Чаты» o
`chatstyle chats add`), puedes comprobar con ellos el orden de los candidatos sin ningún
etiquetado:

```bash
python -m experiments.chats_eval            # el conjunto de métodos de estilo (por defecto)
# lee el almacén cifrado (pide la contraseña maestra); --chats-dir CARPETA indica archivos de chat sin cifrar
python -m experiments.chats_eval --lexical  # el conjunto de métodos con vocabulario
```

El mismo identificador de participante en distintos chats cuenta como una persona; se construyen
dos tipos de tareas: «entre contextos» (una persona de un chat frente a los demás, cuyos textos se
toman de otros chats) y «por tiempo» (los últimos mensajes frente al resto). Solo se imprimen
números (la proporción de primeros puestos, MRR, la proporción al adivinar al azar), ni nombres ni
textos. Esto no sustituye una evaluación con un corpus etiquetado (véanse las salvedades en
«Estado y lagunas conocidas»), pero permite volver a comprobar cómo se comporta el algoritmo con
tus propios datos.

Las herramientas de evaluación están listas (`experiments/`) y probadas con datos sintéticos:

```bash
# conjunto de datos: una carpeta, un archivo .txt por autor, nombres anónimos, mensajes en orden
python -m experiments.evaluate DATASET --words 1000 --impostors 10 --jobs 4 --output results.json
python -m experiments.volume DATASET --slices 250 500 1000 2000 5000 --jobs 4   # calidad según el volumen, y un gráfico
python -m experiments.prepare_tgexport result.json DATASET --min-messages 300   # un conjunto de datos a partir de un chat de grupo
```

Para cada método se calcula el ROC AUC (con un intervalo de confianza, bootstrap sobre autores) y
la exactitud con un umbral elegido con datos distintos. Para depurar existe
`python -m experiments.make_synthetic CARPETA`; esos datos se marcan y los scripts advierten dos
veces de que los números no deben publicarse.

Los nuevos grupos de rasgos de estilo (puntuación, ortografía, palabras, frases) se pueden
comprobar de uno en uno: `python -m experiments.ablation DATASET` calcula el AUC de Burrows Delta
sin grupos, con cada grupo y con todos, y `python -m experiments.evaluate DATASET --style-groups
words,sentences` ejecuta la evaluación habitual con los grupos elegidos. Un conjunto de datos con
autores que tienen hábitos de escritura incorporados lo crea
`python -m experiments.make_synthetic CARPETA --habits`. Mientras no haya corpus, una ejecución así
solo demuestra que los grupos cambian realmente la puntuación, no que sean útiles con personas.

El umbral de la advertencia «menos de 1000 palabras» es provisional por ahora: se afinará con los
resultados de una evaluación con datos reales.

## Limitaciones

- **La estimación es probabilística.** Es una medida de la similitud de estilo, no una prueba. Una
  puntuación alta no significa el mismo autor y una baja no significa autores distintos.
- **La cantidad de texto importa mucho.** Con un volumen pequeño (menos de 1000 palabras en
  cualquiera de los lados) la puntuación puede ser aleatoria; con uno muy pequeño, Delta y General
  Impostors no están disponibles.
- **La puntuación final depende de los «ajenos».** Si hay pocos o se diferencian del entorno real
  de comunicación, la puntuación se distorsiona.
- **El estilo depende del contexto.** Una persona escribe de forma distinta en chats distintos, y
  personas distintas del mismo círculo, edad y tema escriben de forma parecida.
- **Idiomas.** Las letras y las mayúsculas se determinan con las tablas de Unicode 16 (latín con
  diacríticos, griego, armenio, georgiano, árabe, hebreo, escrituras índicas y otras), así que los
  métodos basados en caracteres (coseno, modelo de lenguaje, «esqueleto») funcionan con cualquier
  escritura; en chino y japonés (ideogramas y kana) cada signo cuenta como una palabra. **Pero la
  precisión solo se ha verificado en ruso.** Con datos sintéticos de nueve idiomas (inglés,
  francés, alemán, español, polaco, griego, árabe, chino, japonés) se distinguen autores con
  vocabularios distintos; es una comprobación de que funciona, no de precisión. Delta se apoya en
  listas rusas de palabras funcionales, muletillas y «grafías no estándar» y en rasgos como
  «тся/ться» y «ё/е», así que en otros idiomas solo quedan los rasgos independientes del idioma
  (puntuación, mayúsculas, longitudes); las categorías gramaticales (`--morph`) son solo para
  ruso. En otros idiomas conviene activar `--lexical`. Para tailandés, lao, jemer y birmano
  (escrituras sin espacios que no son ideogramas) una palabra sigue siendo una serie de letras. El
  paso a minúsculas sigue las reglas simples de Unicode: la İ turca y otros casos especiales
  parecidos no se modifican.
- **Distorsiones de los datos de origen:** las cuentas compartidas, los bots, las citas, los
  mensajes reenviados y el texto pegado afectan al resultado; los mensajes reenviados de Telegram
  no se cuentan, pero las citas dentro de mensajes normales permanecen.
- **La imitación deliberada del estilo ajeno y la paráfrasis del texto no se han evaluado**
  (previsto para una versión posterior).
- **Las marcas de tiempo** solo hacen falta para el ritmo (`--rhythm`): los archivos de texto no
  las tienen.
- Los archivos de texto se leen solo como UTF-8; un archivo en otra codificación se rechaza con un
  mensaje claro en lugar de leerse con distorsión.
- El método es cerrado: compara con los candidatos que tú indiques. El autor real puede no estar
  entre ellos.

## Ética y privacidad

- **Todo se calcula en local.** El único acceso a la red es Telegram (Telethon), y solo cuando se
  ordena explícitamente: `chatstyle login` y `compare`/`features` con una fuente `tg:`. No hay
  telemetría.
- **Qué archivos crea el programa.** En el directorio de datos (`%APPDATA%\chatstyle` en Windows,
  `~/.local/share/chatstyle` o `$XDG_DATA_HOME/chatstyle` en Linux; se puede cambiar con la
  variable `CHATSTYLE_HOME`):
  - `vault.json` es el almacén **cifrado**: las claves de la API de Telegram y la sesión (que
    equivale a tener acceso a tu cuenta), véase [Seguridad](#seguridad);
  - `cache/` es una caché de mensajes descargados de **personas reales** (sin cifrar);
  - `chats/` contiene los chats cargados (la pestaña «Чаты», `chatstyle chats add`): textos y
    horas de mensajes de **personas reales**, **cifrados** con la clave del almacén (`*.chat`);
  - `gui-settings.json` es el idioma y el tema de la ventana;
  - `.env` contiene las claves `api_id` y `api_hash`, solo si las has puesto ahí tú mismo.

  Para borrarlo todo, borra este directorio (y cierra la sesión en los ajustes de Telegram:
  «Dispositivos»).
- **Los informes contienen fragmentos de conversaciones** (n-gramas) y los nombres de las fuentes.
  No los publiques ni los compartas sin el consentimiento de los autores de los mensajes. Los
  nombres de archivo de la carpeta `--impostors` no llegan al informe.
- **Las conversaciones ajenas son datos personales.** Antes de analizar un chat, obtén el
  consentimiento de sus participantes y comprueba que lo permiten las leyes de tu país. El
  proyecto no da asesoramiento jurídico.
- **El repositorio no debe contener** `.env`, archivos `.session`, la caché ni ninguna conversación
  real; están excluidos en `.gitignore`. No los añadas a commits ni a ejemplos.
- **Para qué no está pensada la herramienta:** desanonimizar a personas contra su voluntad,
  vigilancia, presión y acoso, respaldar acusaciones sin otras pruebas, hacer pasar el resultado
  por prueba de autoría.

## Seguridad

**De qué protege.** De otros usuarios de este ordenador, del robo o la copia del disco y de la
carpeta de datos, de la sincronización en la nube, de la publicación accidental de archivos, de la
manipulación de la página de la ventana y de la interceptación del tráfico hacia Telegram. **De
qué no protege.** De un programa malicioso que se ejecute con tu cuenta, ni de un keylogger o una
grabación de pantalla: si existen, ningún programa puede guardar secretos. Frente a esa amenaza
elige el modo «solo mientras la ventana esté abierta» y activa la protección en dos pasos en
Telegram.

- **Tres formas de guardar el inicio de sesión** (`chatstyle login` o el asistente de la ventana):
  - *contraseña maestra* (recomendada): las claves y la sesión se cifran con AES-256-GCM, la clave
    se deriva de la contraseña con scrypt (64 MB, unos 0,3 s por intento), la contraseña no se
    guarda en ningún sitio, los intentos se ralentizan tras tres entradas erróneas; el almacén se
    bloquea solo tras 15 minutos de inactividad;
  - *cuenta de Windows* (DPAPI): no hace falta contraseña, pero cualquier programa que se ejecute
    con tu cuenta puede descifrar el inicio de sesión;
  - *solo mientras la ventana esté abierta*: no se escribe nada en el disco y, al cerrar la
    ventana, la sesión se cierra en el lado de Telegram.
- **No escribimos criptografía propia:** AES-GCM viene de la biblioteca `cryptography`, scrypt del
  `hashlib` estándar y DPAPI es una llamada al sistema de Windows. El archivo del almacén está
  autenticado: se detecta la corrupción o la manipulación de la cabecera. Una contraseña maestra
  olvidada no se puede recuperar: se inicia sesión de nuevo.
- **Los chats cargados se cifran** con el mismo almacén: la clave AES-256-GCM (256 bits, aleatoria)
  está en `vault.json`, no junto a los archivos; sin el almacén abierto no se pueden leer los
  chats. Al quitar un chat, el archivo se sobrescribe con ceros (en un SSD esto no garantiza el
  borrado físico). Si un programa malicioso se ejecuta con tu cuenta mientras el almacén está
  abierto, también obtendrá los chats, igual que obtendría la sesión de Telegram. El modo «solo
  mientras la ventana esté abierta» guarda los chats solo en memoria.
- **Permisos:** la carpeta de datos queda cerrada para todos salvo tu cuenta (en Windows con
  `icacls`, en Linux con permisos `0700`/`0600`).
- **La ventana:** la página se carga desde un archivo dentro del paquete, no desde un servidor
  local: el proceso no tiene puertos a la escucha (la autocomprobación lo verifica). Una política
  CSP prohíbe cualquier petición de red de la página, la navegación a otras direcciones se
  bloquea, no se usan el almacenamiento del navegador ni el autocompletado (modo privado de
  WebView2) y las herramientas de desarrollo están desactivadas. Los archivos se eligen solo en
  los cuadros de diálogo de la ventana, solo se abren los informes que ella misma creó y todo lo
  que llega de la página se comprueba en tipo y longitud.
- **La compilación:** las dependencias están fijadas por versión y hash
  (`packaging/requirements.lock`, instaladas con `pip install --require-hashes`), `pip-audit` no
  encontró vulnerabilidades conocidas en el momento de escribir esto y junto al exe se crea
  `dist/SHA256SUMS.txt`. **El exe no está firmado** (hace falta un certificado), así que
  SmartScreen puede avisar en el primer arranque.
- **Archivos sin cifrar de la versión anterior** (`telegram.session`, `telegram.account`): la
  ventana ofrece borrarlos cuando los encuentra, porque no están cifrados. La caché de mensajes de
  Telegram (`cache/`) tampoco está cifrada todavía.

## Cómo está organizado el proyecto

- **El núcleo (`core/`, C++17):** cálculos sobre el texto como una secuencia de puntos de código
  Unicode (UTF-8 a `std::u32string`), n-gramas, TF-IDF, coseno, Burrows Delta, General Impostors,
  explicaciones. El núcleo no sabe nada de archivos, Telegram ni informes. El enlace con Python es
  pybind11 (`chatstyle._core`).
- **Python (`python/chatstyle/`):** recolectores (txt, exportación de Telegram, Telethon),
  preprocesamiento, el pipeline, la CLI (typer, rich), informes. Python no calcula rasgos por sí
  mismo.
- **Otros:** `tests/` (pytest), `core/tests/` (Catch2), `experiments/` (evaluación de calidad, no
  forma parte del paquete), `packaging/` (PyInstaller), `docs/` (el informe de ejemplo),
  `.github/workflows/ci.yml`.

## Estado y lagunas conocidas

Esta sección es temporal y debe desaparecer antes de la v1.0. Una lista honesta de lo que **no
está verificado**:

- **CI** (GitHub Actions) está en verde en Windows (MSVC, Python 3.12) y Ubuntu (Python 3.11 y
  3.12): análisis de estilo del código, las pruebas de Python, las pruebas del núcleo y la
  compilación y ejecución de un wheel. En local el proyecto se comprobó además en Windows 10 con
  MinGW-w64 (Python 3.14). La ventana no está cubierta por CI en Linux (no hay pantalla y la
  prueba de la ventana se omite allí); la instalación en Linux (compilar el núcleo, ejecutar
  `chatstyle`) se comprobó además a mano en Kali Linux.
- **El recolector de Telegram solo se verificó con simulaciones**, sin una cuenta real.
- **Los archivos exe de Windows.** El flujo de trabajo de la versión compila `chatstyle.exe` y
  `chatstyle-gui.exe` con MSVC en un runner de GitHub y ejecuta allí pruebas rápidas
  (`--version`, `compare`, la autocomprobación de la ventana). Las compilaciones de la versión
  también se iniciaron a mano en la máquina Windows 10 del autor y funcionan. Una compilación
  local con MinGW-w64 pasó además `packaging/check_exe.py` (la versión y el icono en las
  propiedades del archivo, un `PATH` sin Python, la lectura de `.env` desde
  `%APPDATA%\chatstyle`, la salida en una consola real de 80 columnas de ancho, la pausa al
  arrancar con doble clic); en el runner ese script se ejecuta sin consola real, así que su
  resultado es solo informativo. **No verificado:** un Windows 10 limpio sin Python instalado en
  absoluto (sirve Windows Sandbox: copiar allí un único `chatstyle.exe` y ejecutar
  `chatstyle --version` y `compare`).
- **La evaluación con datos reales es un único entorno de conversación, y la elección del método
  se ajustó a él.** La comprobación se hizo con los chats de un usuario: dos grupos (202 y 16
  participantes) y chats privados. Tareas: una persona de un contexto (chat) frente a las demás
  personas cuyos textos se toman de otros chats (25 tareas), una división por tiempo dentro de un
  grupo (16) y un caso real de «cuenta gemela» (2); todos los candidatos tienen 2500 palabras, el
  texto desconocido tiene 600-1400 palabras y hay entre 10 y 36 candidatos. Primer puesto del
  autor verdadero: el conjunto completo con vocabulario (modelo de lenguaje, palabras,
  «esqueleto», Delta) 95 % (MRR 0,97), el conjunto de estilo (el predeterminado: «esqueleto»,
  Delta, modelo de lenguaje sin palabras raras) 91 % (MRR 0,93); en las tareas «entre contextos»
  eso es 92 % frente a 84 %: el conjunto de estilo paga unos puntos por la independencia del tema
  (en 129 ejecuciones «el autor verdadero y 3 rivales» el completo obtiene 98 %, el de estilo
  95 %); por separado el modelo de lenguaje 88 %, los n-gramas de palabras 88 %, Delta 72 %,
  «esqueleto» 72 %, Impostors con los demás candidatos como ajenos 58 %, el coseno TF-IDF 56 %. Si
  se mantiene el autor verdadero y 3 rivales al azar (129 ejecuciones, adivinar al azar es 25 %):
  el conjunto completo 98 %, Delta 88 %, coseno 84 %, Impostors 75 %. Los pesos ajustados del
  conjunto no fueron mejores que los iguales (una comprobación «dejar fuera a una persona», la
  diferencia dentro del ruido), y añadir un «fondo» de decenas de autores ajenos para las
  puntuaciones z no cambió nada, así que los pesos son iguales y no hay fondo.
  **Cómo tomarse esto:** es un solo entorno (chats en ruso de un mismo círculo, con muchas palabras
  y temas en común), las tareas dependen unas de otras y los cuatro métodos se eligieron entre
  unos diez con los mismos datos, así que las cifras son optimistas y pueden no trasladarse a otras
  personas, idiomas y volúmenes. El modelo de lenguaje y los n-gramas de palabras son sensibles al
  vocabulario y al tema (en parte compensado porque el texto desconocido y los candidatos se toman
  de chats distintos); el «esqueleto» y Delta dependen poco del tema.
  **Cuánto texto hace falta** (tareas «entre contextos» y reales, 27 tareas, ruido de unos ±7
  puntos). El texto del autor desconocido, primer puesto del conjunto de estilo / del conjunto con
  vocabulario: 300 palabras 67 % / 70 %, 600 70 % / 93 %, 1000 85 % / 96 %, 2000 81 % / 96 %, 4000
  89 % / 93 %. El conjunto de estilo apenas crece con más texto (con estos datos se queda en
  85-90 %), mientras que el vocabulario ya da más del 93 % con 600 palabras: si el autor
  desconocido tiene menos de 1000 palabras, usa `--lexical` (el propio programa lo recuerda con
  una pista en la tabla, los informes y la ventana). Volumen de los candidatos (igual para todos):
  2500 palabras cada uno 93 % / 98 %, 5000 86 % / 93 %, 10000 88 % / 95 %; cuanto peor se igualan
  los volúmenes, peor es el resultado, por eso el tope predeterminado es de 2500 palabras (pero no
  menos de las que tiene el más corto). Distintas muestras aleatorias de mensajes del mismo volumen
  dan una dispersión adicional de 2-3 puntos. Una primera comprobación con 5 candidatos favorecía
  la «Delta coseno»; con 36 candidatos no se confirmó: la conclusión de una muestra pequeña resultó
  errónea y ese método ya no está en el programa.

## Referencias

- Burrows J. *Delta: a Measure of Stylistic Difference and a Guide to Likely Authorship.*
  Literary and Linguistic Computing, 17(3), 2002.
- Koppel M., Winter Y. *Determining if two documents are written by the same author.*
  Journal of the Association for Information Science and Technology, 65(1), 2014.

## Licencia

MIT, véase [`LICENSE`](LICENSE).
