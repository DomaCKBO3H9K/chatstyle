#include <catch2/catch_test_macros.hpp>
#include <chatstyle/charlm.hpp>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

using chatstyle::CharLmOptions;
using chatstyle::charlm_compare;
using Messages = std::vector<std::u32string>;

namespace {

const Messages kCats = {U"кот сидит дома", U"кот спит на диване", U"мой кот любит молоко",
                        U"кот сидит у окна"};
const Messages kRiver = {U"ночь тихая река", U"река течёт под мостом", U"над рекой тихая ночь",
                         U"тихая река шумит"};

}  // namespace

TEST_CASE("charlm: unknown is closer to the candidate it resembles") {
    const Messages unknown = {U"кот сидит дома у окна", U"мой кот спит"};
    const auto results = charlm_compare(unknown, {kCats, kRiver}, CharLmOptions{});
    REQUIRE(results.size() == 2);
    REQUIRE(results[0].available);
    REQUIRE(results[1].available);
    REQUIRE(results[0].llr > 0.0);
    REQUIRE(results[1].llr < 0.0);
    REQUIRE(results[0].bits_candidate < results[0].bits_rest);
}

TEST_CASE("charlm: two candidates give mirrored scores") {
    const Messages unknown = {U"кот сидит у реки", U"тихая ночь"};
    const auto results = charlm_compare(unknown, {kCats, kRiver}, CharLmOptions{});
    REQUIRE(std::abs(results[0].llr + results[1].llr) < 1e-9);
    REQUIRE(results[0].chars_scored == results[1].chars_scored);
}

TEST_CASE("charlm: no score without text, a second candidate or with an empty candidate") {
    const Messages unknown = {U"кот сидит дома"};
    REQUIRE_FALSE(charlm_compare({}, {kCats, kRiver}, CharLmOptions{})[0].available);
    REQUIRE_FALSE(charlm_compare(unknown, {kCats}, CharLmOptions{})[0].available);

    const auto with_empty = charlm_compare(unknown, {kCats, Messages{}}, CharLmOptions{});
    REQUIRE_FALSE(with_empty[0].available);
    REQUIRE_FALSE(with_empty[1].available);

    const auto three = charlm_compare(unknown, {kCats, Messages{}, kRiver}, CharLmOptions{});
    REQUIRE(three[0].available);
    REQUIRE_FALSE(three[1].available);
    REQUIRE(three[2].available);
}

TEST_CASE("charlm: order zero is rejected") {
    CharLmOptions options;
    options.order = 0;
    REQUIRE_THROWS_AS(charlm_compare({U"кот"}, {kCats, kRiver}, options), std::invalid_argument);
}

TEST_CASE("charlm: cyrillic is counted by codepoints plus an end marker per message") {
    const Messages unknown = {U"привет", U"мир"};
    const auto results = charlm_compare(unknown, {kCats, kRiver}, CharLmOptions{});
    REQUIRE(results[0].chars_scored == 6 + 3 + 2);
}

TEST_CASE("charlm: repeated run gives the same numbers") {
    const Messages unknown = {U"кот сидит у реки", U"тихая ночь"};
    const auto first = charlm_compare(unknown, {kCats, kRiver}, CharLmOptions{});
    const auto second = charlm_compare(unknown, {kCats, kRiver}, CharLmOptions{});
    for (std::size_t i = 0; i < first.size(); ++i) {
        REQUIRE(first[i].llr == second[i].llr);
        REQUIRE(first[i].bits_rest == second[i].bits_rest);
    }
}

TEST_CASE("charlm: balancing denies a long candidate an advantage") {
    Messages long_cats = kCats;
    for (int i = 0; i < 20; ++i) {
        long_cats.insert(long_cats.end(), kCats.begin(), kCats.end());
    }
    const Messages unknown = {U"над рекой тихая ночь", U"течёт под мостом"};
    CharLmOptions balanced;
    const auto results = charlm_compare(unknown, {long_cats, kRiver}, balanced);
    REQUIRE(results[1].llr > 0.0);
}
