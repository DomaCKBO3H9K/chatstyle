#pragma once

#include <string>
#include <vector>

namespace chatstyle {
    // Сходство неизвестного автора с каждым кандидатом; результат в порядке кандидатов
    std::vector<double> compare_to_unknown(const std::vector<std::string>& unknown, const std::vector<std::vector<std::string>>& candidates);
}
