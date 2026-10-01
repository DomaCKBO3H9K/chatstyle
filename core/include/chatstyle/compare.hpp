#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace chatstyle {

// Общий n-граммный признак, объясняющий сходство неизвестного автора и кандидата
struct SharedFeature {
    std::u32string feature;   // читаемый вид: пробел «␣», начало «^», конец «$»
    double contribution;      // вклад в косинус; сумма вкладов по всем общим признакам = сходство
    double unknown_count;     // сколько раз n-грамма встречается у неизвестного автора
    double candidate_count;   // и у кандидата
};

struct CandidateReport {
    double similarity;
    std::vector<SharedFeature> top_features;  // по убыванию вклада
};

// Сходство неизвестного автора с каждым кандидатом; результат в порядке кандидатов
std::vector<double> compare_to_unknown(const std::vector<std::string>& unknown,
                                       const std::vector<std::vector<std::string>>& candidates);

// То же сходство плюс top_k признаков с наибольшим вкладом для каждого кандидата
std::vector<CandidateReport> compare_with_explanations(
    const std::vector<std::string>& unknown,
    const std::vector<std::vector<std::string>>& candidates, std::size_t top_k);

}  // namespace chatstyle
