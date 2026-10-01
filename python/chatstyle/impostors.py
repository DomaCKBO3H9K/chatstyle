"""General Impostors: тонкая обёртка над ядром."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from chatstyle import _core
from chatstyle.preprocess import MENTION_TOKEN, URL_TOKEN

DEFAULT_SEED = 1
DEFAULT_ITERATIONS = 100
DEFAULT_FEATURE_FRACTION = 0.5
DEFAULT_MAX_IMPOSTORS = 25
DEFAULT_MIN_IMPOSTORS = 3
DEFAULT_MIN_CHUNKS = 2
DEFAULT_CHUNK_WORDS = 200


@dataclass(frozen=True)
class ImpostorsScore:
    """Оценка General Impostors одного кандидата.

    score — доля итераций, в которых кандидат оказался ближе к неизвестному тексту, чем все
    посторонние (0..1). Это не вероятность авторства. Если available == False, данных
    недостаточно (мало посторонних или мало текста) и score не имеет смысла.
    """

    available: bool
    score: float
    impostors: int  # сколько посторонних авторов было у этого кандидата
    iterations: int


def general_impostors(
    unknown: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
    impostors: Mapping[str, Sequence[str]] | None = None,
    *,
    seed: int = DEFAULT_SEED,
    iterations: int = DEFAULT_ITERATIONS,
    feature_fraction: float = DEFAULT_FEATURE_FRACTION,
    max_impostors: int = DEFAULT_MAX_IMPOSTORS,
    min_impostors: int = DEFAULT_MIN_IMPOSTORS,
    min_chunks: int = DEFAULT_MIN_CHUNKS,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
) -> dict[str, ImpostorsScore]:
    """Оценка General Impostors каждого кандидата по предобработанным сообщениям.

    Посторонние кандидата: остальные кандидаты и все авторы из impostors (имена нужны
    только вам: ядру важен список текстов). Результат полностью определяется входом и seed.
    """
    raw = _core.general_impostors(
        list(unknown),
        {name: list(texts) for name, texts in candidates.items()},
        [list(texts) for texts in (impostors or {}).values()],
        [URL_TOKEN, MENTION_TOKEN],
        iterations,
        feature_fraction,
        max_impostors,
        min_impostors,
        min_chunks,
        chunk_words,
        seed,
    )
    return {name: ImpostorsScore(**report) for name, report in raw.items()}
