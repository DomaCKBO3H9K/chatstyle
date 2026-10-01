#include "chatstyle/similarity.hpp"

#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <utility>

namespace chatstyle {

std::vector<SparseVector> tfidf(const std::vector<SparseVector>& counts) {
    std::vector<SparseVector> result;
    const std::size_t N = counts.size();
    if (N == 0) {
        return result;
    }

    result.resize(N);

    // Вычисляем df для каждого ключа: в скольких документах ключ встречается
    std::unordered_map<std::u32string, std::size_t> df;
    for (const auto& doc : counts) {
        for (const auto& [key, count] : doc) {
            if (count > 0) {
                df[key]++;
            }
        }
    }

    // Для каждого документа вычисляем TF-IDF
    for (std::size_t i = 0; i < N; ++i) {
        for (const auto& [key, count] : counts[i]) {
            if (count <= 0) {
                continue;
            }
            const std::size_t document_frequency = df[key];
            const double inverse_document_frequency = std::log((1.0 + N) / (1.0 + document_frequency)) + 1.0;
            const double term_frequency = 1.0 + std::log(count);
            result[i][key] = term_frequency * inverse_document_frequency;
        }
    }

    return result;
}

double cosine(const SparseVector& a, const SparseVector& b) {
    if (a.empty() || b.empty()) {
        return 0.0;
    }

    // Скалярное произведение: проходим по меньшему вектору
    const SparseVector* smaller = &a;
    const SparseVector* larger = &b;
    if (a.size() > b.size()) {
        std::swap(smaller, larger);
    }

    double dot = 0.0;
    for (const auto& [key, value] : *smaller) {
        auto it = larger->find(key);
        if (it != larger->end()) {
            dot += value * it->second;
        }
    }

    // Нормы векторов
    double norm_a = 0.0;
    for (const auto& [_, value] : a) {
        norm_a += value * value;
    }
    norm_a = std::sqrt(norm_a);

    double norm_b = 0.0;
    for (const auto& [_, value] : b) {
        norm_b += value * value;
    }
    norm_b = std::sqrt(norm_b);

    if (norm_a == 0.0 || norm_b == 0.0) {
        return 0.0;
    }

    double similarity = dot / (norm_a * norm_b);
    if (similarity > 1.0) {
        return 1.0;
    }
    if (similarity < 0.0) {
        return 0.0;
    }
    return similarity;
}

std::vector<FeatureContribution> top_contributions(const SparseVector& a, const SparseVector& b, std::size_t k) {
    std::vector<FeatureContribution> result;
    if (k == 0 || a.empty() || b.empty()) {
        return result;
    }

    double norm_a = 0.0;
    for (const auto& [_, value] : a) {
        norm_a += value * value;
    }
    double norm_b = 0.0;
    for (const auto& [_, value] : b) {
        norm_b += value * value;
    }
    const double scale = std::sqrt(norm_a) * std::sqrt(norm_b);
    if (scale == 0.0) {
        return result;
    }

    for (const auto& [key, value] : a) {
        const auto found = b.find(key);
        if (found != b.end()) {
            result.push_back({key, value * found->second / scale});
        }
    }

    const auto better = [](const FeatureContribution& left, const FeatureContribution& right) {
        if (left.contribution != right.contribution) {
            return left.contribution > right.contribution;
        }
        return left.feature < right.feature;
    };
    const std::size_t count = std::min(k, result.size());
    std::partial_sort(result.begin(), result.begin() + static_cast<std::ptrdiff_t>(count), result.end(), better);
    result.resize(count);
    return result;
}

}
