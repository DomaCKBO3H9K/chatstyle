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
