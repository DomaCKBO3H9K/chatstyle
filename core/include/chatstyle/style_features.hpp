#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "chatstyle/ngrams.hpp"

namespace chatstyle {

// Группы дополнительных признаков (битовая маска StyleLexicon::groups). Базовые признаки
// (p:paren*, p:ellipsis, f:*, r:*, fw:, fl:) считаются всегда.
constexpr unsigned kGroupPunctuation = 1;  // привычки пунктуации
constexpr unsigned kGroupOrthography = 2;  // регистр и орфографические привычки
constexpr unsigned kGroupWords = 4;        // словарное богатство
constexpr unsigned kGroupSentences = 8;    // длина и число предложений
constexpr unsigned kGroupAll = 15;

// Словари, которые Python передаёт в ядро: ядро не читает файлы
struct StyleLexicon {
    std::vector<std::u32string> function_words;  // служебные слова, ключи "fw:<слово>"
    std::vector<std::u32string> filler_words;    // слова-паразиты, ключи "fl:<слово>"
    std::vector<std::u32string> ignored_tokens;  // служебные метки предобработки ("<URL>")
    std::vector<std::u32string> nonstandard_words;  // нестандартные написания, ключи "ms:<слово>"
    std::vector<std::u32string> conjunctions;       // союзы для p:comma_before_conj
    unsigned groups = kGroupAll;                    // какие дополнительные группы считать
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
// Дополнительные группы (по маске groups; в выключенной группе ключей нет):
//   пунктуация: p:comma_per_word запятых на слово; p:comma_before_conj доля союзов из словаря
//     (не в начале сообщения и предложения) с запятой перед ними; p:no_space_after_comma доля
//     запятых без пробела после (перед буквой); p:space_before_punct доля знаков «, . ! ?» с
//     пробелом перед ними; p:dash тире на сообщение (« - », «–», «—»); p:guillemets доля «ёлочек»
//     среди всех кавычек; p:end_none доля сообщений, оканчивающихся буквой или цифрой
//   орфография: f:caps_words слов ЦЕЛИКОМ заглавными (2+ букв) на сообщение; f:capital_after_dot
//     доля заглавных букв после «. ! ?» внутри сообщения; o:repeat_letters растяжений (3+ одинаковые
//     буквы подряд) на сообщение; o:tsya_share «тся» / («тся» + «ться»); o:mixed_script доля слов
//     со смешением кириллицы и латиницы; o:double_space двойных пробелов на сообщение;
//     o:nonstandard доля слов из словаря нестандартных написаний; ms:<слово> частота такого слова
//   слова: w:mattr разнообразие слов в скользящем окне из 50 слов (не зависит от длины текста);
//     w:avg_word_len средняя длина слова в буквах; w:long_words, w:short_words доли слов длиной
//     9 и более и 2 и менее букв
//   предложения (граница: «. ! ? … » или перевод строки): s:avg_sentence_words средняя длина в
//     словах; s:per_message предложений на сообщение; s:short_share, s:long_share доли предложений
//     из 3 слов и менее и из 15 и более; s:multi_share доля сообщений из двух и более предложений
SparseVector style_features(const std::vector<std::u32string>& messages,
                            const StyleLexicon& lexicon);

// Число слов в сообщении: служебные метки не считаются, слова определяются как в style_features
std::size_t word_count(const std::u32string& message,
                       const std::vector<std::u32string>& ignored_tokens);

}  // namespace chatstyle
