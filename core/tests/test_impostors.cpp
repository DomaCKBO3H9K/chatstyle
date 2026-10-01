#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <chatstyle/impostors.hpp>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

#include "synthetic_text.hpp"

using chatstyle::general_impostors;
using chatstyle::ImpostorsOptions;
using chatstyle::ImpostorsResult;
using Catch::Matchers::WithinAbs;

namespace {

using Messages = synthetic::Messages;

ImpostorsOptions defaults(unsigned seed = 1) {
    ImpostorsOptions options;
    options.chunk_words = 100;  // по 60 сообщений на автора получается около шести кусков
    options.seed = seed;
    return options;
}

std::vector<Messages> four_extra_impostors() {
    return {synthetic::other(0, 11, 60), synthetic::other(1, 12, 60), synthetic::other(2, 13, 60),
            synthetic::other(3, 14, 60)};
}

std::vector<ImpostorsResult> run(const Messages& unknown, const std::vector<Messages>& candidates,
                                 const std::vector<Messages>& extra, const ImpostorsOptions& options) {
    return general_impostors(unknown, candidates, extra, {}, options);
}

}  // namespace

TEST_CASE("impostors: the same style wins, a different style loses", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60), synthetic::formal(3, 60)};
    const auto results = run(unknown, candidates, four_extra_impostors(), defaults());
    REQUIRE(results.size() == 2);
    REQUIRE(results[0].available);
    REQUIRE(results[1].available);
    REQUIRE(results[0].score > 0.9);
    REQUIRE(results[1].score < 0.2);
    // посторонние: остальные кандидаты и четыре дополнительных; сам кандидат в свой пул не входит
    REQUIRE(results[0].impostors == 5);
    REQUIRE(results[1].impostors == 5);
    REQUIRE(results[0].iterations == 100);
}

TEST_CASE("impostors: a copy of the unknown text is the best candidate", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    const auto results = run(unknown, {unknown}, four_extra_impostors(), defaults());
    REQUIRE(results[0].available);
    REQUIRE(results[0].impostors == 4);
    REQUIRE(results[0].score >= 0.9);
}

TEST_CASE("impostors: too few impostors makes the score unavailable", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60), synthetic::formal(3, 60)};

    const auto none = run(unknown, candidates, {}, defaults());  // у каждого один посторонний
    for (const auto& result : none) {
        REQUIRE_FALSE(result.available);
        REQUIRE(result.impostors == 1);
        REQUIRE(result.iterations == 0);
        REQUIRE(result.score == 0.0);
    }
    const auto two = run(unknown, candidates, {synthetic::other(0, 11, 60)}, defaults());
    REQUIRE_FALSE(two[0].available);  // 1 + 1 = 2 < 3
    const auto three = run(unknown, candidates, {synthetic::other(0, 11, 60), synthetic::other(1, 12, 60)},
                           defaults());
    REQUIRE(three[0].available);  // 1 + 2 = 3
    REQUIRE(three[1].available);
}

TEST_CASE("impostors: too little text on the unknown or candidate side", "[impostors]") {
    const std::vector<Messages> extra = four_extra_impostors();

    const Messages short_text = {U"привет", U"как дела", U"ну ладно"};  // меньше двух кусков
    const auto unknown_short = run(short_text, {synthetic::casual(2, 60)}, extra, defaults());
    REQUIRE_FALSE(unknown_short[0].available);
    REQUIRE(unknown_short[0].impostors == 4);  // пул считается и при недоступной оценке

    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {short_text, synthetic::casual(2, 60), {}};
    const auto results = run(unknown, candidates, extra, defaults());
    REQUIRE_FALSE(results[0].available);  // мало кусков
    REQUIRE(results[1].available);
    REQUIRE_FALSE(results[2].available);  // пустой кандидат
    REQUIRE(run({}, {synthetic::casual(2, 60)}, extra, defaults())[0].available == false);
}

TEST_CASE("impostors: no candidates", "[impostors]") {
    REQUIRE(run(synthetic::casual(1, 60), {}, four_extra_impostors(), defaults()).empty());
}

TEST_CASE("impostors: the result depends only on the input and the seed", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60), synthetic::formal(3, 60)};
    const auto extra = four_extra_impostors();
    const auto first = run(unknown, candidates, extra, defaults(7));
    const auto second = run(unknown, candidates, extra, defaults(7));
    for (std::size_t i = 0; i < first.size(); ++i) {
        REQUIRE(first[i].score == second[i].score);
        REQUIRE(first[i].available == second[i].available);
    }
}

TEST_CASE("impostors: score is a share of iterations", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    ImpostorsOptions options = defaults();
    options.iterations = 40;
    options.feature_fraction = 0.1;
    const auto results = run(unknown, {synthetic::casual(2, 60), synthetic::other(0, 5, 60)},
                             four_extra_impostors(), options);
    for (const auto& result : results) {
        REQUIRE(result.available);
        REQUIRE(result.iterations == 40);
        REQUIRE(result.score >= 0.0);
        REQUIRE(result.score <= 1.0);
        const double wins = result.score * 40.0;
        REQUIRE_THAT(wins, WithinAbs(std::round(wins), 1e-9));
    }
}

TEST_CASE("impostors: limits on sampled impostors and full feature set work", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    ImpostorsOptions options = defaults();
    options.max_impostors = 1;
    options.feature_fraction = 1.0;
    const auto results = run(unknown, {synthetic::casual(2, 60)}, four_extra_impostors(), options);
    REQUIRE(results[0].available);
    REQUIRE(results[0].impostors == 4);  // в пуле все четверо, в итерацию берётся один
    REQUIRE(results[0].score > 0.9);
}

TEST_CASE("impostors: invalid options are rejected", "[impostors]") {
    const auto unknown = synthetic::casual(1, 60);
    const std::vector<Messages> candidates = {synthetic::casual(2, 60)};
    const auto extra = four_extra_impostors();
    auto with = [&](auto change) {
        ImpostorsOptions options = defaults();
        change(options);
        return options;
    };
    REQUIRE_THROWS_AS(run(unknown, candidates, extra, with([](auto& o) { o.iterations = 0; })),
                      std::invalid_argument);
    REQUIRE_THROWS_AS(run(unknown, candidates, extra, with([](auto& o) { o.chunk_words = 0; })),
                      std::invalid_argument);
    REQUIRE_THROWS_AS(run(unknown, candidates, extra, with([](auto& o) { o.max_impostors = 0; })),
                      std::invalid_argument);
    REQUIRE_THROWS_AS(run(unknown, candidates, extra, with([](auto& o) { o.feature_fraction = 0.0; })),
                      std::invalid_argument);
    REQUIRE_THROWS_AS(run(unknown, candidates, extra, with([](auto& o) { o.feature_fraction = 1.5; })),
                      std::invalid_argument);
}
