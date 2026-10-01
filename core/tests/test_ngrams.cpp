#include <catch2/catch_test_macros.hpp>
#include <chatstyle/ngrams.hpp>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
    std::u32string mk(std::u32string s) {
        for (auto& c : s) {
            if (c == U'^') c = chatstyle::kStartMarker;
            else if (c == U'$') c = chatstyle::kEndMarker;
        }
        return s;
    }
}

TEST_CASE("ngrams: count_char_ngrams basic", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"ab"}, 1, 2);
    REQUIRE(r.size() == 5);
    REQUIRE(r.at(mk(U"a")) == 1);
    REQUIRE(r.at(mk(U"b")) == 1);
    REQUIRE(r.at(mk(U"^a")) == 1);
    REQUIRE(r.at(mk(U"ab")) == 1);
    REQUIRE(r.at(mk(U"b$")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams single char", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"a"}, 1, 4);
    REQUIRE(r.size() == 4);
    REQUIRE(r.at(mk(U"a")) == 1);
    REQUIRE(r.at(mk(U"^a")) == 1);
    REQUIRE(r.at(mk(U"a$")) == 1);
    REQUIRE(r.at(mk(U"^a$")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams double same char", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"aa"}, 1, 2);
    REQUIRE(r.size() == 4);
    REQUIRE(r.at(mk(U"a")) == 2);
    REQUIRE(r.at(mk(U"^a")) == 1);
    REQUIRE(r.at(mk(U"aa")) == 1);
    REQUIRE(r.at(mk(U"a$")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams two messages", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"ab", U"ba"}, 2, 2);
    REQUIRE(r.size() == 6);
    REQUIRE(r.at(mk(U"ab")) == 1);
    REQUIRE(r.at(mk(U"ba")) == 1);
    REQUIRE(r.at(mk(U"^a")) == 1);
    REQUIRE(r.at(mk(U"b$")) == 1);
    REQUIRE(r.at(mk(U"^b")) == 1);
    REQUIRE(r.at(mk(U"a$")) == 1);
    REQUIRE(r.count(U"bb") == 0);
}

TEST_CASE("ngrams: count_char_ngrams cyrillic", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"да"}, 2, 2);
    REQUIRE(r.size() == 3);
    REQUIRE(r.at(mk(U"^д")) == 1);
    REQUIRE(r.at(mk(U"да")) == 1);
    REQUIRE(r.at(mk(U"а$")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams emoji", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"😀a"}, 1, 1);
    REQUIRE(r.size() == 2);
    REQUIRE(r.at(mk(U"😀")) == 1);
    REQUIRE(r.at(mk(U"a")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams empty input", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({}, 1, 2);
    REQUIRE(r.empty());
    auto r2 = chatstyle::count_char_ngrams({U""}, 1, 2);
    REQUIRE(r2.empty());
}

TEST_CASE("ngrams: count_char_ngrams empty string with non-empty", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"", U"a"}, 1, 2);
    REQUIRE(r.size() == 3);
    REQUIRE(r.at(mk(U"a")) == 1);
    REQUIRE(r.at(mk(U"^a")) == 1);
    REQUIRE(r.at(mk(U"a$")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams duplicate messages", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"ab", U"ab"}, 1, 2);
    REQUIRE(r.size() == 5);
    REQUIRE(r.at(mk(U"a")) == 2);
    REQUIRE(r.at(mk(U"b")) == 2);
    REQUIRE(r.at(mk(U"^a")) == 2);
    REQUIRE(r.at(mk(U"ab")) == 2);
    REQUIRE(r.at(mk(U"b$")) == 2);
}

TEST_CASE("ngrams: count_char_ngrams unigrams only no markers", "[ngrams]") {
    auto r = chatstyle::count_char_ngrams({U"ab"}, 1, 1);
    REQUIRE(r.size() == 2);
    REQUIRE(r.at(mk(U"a")) == 1);
    REQUIRE(r.at(mk(U"b")) == 1);
}

TEST_CASE("ngrams: count_char_ngrams invalid ranges", "[ngrams]") {
    REQUIRE_THROWS_AS(chatstyle::count_char_ngrams({U"a"}, 0, 2), std::invalid_argument);
    REQUIRE_THROWS_AS(chatstyle::count_char_ngrams({U"a"}, 3, 2), std::invalid_argument);
}
