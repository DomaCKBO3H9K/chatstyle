#include "chatstyle/compare.hpp"

#include <utility>

#include "chatstyle/ngrams.hpp"
#include "chatstyle/similarity.hpp"
#include "chatstyle/text.hpp"

namespace chatstyle {

namespace {

constexpr std::size_t kNgramMin = 1;
constexpr std::size_t kNgramMax = 4;

SparseVector author_ngrams(const std::vector<std::string>& messages) {
    std::vector<std::u32string> unicode_messages;
    unicode_messages.reserve(messages.size());
    for (const auto& message : messages) {
        unicode_messages.push_back(to_lower(utf8_to_u32(message)));
    }
    return count_char_ngrams(unicode_messages, kNgramMin, kNgramMax);
}

// counts[0] и weighted[0] — неизвестный автор, дальше кандидаты по порядку;
// IDF считается по всем авторам сразу
struct Analysis {
    std::vector<SparseVector> counts;
    std::vector<SparseVector> weighted;
};

Analysis analyze(const std::vector<std::string>& unknown,
                 const std::vector<std::vector<std::string>>& candidates) {
    Analysis analysis;
    analysis.counts.reserve(candidates.size() + 1);
    analysis.counts.push_back(author_ngrams(unknown));
    for (const auto& candidate : candidates) {
        analysis.counts.push_back(author_ngrams(candidate));
    }
    analysis.weighted = tfidf(analysis.counts);
    return analysis;
}

}  // namespace

std::vector<double> compare_to_unknown(const std::vector<std::string>& unknown,
                                       const std::vector<std::vector<std::string>>& candidates) {
    std::vector<double> result;
    if (candidates.empty()) {
        return result;
    }
    const Analysis analysis = analyze(unknown, candidates);
    result.reserve(candidates.size());
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        result.push_back(cosine(analysis.weighted[0], analysis.weighted[1 + i]));
    }
    return result;
}

std::vector<CandidateReport> compare_with_explanations(
    const std::vector<std::string>& unknown,
    const std::vector<std::vector<std::string>>& candidates, std::size_t top_k) {
    std::vector<CandidateReport> result;
    if (candidates.empty()) {
        return result;
    }
    const Analysis analysis = analyze(unknown, candidates);
    result.reserve(candidates.size());
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        const SparseVector& unknown_weights = analysis.weighted[0];
        const SparseVector& candidate_weights = analysis.weighted[1 + i];
        CandidateReport report;
        report.similarity = cosine(unknown_weights, candidate_weights);
        for (const auto& item : top_contributions(unknown_weights, candidate_weights, top_k)) {
            report.top_features.push_back({readable_ngram(item.feature), item.contribution,
                                           analysis.counts[0].at(item.feature),
                                           analysis.counts[1 + i].at(item.feature)});
        }
        result.push_back(std::move(report));
    }
    return result;
}

}  // namespace chatstyle
