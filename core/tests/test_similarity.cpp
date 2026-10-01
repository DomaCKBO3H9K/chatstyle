#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <chatstyle/similarity.hpp>
#include <vector>

using chatstyle::SparseVector;
using chatstyle::cosine;
using chatstyle::tfidf;

TEST_CASE("cosine of identical vectors", "[similarity]") {
    SparseVector a;
    a[U"x"] = 1.0;
    a[U"y"] = 2.0;
    SparseVector b = a;

    REQUIRE_THAT(cosine(a, b), Catch::Matchers::WithinAbs(1.0, 1e-12));
}

TEST_CASE("cosine of vectors with no common keys", "[similarity]") {
    SparseVector a;
    a[U"x"] = 1.0;
    SparseVector b;
    b[U"y"] = 1.0;

    REQUIRE_THAT(cosine(a, b), Catch::Matchers::WithinAbs(0.0, 1e-12));
}

TEST_CASE("cosine symmetry", "[similarity]") {
    SparseVector a;
    a[U"x"] = 1.0;
    a[U"y"] = 2.0;
    a[U"z"] = 3.0;
    SparseVector b;
    b[U"x"] = 4.0;
    b[U"w"] = 1.0;

    REQUIRE_THAT(cosine(a, b), Catch::Matchers::WithinAbs(cosine(b, a), 1e-12));
}

TEST_CASE("cosine with empty vectors", "[similarity]") {
    SparseVector a;
    a[U"x"] = 1.0;
    SparseVector empty;

    REQUIRE_THAT(cosine(empty, a), Catch::Matchers::WithinAbs(0.0, 1e-12));
    REQUIRE_THAT(cosine(a, empty), Catch::Matchers::WithinAbs(0.0, 1e-12));
    REQUIRE_THAT(cosine(empty, empty), Catch::Matchers::WithinAbs(0.0, 1e-12));
}

TEST_CASE("tfidf returns empty vector for empty input", "[similarity]") {
    std::vector<SparseVector> input;
    auto result = tfidf(input);
    REQUIRE(result.empty());
}

TEST_CASE("tfidf with three authors", "[similarity]") {
    SparseVector a;
    a[U"x"] = 1.0;
    a[U"y"] = 1.0;
    SparseVector b;
    b[U"x"] = 1.0;
    b[U"z"] = 1.0;
    SparseVector c;
    c[U"w"] = 1.0;

    auto r = tfidf({a, b, c});

    REQUIRE(r.size() == 3);
    REQUIRE_THAT(r[0].at(U"x"), Catch::Matchers::WithinAbs(1.2876820724517808, 1e-12));
    REQUIRE_THAT(r[0].at(U"y"), Catch::Matchers::WithinAbs(1.6931471805599454, 1e-12));
    REQUIRE_THAT(r[1].at(U"z"), Catch::Matchers::WithinAbs(1.6931471805599454, 1e-12));
    REQUIRE_THAT(cosine(r[0], r[1]), Catch::Matchers::WithinAbs(0.366446816266513, 1e-12));
    REQUIRE_THAT(cosine(r[0], r[2]), Catch::Matchers::WithinAbs(0.0, 1e-12));
}

TEST_CASE("tfidf with sublinear term frequency", "[similarity]") {
    SparseVector a;
    a[U"x"] = 3.0;
    a[U"y"] = 1.0;
    SparseVector b;
    b[U"x"] = 1.0;

    auto r = tfidf({a, b});

    REQUIRE_THAT(r[0].at(U"x"), Catch::Matchers::WithinAbs(2.09861228866811, 1e-12));
    REQUIRE_THAT(r[0].at(U"y"), Catch::Matchers::WithinAbs(1.4054651081081644, 1e-12));
    REQUIRE_THAT(r[1].at(U"x"), Catch::Matchers::WithinAbs(1.0, 1e-12));
    REQUIRE_THAT(cosine(r[0], r[1]), Catch::Matchers::WithinAbs(0.830880748357988, 1e-12));
}

TEST_CASE("tfidf with two identical authors", "[similarity]") {
    SparseVector a;
    a[U"x"] = 2.0;
    a[U"y"] = 1.0;

    auto r = tfidf({a, a});

    REQUIRE(r.size() == 2);
    REQUIRE_THAT(cosine(r[0], r[1]), Catch::Matchers::WithinAbs(1.0, 1e-12));
}

TEST_CASE("tfidf skips non-positive values", "[similarity]") {
    SparseVector a;
    a[U"x"] = 1.0;
    a[U"y"] = 0.0;
    a[U"z"] = -1.0;

    auto r = tfidf({a});

    REQUIRE(r.size() == 1);
    REQUIRE(r[0].size() == 1);
    REQUIRE(r[0].count(U"y") == 0);
    REQUIRE(r[0].count(U"z") == 0);
}
