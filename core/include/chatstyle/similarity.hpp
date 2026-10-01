#pragma once

#include <vector>

#include "chatstyle/ngrams.hpp"

namespace chatstyle {
    // Вычисляет TF-IDF для каждого вектора счётчиков (документа)
    std::vector<SparseVector> tfidf(const std::vector<SparseVector>& counts);
    // Вычисляет косинусное сходство между двумя векторами
    double cosine(const SparseVector& a, const SparseVector& b);

    // Вклад одного общего признака в косинус: w_a * w_b / (|a| * |b|)
    struct FeatureContribution {
        std::u32string feature;
        double contribution;
    };
    // k общих признаков с наибольшим вкладом по убыванию; при равенстве порядок по ключу.
    // Сумма вкладов по всем общим признакам равна cosine(a, b)
    std::vector<FeatureContribution> top_contributions(const SparseVector& a, const SparseVector& b, std::size_t k);
}
