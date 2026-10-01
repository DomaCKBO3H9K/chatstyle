#include "chatstyle/impostors.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <random>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include "chatstyle/delta.hpp"
#include "chatstyle/ngrams.hpp"
#include "chatstyle/similarity.hpp"
#include "chatstyle/text.hpp"

namespace chatstyle {

namespace {

constexpr std::size_t kNgramMin = 1;
constexpr std::size_t kNgramMax = 4;

using IndexedVector = std::vector<std::pair<std::uint32_t, double>>;  // отсортирован по индексу

struct Corpus {
    std::vector<IndexedVector> chunks;                // куски всех авторов
    std::vector<std::vector<std::size_t>> authors;    // автор -> индексы его кусков
    std::size_t feature_count = 0;
};

void validate(const ImpostorsOptions& options) {
    if (options.iterations == 0 || options.chunk_words == 0 || options.max_impostors == 0 ||
        options.min_impostors == 0 || options.min_chunks == 0) {
        throw std::invalid_argument("iterations, chunk_words, max_impostors, min_impostors and "
                                    "min_chunks must be > 0");
    }
    if (!(options.feature_fraction > 0.0 && options.feature_fraction <= 1.0)) {
        throw std::invalid_argument("feature_fraction must be in (0, 1]");
    }
}

// Куски всех авторов в виде TF-IDF векторов (документ = кусок). Индексы признаков идут в
// порядке сортировки ключей, а не обхода unordered_map, чтобы маски не зависели от платформы
Corpus build_corpus(const std::vector<const std::vector<std::u32string>*>& authors,
                    const std::vector<std::u32string>& ignored_tokens, std::size_t chunk_words) {
    Corpus corpus;
    std::vector<SparseVector> counts;
    for (const auto* author : authors) {
        std::vector<std::size_t> indexes;
        for (const auto& chunk : split_into_chunks(*author, chunk_words, ignored_tokens)) {
            std::vector<std::u32string> lowered;
            lowered.reserve(chunk.size());
            for (const auto& message : chunk) {
                lowered.push_back(to_lower(message));
            }
            indexes.push_back(counts.size());
            counts.push_back(count_char_ngrams(lowered, kNgramMin, kNgramMax));
        }
        corpus.authors.push_back(std::move(indexes));
    }

    const std::vector<SparseVector> weighted = tfidf(counts);
    counts.clear();

    std::unordered_set<std::u32string> unique_keys;
    for (const auto& vector : weighted) {
        for (const auto& entry : vector) {
            unique_keys.insert(entry.first);
        }
    }
    std::vector<std::u32string> keys(unique_keys.begin(), unique_keys.end());
    std::sort(keys.begin(), keys.end());
    std::unordered_map<std::u32string, std::uint32_t> index_of;
    index_of.reserve(keys.size());
    for (std::size_t i = 0; i < keys.size(); ++i) {
        index_of.emplace(keys[i], static_cast<std::uint32_t>(i));
    }
    corpus.feature_count = keys.size();

    corpus.chunks.reserve(weighted.size());
    for (const auto& vector : weighted) {
        IndexedVector indexed;
        indexed.reserve(vector.size());
        for (const auto& entry : vector) {
            indexed.emplace_back(index_of.at(entry.first), entry.second);
        }
        std::sort(indexed.begin(), indexed.end());
        corpus.chunks.push_back(std::move(indexed));
    }
    return corpus;
}

double masked_norm(const IndexedVector& vector, const std::vector<char>& mask) {
    double sum = 0.0;
    for (const auto& [index, weight] : vector) {
        if (mask[index]) {
            sum += weight * weight;
        }
    }
    return std::sqrt(sum);
}

double masked_dot(const IndexedVector& a, const IndexedVector& b, const std::vector<char>& mask) {
    double sum = 0.0;
    std::size_t i = 0;
    std::size_t j = 0;
    while (i < a.size() && j < b.size()) {
        if (a[i].first < b[j].first) {
            ++i;
        } else if (a[i].first > b[j].first) {
            ++j;
        } else {
            if (mask[a[i].first]) {
                sum += a[i].second * b[j].second;
            }
            ++i;
            ++j;
        }
    }
    return sum;
}

// Косинус только по признакам из маски; norm_a передаётся готовой, она общая для итерации
double masked_cosine(const IndexedVector& a, double norm_a, const IndexedVector& b,
                     const std::vector<char>& mask) {
    const double norm_b = masked_norm(b, mask);
    if (norm_a == 0.0 || norm_b == 0.0) {
        return 0.0;
    }
    return masked_dot(a, b, mask) / (norm_a * norm_b);
}

}  // namespace

std::vector<ImpostorsResult> general_impostors(
    const std::vector<std::u32string>& unknown,
    const std::vector<std::vector<std::u32string>>& candidates,
    const std::vector<std::vector<std::u32string>>& extra_impostors,
    const std::vector<std::u32string>& ignored_tokens, const ImpostorsOptions& options) {
    validate(options);
    std::vector<ImpostorsResult> results(candidates.size());
    if (candidates.empty()) {
        return results;
    }

    // авторы: 0 — неизвестный, 1..C — кандидаты, дальше посторонние из extra_impostors
    std::vector<const std::vector<std::u32string>*> authors = {&unknown};
    for (const auto& candidate : candidates) {
        authors.push_back(&candidate);
    }
    for (const auto& impostor : extra_impostors) {
        authors.push_back(&impostor);
    }
    const Corpus corpus = build_corpus(authors, ignored_tokens, options.chunk_words);
    const auto& unknown_chunks = corpus.authors[0];
    if (unknown_chunks.size() < options.min_chunks) {
        return results;
    }

    // пул посторонних кандидата: остальные кандидаты и extra_impostors, у которых есть текст
    std::vector<std::vector<std::size_t>> pools(candidates.size());
    std::vector<char> usable(candidates.size(), 0);
    for (std::size_t c = 0; c < candidates.size(); ++c) {
        for (std::size_t a = 1; a < authors.size(); ++a) {
            const bool is_self = a == c + 1;
            if (!is_self && !corpus.authors[a].empty()) {
                pools[c].push_back(a);
            }
        }
        usable[c] = corpus.authors[c + 1].size() >= options.min_chunks &&
                    pools[c].size() >= options.min_impostors;
        results[c].impostors = pools[c].size();
    }

    std::mt19937 rng(options.seed);
    const auto threshold =
        static_cast<std::uint32_t>(std::llround(options.feature_fraction * 1e6));
    std::vector<char> mask(corpus.feature_count);
    std::vector<std::size_t> wins(candidates.size(), 0);

    for (std::size_t iteration = 0; iteration < options.iterations; ++iteration) {
        for (auto& bit : mask) {
            bit = (rng() % 1000000u) < threshold ? 1 : 0;
        }
        const IndexedVector& questioned = corpus.chunks[unknown_chunks[rng() % unknown_chunks.size()]];
        const double questioned_norm = masked_norm(questioned, mask);

        for (std::size_t c = 0; c < candidates.size(); ++c) {
            if (!usable[c]) {
                continue;
            }
            const auto& own = corpus.authors[c + 1];
            const IndexedVector& candidate_chunk = corpus.chunks[own[rng() % own.size()]];
            const double own_similarity =
                masked_cosine(questioned, questioned_norm, candidate_chunk, mask);

            // выбор не более max_impostors посторонних: частичная перестановка Фишера-Йетса
            std::vector<std::size_t> pool = pools[c];
            const std::size_t sample = std::min(options.max_impostors, pool.size());
            double best_impostor = 0.0;
            for (std::size_t k = 0; k < sample; ++k) {
                const std::size_t pick = k + rng() % (pool.size() - k);
                std::swap(pool[k], pool[pick]);
                const auto& chunks = corpus.authors[pool[k]];
                const IndexedVector& impostor_chunk = corpus.chunks[chunks[rng() % chunks.size()]];
                best_impostor = std::max(
                    best_impostor, masked_cosine(questioned, questioned_norm, impostor_chunk, mask));
            }
            if (own_similarity > best_impostor) {
                ++wins[c];
            }
        }
    }

    for (std::size_t c = 0; c < candidates.size(); ++c) {
        if (usable[c]) {
            results[c].available = true;
            results[c].iterations = options.iterations;
            results[c].score =
                static_cast<double>(wins[c]) / static_cast<double>(options.iterations);
        }
    }
    return results;
}

}  // namespace chatstyle
