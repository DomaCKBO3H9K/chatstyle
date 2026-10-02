#include <algorithm>
#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <chatstyle/delta.hpp>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

#include "synthetic_text.hpp"

using chatstyle::burrows_delta;
using chatstyle::DeltaOptions;
using chatstyle::split_into_chunks;
using chatstyle::StyleLexicon;
using Catch::Matchers::WithinAbs;

namespace {

using Messages = synthetic::Messages;

std::vector<std::size_t> chunk_sizes(const Messages& messages, std::size_t chunk_words,
                                     const Messages& ignored = {}) {
    std::vector<std::size_t> sizes;
    for (const auto& chunk : split_into_chunks(messages, chunk_words, ignored)) {
        sizes.push_back(chunk.size());
    }
    return sizes;
}

DeltaOptions options(std::size_t chunk_words, std::size_t min_chunks = 6,
                     std::size_t top_words = 100) {
    DeltaOptions result;
    result.chunk_words = chunk_words;
    result.min_chunks = min_chunks;
    result.top_words = top_words;
    return result;
}

StyleLexicon chat_lexicon() {
    StyleLexicon lexicon;
    lexicon.function_words = {U"и", U"не",   U"что",    U"для", U"при", U"также",
                              U"однако", U"это", U"в", U"поэтому", U"я"};
    lexicon.filler_words = {U"ну", U"типа", U"короче", U"блин", U"щас"};
    return lexicon;
}

}  // namespace

// --- нарезка на куски ---

TEST_CASE("delta: chunks close by word count and a short rest is merged", "[delta]") {
    const Messages seven = {U"а", U"б", U"в", U"г", U"д", U"е", U"ж"};
    REQUIRE(chunk_sizes(seven, 3) == std::vector<std::size_t>{3, 4});  // остаток 1 < 3/2
}

TEST_CASE("delta: a long enough rest becomes its own chunk", "[delta]") {
    const Messages eight = {U"а", U"б", U"в", U"г", U"д", U"е", U"ж", U"з"};
    REQUIRE(chunk_sizes(eight, 3) == std::vector<std::size_t>{3, 3, 2});  // остаток 2*2 >= 3
}

TEST_CASE("delta: a single short text stays one chunk", "[delta]") {
    REQUIRE(chunk_sizes({U"раз", U"два"}, 100) == std::vector<std::size_t>{2});
}

TEST_CASE("delta: messages are never split", "[delta]") {
    const Messages messages = {U"раз два", U"три", U"четыре пять шесть"};
    REQUIRE(chunk_sizes(messages, 3) == std::vector<std::size_t>{2, 1});
}

TEST_CASE("delta: ignored tokens are not counted as words", "[delta]") {
    const Messages messages = {U"<URL> раз", U"два"};
    REQUIRE(chunk_sizes(messages, 2, {U"<URL>"}) == std::vector<std::size_t>{2});
    REQUIRE(chunk_sizes(messages, 2) == std::vector<std::size_t>{1, 1});  // «URL» считается словом
}

TEST_CASE("delta: chunking edge cases", "[delta]") {
    REQUIRE(split_into_chunks({}, 5, {}).empty());
    REQUIRE_THROWS_AS(split_into_chunks({U"а"}, 0, {}), std::invalid_argument);
    REQUIRE_THROWS_AS(burrows_delta({U"а"}, {{U"б"}}, StyleLexicon{}, options(0)),
                      std::invalid_argument);
}

// --- Delta: точный пример ---

TEST_CASE("delta: hand-computed example with a single varying feature", "[delta]") {
    // каждое сообщение — один кусок; меняется только r:avg_chars (остальное константно):
    // значения по кускам 2,2,2,4,4,4,2,3,3, sigma = 0.927960727138337
    const Messages unknown = {U"aa", U"aa", U"aa"};
    const std::vector<Messages> candidates = {{U"aaaa", U"aaaa", U"aaaa"}, {U"aa", U"aaa", U"aaa"}};
    StyleLexicon base_only;
    base_only.groups = 0;  // один меняющийся признак: группы привычек выключены
    const auto results = burrows_delta(unknown, candidates, base_only, options(1));
    REQUIRE(results.size() == 2);
    for (const auto& result : results) {
        REQUIRE(result.available);
        REQUIRE(result.features_used == 1);
        REQUIRE(result.differences.size() == 1);
        REQUIRE(result.differences[0].feature == U"r:avg_chars");
        REQUIRE_THAT(result.differences[0].sigma, WithinAbs(0.927960727138337, 1e-12));
    }
    REQUIRE_THAT(results[0].delta, WithinAbs(2.155263624321299, 1e-9));
    REQUIRE_THAT(results[1].delta, WithinAbs(0.7184212081070994, 1e-9));
    // знак: у неизвестного значение меньше, чем у кандидата
    REQUIRE_THAT(results[0].differences[0].z_difference, WithinAbs(-2.155263624321299, 1e-9));
    REQUIRE_THAT(results[0].differences[0].unknown_value, WithinAbs(2.0, 1e-12));
    REQUIRE_THAT(results[0].differences[0].candidate_value, WithinAbs(4.0, 1e-12));
}

// --- доступность ---

TEST_CASE("delta: unavailable with too few chunks", "[delta]") {
    const auto results = burrows_delta({U"aa", U"aaa"}, {{U"aaaa", U"a"}}, StyleLexicon{}, options(1, 6));
    REQUIRE(results.size() == 1);
    REQUIRE_FALSE(results[0].available);
    REQUIRE(results[0].differences.empty());
    REQUIRE(results[0].delta == 0.0);
}

TEST_CASE("delta: unavailable when the unknown author has no text", "[delta]") {
    const auto results = burrows_delta({}, {{U"aa", U"aaa", U"aaaa", U"a", U"aa", U"aaa"}},
                                       StyleLexicon{}, options(1, 2));
    REQUIRE_FALSE(results[0].available);
}

TEST_CASE("delta: an empty candidate is unavailable, the others are not", "[delta]") {
    const Messages unknown = {U"aa", U"aa", U"aaa"};
    const std::vector<Messages> candidates = {{}, {U"aaaa", U"aaaa", U"a"}};
    const auto results = burrows_delta(unknown, candidates, StyleLexicon{}, options(1, 2));
    REQUIRE_FALSE(results[0].available);
    REQUIRE(results[1].available);
    REQUIRE(results[1].delta > 0.0);
}

TEST_CASE("delta: no candidates and no variation", "[delta]") {
    REQUIRE(burrows_delta({U"aa"}, {}, StyleLexicon{}, options(1)).empty());
    // одинаковые сообщения: все признаки константны, сравнивать нечего
    const Messages same = {U"aa", U"aa", U"aa"};
    const auto results = burrows_delta(same, {same}, StyleLexicon{}, options(1));
    REQUIRE_FALSE(results[0].available);
}

// --- выбор признаков и порядок ---

TEST_CASE("delta: top_words limits word features, ties are broken by key", "[delta]") {
    // «в» и «и» одинаково частые и оба меняются между кусками
    StyleLexicon lexicon;
    lexicon.function_words = {U"и", U"в"};
    const Messages unknown = {U"и и и", U"и и в", U"и и и"};
    const std::vector<Messages> candidates = {{U"в в в", U"в и в", U"в в в"}};

    const auto many = burrows_delta(unknown, candidates, lexicon, options(3, 6, 100));
    const auto one = burrows_delta(unknown, candidates, lexicon, options(3, 6, 1));
    auto count_words = [](const chatstyle::DeltaResult& result) {
        return std::count_if(result.differences.begin(), result.differences.end(),
                             [](const auto& d) { return d.feature.compare(0, 3, U"fw:") == 0; });
    };
    REQUIRE(count_words(many[0]) == 2);
    REQUIRE(count_words(one[0]) == 1);
    for (const auto& d : one[0].differences) {
        REQUIRE(d.feature != U"fw:и");  // при равных средних выбирается меньший ключ: «в» < «и»
    }
}

TEST_CASE("delta: differences are sorted by absolute difference", "[delta]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::formal(3, 60)};
    const auto results = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    REQUIRE(results[0].available);
    const auto& diffs = results[0].differences;
    REQUIRE(diffs.size() == results[0].features_used);
    for (std::size_t i = 1; i < diffs.size(); ++i) {
        REQUIRE(std::fabs(diffs[i - 1].z_difference) >= std::fabs(diffs[i].z_difference));
    }
    // delta — среднее модулей
    double total = 0.0;
    for (const auto& d : diffs) {
        total += std::fabs(d.z_difference);
    }
    REQUIRE_THAT(results[0].delta, WithinAbs(total / static_cast<double>(diffs.size()), 1e-12));
}

// --- синтетические стили ---

TEST_CASE("delta: same style is much closer than a different style", "[delta]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60), synthetic::formal(3, 60)};
    const auto results = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    REQUIRE(results[0].available);
    REQUIRE(results[1].available);
    REQUIRE(results[0].delta < results[1].delta);
    REQUIRE(results[1].delta > 2.0 * results[0].delta);
}

TEST_CASE("delta: result is deterministic", "[delta]") {
    const auto unknown = synthetic::casual(1, 40);
    const std::vector<Messages> candidates = {synthetic::casual(2, 40), synthetic::formal(3, 40)};
    const auto first = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    const auto second = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    REQUIRE(first.size() == second.size());
    for (std::size_t i = 0; i < first.size(); ++i) {
        REQUIRE(first[i].delta == second[i].delta);
        REQUIRE(first[i].differences.size() == second[i].differences.size());
    }
}

// --- косинусная Delta ---

TEST_CASE("delta: cosine ranks the same style first and needs two non-empty candidates", "[delta]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60), synthetic::formal(3, 60)};
    const auto results = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    REQUIRE(results[0].cosine_available);
    REQUIRE(results[1].cosine_available);
    REQUIRE(results[0].cosine > results[1].cosine);
    for (const auto& result : results) {
        REQUIRE(result.cosine >= -1.0);
        REQUIRE(result.cosine <= 1.0);
    }
}

TEST_CASE("delta: cosine is unavailable for a single candidate", "[delta]") {
    // профиль неизвестного и единственного кандидата зеркальны относительно среднего: -1 всегда
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60)};
    const auto results = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    REQUIRE(results[0].available);
    REQUIRE_FALSE(results[0].cosine_available);
}

TEST_CASE("delta: an empty candidate does not count towards the two needed for cosine", "[delta]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60), Messages{}};
    const auto results = burrows_delta(unknown, candidates, chat_lexicon(), options(50));
    REQUIRE(results[0].available);
    REQUIRE_FALSE(results[0].cosine_available);
    REQUIRE_FALSE(results[1].available);

    const std::vector<Messages> three = {synthetic::casual(2, 60), Messages{}, synthetic::formal(3, 60)};
    const auto with_two = burrows_delta(unknown, three, chat_lexicon(), options(50));
    REQUIRE(with_two[0].cosine_available);
    REQUIRE_FALSE(with_two[1].cosine_available);
    REQUIRE(with_two[2].cosine_available);
}

TEST_CASE("delta: cosine does not depend on the order of candidates", "[delta]") {
    const auto unknown = synthetic::casual(1, 60);
    const Messages a = synthetic::casual(2, 60);
    const Messages b = synthetic::formal(3, 60);
    const auto forward = burrows_delta(unknown, {a, b}, chat_lexicon(), options(50));
    const auto backward = burrows_delta(unknown, {b, a}, chat_lexicon(), options(50));
    REQUIRE_THAT(forward[0].cosine, WithinAbs(backward[1].cosine, 1e-12));
    REQUIRE_THAT(forward[1].cosine, WithinAbs(backward[0].cosine, 1e-12));
}
