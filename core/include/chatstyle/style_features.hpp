#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "chatstyle/ngrams.hpp"

namespace chatstyle {

// Словари, которые Python передаёт в ядро: ядро не читает файлы
struct StyleLexicon {
    std::vector<std::u32string> function_words;  // служебные слова, ключи "fw:<слово>"
    std::vector<std::u32string> filler_words;    // слова-паразиты, ключи "fl:<слово>"
    std::vector<std::u32string> ignored_tokens;  // служебные метки предобработки ("<URL>")
};

// Стилевые признаки автора (кроме n-грамм). Набор ключей всегда полный: нулевые значения
// записываются тоже, чтобы у разных авторов признаковое пространство совпадало.
// Сообщения нужны в исходном регистре. Для пустого входа все значения 0.0.
//   fw:<слово>, fl:<слово>  частота слова среди всех слов
//   p:paren1/paren2/paren3+  серии ")" длиной 1, 2, 3 и более, на сообщение
//   p:ellipsis               серии из 3 и более точек или символ "…", на сообщение
//   p:excl1/excl2+, p:quest1/quest2+  серии "!" и "?", на сообщение
//   p:end_dot                доля сообщений, оканчивающихся одной точкой
//   f:capital_start          доля сообщений с заглавной первой буквой
//   f:yo_ratio               ё / (ё + е)
//   f:latin_share            доля латинских букв среди всех букв
//   f:emoji                  эмодзи на сообщение
//   r:avg_chars, r:avg_words средняя длина сообщения в символах и в словах
SparseVector style_features(const std::vector<std::u32string>& messages,
                            const StyleLexicon& lexicon);

// Число слов в сообщении: служебные метки не считаются, слова определяются как в style_features
std::size_t word_count(const std::u32string& message,
                       const std::vector<std::u32string>& ignored_tokens);

}  // namespace chatstyle
