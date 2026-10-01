"""Синтетический датасет для отладки скриптов оценки: ВЫМЫШЛЕННЫЕ авторы, не реальные люди.

    python -m experiments.make_synthetic DIR --authors 12 --messages 1500 --seed 1 --blend 0.6

В папке появятся a001.txt, a002.txt, ... и файл-метка SYNTHETIC. Метку читает evaluate.py и
предупреждает, что числа с такого датасета нельзя публиковать как результат: у каждого автора
свои привычки (веса служебных слов и слов-паразитов, знаки в конце, заглавные), но это не
живая речь и не показатель качества на настоящих перепис­ках.
"""

import argparse
import random
from collections.abc import Sequence
from pathlib import Path

from chatstyle.lexicon import filler_words, function_words

from experiments.trials import SYNTHETIC_MARKER

_SYLLABLES = ["ка", "ро", "ли", "ма", "но", "се", "ту", "ви", "до", "пе", "ша", "ре", "ни", "бо"]
_CONTENT_POOL_SIZE = 400


def _content_pool(rng: random.Random) -> list[str]:
    return [
        "".join(rng.choice(_SYLLABLES) for _ in range(rng.randint(2, 3)))
        for _ in range(_CONTENT_POOL_SIZE)
    ]


def _skewed_weights(rng: random.Random, size: int) -> list[float]:
    return [rng.random() ** 3 + 0.02 for _ in range(size)]


def _ending(rng: random.Random, habits: dict[str, float]) -> str:
    roll = rng.random()
    for kind, text in (("paren", ")"), ("ellipsis", "..."), ("excl", "!"), ("dot", ".")):
        roll -= habits[kind]
        if roll < 0:
            if kind == "paren":
                return text * rng.choice([1, 1, 2, 3])
            return text
    return ""


class _Traits:
    """Привычки автора: веса слов, доли знаков и длина сообщения."""

    def __init__(self, rng: random.Random, vocabulary_size: int, content_size: int) -> None:
        self.vocabulary_weights = _skewed_weights(rng, vocabulary_size)
        self.content_weights = _skewed_weights(rng, content_size)
        self.content_share = rng.uniform(0.15, 0.4)
        self.habits = {
            "paren": rng.choice([0.0, 0.1, 0.3, 0.5]),
            "ellipsis": rng.choice([0.0, 0.05, 0.15]),
            "excl": rng.choice([0.0, 0.05, 0.15]),
            "dot": rng.choice([0.0, 0.2, 0.6]),
        }
        self.capital_share = rng.choice([0.0, 0.1, 0.5, 0.9])
        self.mean_length = float(rng.randint(5, 11))

    def blended(self, common: "_Traits", blend: float) -> "_Traits":
        """Привычки, смешанные с общими: blend=0 — как есть, blend=1 — все авторы одинаковы."""

        def mix(own: float, shared: float) -> float:
            return (1 - blend) * own + blend * shared

        result = object.__new__(_Traits)
        result.vocabulary_weights = [
            mix(own, shared)
            for own, shared in zip(self.vocabulary_weights, common.vocabulary_weights, strict=True)
        ]
        result.content_weights = [
            mix(own, shared)
            for own, shared in zip(self.content_weights, common.content_weights, strict=True)
        ]
        result.content_share = mix(self.content_share, common.content_share)
        result.habits = {k: mix(v, common.habits[k]) for k, v in self.habits.items()}
        result.capital_share = mix(self.capital_share, common.capital_share)
        result.mean_length = mix(self.mean_length, common.mean_length)
        return result


def make_author(
    seed: int,
    messages: int,
    content_pool: Sequence[str],
    common: _Traits | None = None,
    blend: float = 0.0,
) -> list[str]:
    """Сообщения одного вымышленного автора со своими привычками (смешанными с общими)."""
    rng = random.Random(seed)
    vocabulary = function_words() + filler_words()
    traits = _Traits(rng, len(vocabulary), len(content_pool))
    if common is not None and blend > 0:
        traits = traits.blended(common, blend)

    lines = []
    for _ in range(messages):
        words = []
        for _ in range(max(1, round(traits.mean_length) + rng.randint(-3, 3))):
            if rng.random() < traits.content_share:
                words.append(rng.choices(content_pool, traits.content_weights)[0])
            else:
                words.append(rng.choices(vocabulary, traits.vocabulary_weights)[0])
        if rng.random() < traits.capital_share:
            words[0] = words[0].capitalize()
        lines.append(" ".join(words) + _ending(rng, traits.habits))
    return lines


def make_dataset(
    directory: Path,
    authors: int = 12,
    messages: int = 1500,
    seed: int = 1,
    blend: float = 0.6,
) -> None:
    """Создать папку датасета (формат evaluate.py) с вымышленными авторами.

    blend от 0 до 1: чем больше, тем ближе привычки авторов к общим и тем труднее их различить.
    """
    directory.mkdir(parents=True, exist_ok=True)
    content_pool = _content_pool(random.Random(seed))
    vocabulary_size = len(function_words()) + len(filler_words())
    common = _Traits(random.Random(seed * 7919 + 1), vocabulary_size, len(content_pool))
    for index in range(authors):
        lines = make_author(seed * 1000 + index, messages, content_pool, common, blend)
        (directory / f"a{index + 1:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    (directory / SYNTHETIC_MARKER).write_text(
        "Синтетический датасет (make_synthetic.py): числа с него нельзя публиковать.\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Создать синтетический датасет для отладки.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--authors", type=int, default=12)
    parser.add_argument("--messages", type=int, default=1500, help="сообщений на автора")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--blend", type=float, default=0.6, help="0..1: чем больше, тем труднее различить авторов"
    )
    args = parser.parse_args(argv)
    if not 0.0 <= args.blend <= 1.0:
        parser.error("--blend должен быть от 0 до 1")
    make_dataset(args.directory, args.authors, args.messages, args.seed, args.blend)
    print(f"Создано авторов: {args.authors} в {args.directory} (метка {SYNTHETIC_MARKER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
