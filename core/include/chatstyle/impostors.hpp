#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace chatstyle {

struct ImpostorsOptions {
    std::size_t iterations = 100;
    double feature_fraction = 0.5;      // доля символьных n-грамм, учитываемых в итерации, (0, 1]
    std::size_t max_impostors = 25;     // сколько посторонних авторов берётся в итерацию
    std::size_t min_impostors = 3;      // меньше посторонних: оценка недоступна
    std::size_t min_chunks = 2;         // меньше кусков у неизвестного или кандидата: недоступна
    std::size_t chunk_words = 200;      // размер куска текста в словах
    unsigned seed = 1;                  // seed std::mt19937; задаётся снаружи
};

struct ImpostorsResult {
    bool available = false;      // false: данных недостаточно, score не имеет смысла
    double score = 0.0;          // доля итераций, где кандидат ближе неизвестного, чем все посторонние
    std::size_t impostors = 0;   // сколько посторонних авторов было у кандидата
    std::size_t iterations = 0;
};

// General Impostors (Koppel, Winter). Для каждого кандидата в каждой итерации выбирается
// случайное подмножество признаков (символьные n-граммы 1-4, TF-IDF по кускам всех авторов),
// случайный кусок неизвестного, случайный кусок кандидата и по случайному куску у посторонних;
// победа, если кусок кандидата строго ближе (косинус) куска неизвестного, чем куски всех
// посторонних. Куски одного размера, поэтому длина текстов сравнению не мешает.
// Посторонние кандидата: остальные кандидаты и extra_impostors. Результат в порядке кандидатов.
// Результат полностью определяется входом и options.seed (на любой платформе).
// Некорректные параметры — std::invalid_argument.
std::vector<ImpostorsResult> general_impostors(
    const std::vector<std::u32string>& unknown,
    const std::vector<std::vector<std::u32string>>& candidates,
    const std::vector<std::vector<std::u32string>>& extra_impostors,
    const std::vector<std::u32string>& ignored_tokens, const ImpostorsOptions& options);

}  // namespace chatstyle
