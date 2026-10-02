#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace chatstyle {

struct CharLmOptions {
    std::size_t order = 4;  // длина контекста+1
    bool balance = true;    // выровнять объём обучения у кандидатов
};

struct CharLmResult {
    bool available = false;
    double bits_candidate = 0.0;  // кросс-энтропия текста неизвестного автора под моделью кандидата, бит на символ
    double bits_rest = 0.0;       // кросс-энтропия текста неизвестного автора под моделью остальных кандидатов, бит на символ
    double llr = 0.0;             // bits_rest - bits_candidate (больше нуля: ближе к этому кандидату)
    std::size_t chars_scored = 0;
};

// charlm_compare: сравнение неизвестного автора с каждым кандидатом по символьным n-граммным моделям.
// order == 0: std::invalid_argument
std::vector<CharLmResult> charlm_compare(const std::vector<std::u32string>& unknown,
                                         const std::vector<std::vector<std::u32string>>& candidates,
                                         const CharLmOptions& options);

}  // namespace chatstyle
