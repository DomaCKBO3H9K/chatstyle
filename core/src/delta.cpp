#include "chatstyle/delta.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace chatstyle {

namespace {

constexpr double kMinSigma = 1e-12;

bool is_word_feature(const std::u32string& key) {
    return key.compare(0, 3, U"fw:") == 0 || key.compare(0, 3, U"fl:") == 0;
}

// Признак, выбранный для Delta, и его разброс по кускам
struct SelectedFeature {
    std::u32string key;
    double sigma;
};

// Все фиксированные признаки плюс top_words самых частых слов (по среднему значению по
// кускам, при равенстве по ключу); признаки с нулевым разбросом исключаются
std::vector<SelectedFeature> select_features(const std::vector<SparseVector>& chunk_features,
                                             std::size_t top_words) {
    const auto chunks = static_cast<double>(chunk_features.size());
    std::vector<std::pair<std::u32string, double>> fixed;
    std::vector<std::pair<std::u32string, double>> words;
    for (const auto& entry : chunk_features.front()) {
        double sum = 0.0;
        for (const auto& chunk : chunk_features) {
            sum += chunk.at(entry.first);
        }
        const double mean = sum / chunks;
        if (is_word_feature(entry.first)) {
            if (mean > 0.0) {
                words.emplace_back(entry.first, mean);
            }
        } else {
            fixed.emplace_back(entry.first, mean);
        }
    }
    std::sort(words.begin(), words.end(), [](const auto& left, const auto& right) {
        return left.second != right.second ? left.second > right.second : left.first < right.first;
    });
    if (words.size() > top_words) {
        words.resize(top_words);
    }

    std::vector<SelectedFeature> selected;
    for (const auto* group : {&fixed, &words}) {
        for (const auto& [key, mean] : *group) {
            double squares = 0.0;
            for (const auto& chunk : chunk_features) {
                const double deviation = chunk.at(key) - mean;
                squares += deviation * deviation;
            }
            const double sigma = std::sqrt(squares / (chunks - 1.0));  // выборочное отклонение
            if (sigma > kMinSigma) {
                selected.push_back({key, sigma});
            }
        }
    }
    return selected;
}

}  // namespace

std::vector<std::vector<std::u32string>> split_into_chunks(
    const std::vector<std::u32string>& messages, std::size_t chunk_words,
    const std::vector<std::u32string>& ignored_tokens) {
    if (chunk_words == 0) {
        throw std::invalid_argument("chunk_words must be > 0");
    }
    std::vector<std::vector<std::u32string>> chunks;
    std::vector<std::u32string> current;
    std::size_t current_words = 0;
    for (const auto& message : messages) {
        current.push_back(message);
        current_words += word_count(message, ignored_tokens);
        if (current_words >= chunk_words) {
            chunks.push_back(std::move(current));
            current.clear();
            current_words = 0;
        }
    }
    if (!current.empty()) {
        if (chunks.empty() || current_words * 2 >= chunk_words) {
            chunks.push_back(std::move(current));
        } else {
            chunks.back().insert(chunks.back().end(), current.begin(), current.end());
        }
    }
    return chunks;
}

std::vector<DeltaResult> burrows_delta(const std::vector<std::u32string>& unknown,
                                       const std::vector<std::vector<std::u32string>>& candidates,
                                       const StyleLexicon& lexicon, const DeltaOptions& options) {
    if (options.chunk_words == 0) {
        throw std::invalid_argument("chunk_words must be > 0");
    }
    std::vector<DeltaResult> results(candidates.size());
    if (candidates.empty()) {
        return results;
    }

    // авторы: 0 — неизвестный, дальше кандидаты по порядку
    std::vector<const std::vector<std::u32string>*> authors = {&unknown};
    for (const auto& candidate : candidates) {
        authors.push_back(&candidate);
    }

    std::vector<SparseVector> chunk_features;
    for (const auto* author : authors) {
        for (const auto& chunk : split_into_chunks(*author, options.chunk_words,
                                                   lexicon.ignored_tokens)) {
            chunk_features.push_back(style_features(chunk, lexicon));
        }
    }
    if (unknown.empty() || chunk_features.size() < std::max<std::size_t>(options.min_chunks, 2)) {
        return results;
    }

    const auto selected = select_features(chunk_features, options.top_words);
    if (selected.empty()) {
        return results;
    }

    const SparseVector unknown_profile = style_features(unknown, lexicon);
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (candidates[i].empty()) {
            continue;
        }
        const SparseVector candidate_profile = style_features(candidates[i], lexicon);
        DeltaResult& result = results[i];
        double total = 0.0;
        for (const auto& feature : selected) {
            FeatureDifference difference;
            difference.feature = feature.key;
            difference.unknown_value = unknown_profile.at(feature.key);
            difference.candidate_value = candidate_profile.at(feature.key);
            difference.sigma = feature.sigma;
            difference.z_difference =
                (difference.unknown_value - difference.candidate_value) / feature.sigma;
            total += std::fabs(difference.z_difference);
            result.differences.push_back(std::move(difference));
        }
        std::sort(result.differences.begin(), result.differences.end(),
                  [](const FeatureDifference& left, const FeatureDifference& right) {
                      const double a = std::fabs(left.z_difference);
                      const double b = std::fabs(right.z_difference);
                      return a != b ? a > b : left.feature < right.feature;
                  });
        result.available = true;
        result.features_used = selected.size();
        result.delta = total / static_cast<double>(selected.size());
    }
    return results;
}

}  // namespace chatstyle
