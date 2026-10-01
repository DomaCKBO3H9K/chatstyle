#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "chatstyle/style_features.hpp"

namespace chatstyle {

struct DeltaOptions {
    std::size_t chunk_words = 200;  // кусок текста закрывается, когда набралось столько слов
    std::size_t min_chunks = 6;     // меньше кусков во всём сравнении: Delta недоступна
    std::size_t top_words = 100;    // сколько самых частых слов словарей берётся в признаки
};

// Различие одного признака между неизвестным автором и кандидатом
struct FeatureDifference {
    std::u32string feature;
    double unknown_value;
    double candidate_value;
    double sigma;         // разброс признака по кускам текста всех авторов сравнения
    double z_difference;  // (неизвестный - кандидат) / sigma
};

struct DeltaResult {
    bool available = false;  // false: мало текста для оценки разброса, delta не имеет смысла
    double delta = 0.0;      // среднее |z_difference| по признакам; меньше значит ближе
    std::size_t features_used = 0;
    std::vector<FeatureDifference> differences;  // по убыванию |z_difference|, при равенстве по ключу
};

// Режет сообщения по порядку на куски по chunk_words слов (сообщение не режется).
// Остаток короче половины куска приклеивается к последнему куску; единственный остаток
// остаётся отдельным куском. chunk_words == 0 — std::invalid_argument
std::vector<std::vector<std::u32string>> split_into_chunks(
    const std::vector<std::u32string>& messages, std::size_t chunk_words,
    const std::vector<std::u32string>& ignored_tokens);

// Burrows Delta неизвестного автора с каждым кандидатом, в порядке кандидатов.
// Разброс признаков (sigma) оценивается по кускам текста всех авторов сравнения, поэтому
// метод работает и для двух-трёх авторов. Признаки: все фиксированные стилевые признаки и
// top_words самых частых слов словарей; признаки с нулевым разбросом исключаются.
// Сообщения нужны в исходном регистре.
std::vector<DeltaResult> burrows_delta(const std::vector<std::u32string>& unknown,
                                       const std::vector<std::vector<std::u32string>>& candidates,
                                       const StyleLexicon& lexicon, const DeltaOptions& options);

}  // namespace chatstyle
