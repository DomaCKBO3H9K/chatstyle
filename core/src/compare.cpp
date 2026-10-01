#include "chatstyle/compare.hpp"
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
        for (const auto& msg : messages) {
            unicode_messages.push_back(to_lower(utf8_to_u32(msg)));
        }
        return count_char_ngrams(unicode_messages, kNgramMin, kNgramMax);
    }
}

std::vector<double> compare_to_unknown(const std::vector<std::string>& unknown, const std::vector<std::vector<std::string>>& candidates) {
    if (candidates.empty()) {
        return {};
    }

    std::vector<SparseVector> counts;
    counts.reserve(candidates.size() + 1);
    counts.push_back(author_ngrams(unknown));
    for (const auto& candidate : candidates) {
        counts.push_back(author_ngrams(candidate));
    }

    auto weighted = tfidf(counts);

    std::vector<double> result;
    result.reserve(candidates.size());
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        result.push_back(cosine(weighted[0], weighted[1 + i]));
    }
    return result;
}

}
