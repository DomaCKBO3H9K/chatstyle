#include <catch2/catch_test_macros.hpp>
#include <chatstyle/version.hpp>

TEST_CASE("version is reported", "[smoke]") {
    REQUIRE(chatstyle::version() == "0.1.0");
}
