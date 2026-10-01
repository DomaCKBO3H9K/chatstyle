#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <chatstyle/compare.hpp>
#include <string>
#include <vector>

using chatstyle::compare_to_unknown;

TEST_CASE("[compare] identical texts", "[compare]") {
    std::vector<std::string> unknown = {"привет как дела"};
    std::vector<std::vector<std::string>> candidates = {{"привет как дела"}};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 1);
    REQUIRE_THAT(result[0], Catch::Matchers::WithinAbs(1.0, 1e-9));
}

TEST_CASE("[compare] case does not matter", "[compare]") {
    std::vector<std::string> unknown = {"ПРИВЕТ"};
    std::vector<std::vector<std::string>> candidates = {{"привет"}};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 1);
    REQUIRE_THAT(result[0], Catch::Matchers::WithinAbs(1.0, 1e-9));
}

TEST_CASE("[compare] no common n-grams", "[compare]") {
    std::vector<std::string> unknown = {"aaa"};
    std::vector<std::vector<std::string>> candidates = {{"ббб"}};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 1);
    REQUIRE_THAT(result[0], Catch::Matchers::WithinAbs(0.0, 1e-9));
}

TEST_CASE("[compare] ranking", "[compare]") {
    std::vector<std::string> unknown = {"привет как жизнь"};
    std::vector<std::vector<std::string>> candidates = {
        {"привет как дела", "привет, что делаешь"},
        {"Good morning everyone"}
    };
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 2);
    REQUIRE(result[0] > 0.0);
    // общий пробел даёт небольшое ненулевое сходство, поэтому проверяем разрыв, а не ноль
    REQUIRE(result[1] < 0.1);
    REQUIRE(result[0] > 5.0 * result[1]);
}

TEST_CASE("[compare] order matches candidate order", "[compare]") {
    std::vector<std::string> unknown = {"привет"};
    std::vector<std::vector<std::string>> candidates = {
        {"xyz"},
        {"привет"},
        {"xyz"}
    };
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 3);
    REQUIRE_THAT(result[0], Catch::Matchers::WithinAbs(0.0, 1e-9));
    REQUIRE_THAT(result[1], Catch::Matchers::WithinAbs(1.0, 1e-9));
    REQUIRE_THAT(result[2], Catch::Matchers::WithinAbs(0.0, 1e-9));
}

TEST_CASE("[compare] empty candidates list", "[compare]") {
    std::vector<std::string> unknown = {"привет"};
    std::vector<std::vector<std::string>> candidates = {};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.empty());
}

TEST_CASE("[compare] empty unknown", "[compare]") {
    std::vector<std::string> unknown = {};
    std::vector<std::vector<std::string>> candidates = {{"привет"}, {"hello"}};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 2);
    REQUIRE_THAT(result[0], Catch::Matchers::WithinAbs(0.0, 1e-9));
    REQUIRE_THAT(result[1], Catch::Matchers::WithinAbs(0.0, 1e-9));
}

TEST_CASE("[compare] candidate with no messages", "[compare]") {
    std::vector<std::string> unknown = {"привет"};
    std::vector<std::vector<std::string>> candidates = {{}};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 1);
    REQUIRE_THAT(result[0], Catch::Matchers::WithinAbs(0.0, 1e-9));
}

TEST_CASE("[compare] broken UTF-8 does not throw", "[compare]") {
    std::vector<std::string> unknown = {std::string("a\x80" "b", 3), std::string("\xFF", 1)};
    std::vector<std::vector<std::string>> candidates = {{"ab", "привет"}};
    auto result = compare_to_unknown(unknown, candidates);
    REQUIRE(result.size() == 1);
    REQUIRE(result[0] >= 0.0);
    REQUIRE(result[0] <= 1.0);
}

TEST_CASE("[compare] explanations: top features are readable and sorted", "[compare]") {
    const std::vector<std::string> unknown = {"привет как дела"};
    const std::vector<std::vector<std::string>> candidates = {{"привет как дела"}, {"hello world"}};
    const auto reports = chatstyle::compare_with_explanations(unknown, candidates, 5);
    REQUIRE(reports.size() == 2);

    const auto& same = reports[0];
    REQUIRE_THAT(same.similarity, Catch::Matchers::WithinAbs(1.0, 1e-9));
    REQUIRE(same.top_features.size() == 5);
    for (std::size_t i = 0; i < same.top_features.size(); ++i) {
        const auto& item = same.top_features[i];
        REQUIRE(item.contribution > 0.0);
        REQUIRE(item.unknown_count > 0.0);
        REQUIRE(item.candidate_count > 0.0);
        for (const char32_t cp : item.feature) {
            REQUIRE(cp != 0x02);
            REQUIRE(cp != 0x03);
            REQUIRE(cp != U' ');
        }
        if (i > 0) {
            REQUIRE(item.contribution <= same.top_features[i - 1].contribution);
        }
    }
    // единственная общая n-грамма с английским текстом — пробел
    REQUIRE(reports[1].top_features.size() == 1);
    REQUIRE(reports[1].top_features[0].feature == U"␣");
    REQUIRE(reports[1].similarity > 0.0);
}

TEST_CASE("[compare] explanations agree with compare_to_unknown and sum to similarity", "[compare]") {
    const std::vector<std::string> unknown = {"ну привет)) как дела", "щас приду"};
    const std::vector<std::vector<std::string>> candidates = {{"ну привет как жизнь))", "щас буду"}};
    const auto plain = compare_to_unknown(unknown, candidates);
    const auto reports = chatstyle::compare_with_explanations(unknown, candidates, 100000);
    REQUIRE(reports.size() == 1);
    REQUIRE(reports[0].similarity == plain[0]);
    double total = 0.0;
    for (const auto& item : reports[0].top_features) {
        total += item.contribution;
    }
    REQUIRE_THAT(total, Catch::Matchers::WithinAbs(plain[0], 1e-9));
}

TEST_CASE("[compare] explanations: top_k zero and no candidates", "[compare]") {
    const std::vector<std::string> unknown = {"привет"};
    const auto none = chatstyle::compare_with_explanations(unknown, {}, 5);
    REQUIRE(none.empty());
    const auto zero = chatstyle::compare_with_explanations(unknown, {{"привет"}}, 0);
    REQUIRE(zero.size() == 1);
    REQUIRE(zero[0].top_features.empty());
    REQUIRE_THAT(zero[0].similarity, Catch::Matchers::WithinAbs(1.0, 1e-9));
}
