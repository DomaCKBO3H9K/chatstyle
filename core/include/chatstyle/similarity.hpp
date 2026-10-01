#pragma once

#include <vector>

#include "chatstyle/ngrams.hpp"

namespace chatstyle {
    // Вычисляет TF-IDF для каждого вектора счётчиков (документа)
    std::vector<SparseVector> tfidf(const std::vector<SparseVector>& counts);
    // Вычисляет косинусное сходство между двумя векторами
    double cosine(const SparseVector& a, const SparseVector& b);
}
