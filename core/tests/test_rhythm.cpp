#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <chatstyle/rhythm.hpp>
#include <cstdint>
#include <string>
#include <vector>

using Catch::Approx;
using chatstyle::kRhythmMinMessages;
using chatstyle::rhythm_profile;
using chatstyle::rhythm_similarity;
using chatstyle::RhythmProfile;

namespace {

constexpr std::int64_t kDay = 86400;
const double kGapNorm = std::log10(1.0 + 21600.0);
// 1970-01-05 00:00 — понедельник
constexpr std::int64_t kMonday = 4 * kDay;

double feature(const RhythmProfile& profile, const std::u32string& name) {
    for (const auto& item : profile.features) {
        if (item.first == name) {
            return item.second;
        }
    }
    FAIL("no such feature");
    return 0.0;
}

// n сообщений подряд с шагом step секунд от start
std::vector<std::int64_t> sequence(std::int64_t start, std::int64_t step, std::size_t n) {
    std::vector<std::int64_t> times;
    for (std::size_t i = 0; i < n; ++i) {
        times.push_back(start + static_cast<std::int64_t>(i) * step);
    }
    return times;
}

}  // namespace

TEST_CASE("rhythm: too few messages gives no profile") {
    const auto profile = rhythm_profile(sequence(kMonday, 10, kRhythmMinMessages - 1));
    REQUIRE_FALSE(profile.available);
    REQUIRE(profile.messages == kRhythmMinMessages - 1);
    REQUIRE(profile.features.empty());
    REQUIRE_FALSE(rhythm_profile({}).available);
}

TEST_CASE("rhythm: one long burst at noon on a weekday") {
    // 40 сообщений с шагом 10 секунд, начиная с 12:00 понедельника
    const auto profile = rhythm_profile(sequence(kMonday + 12 * 3600, 10, 40));
    REQUIRE(profile.available);
    REQUIRE(profile.features.size() == 8);
    REQUIRE(feature(profile, U"burst_share") == Approx(1.0));
    REQUIRE(feature(profile, U"series_len") == Approx(1.0));  // серия из 40: больше 10
    REQUIRE(feature(profile, U"day") == Approx(1.0));
    REQUIRE(feature(profile, U"night") == Approx(0.0));
    REQUIRE(feature(profile, U"weekend") == Approx(0.0));
    // медианная пауза 10 секунд: log10(11) / log10(21601)
    REQUIRE(feature(profile, U"gap_median") == Approx(std::log10(11.0) / kGapNorm));
}

TEST_CASE("rhythm: single messages hours apart are not bursts") {
    // 30 сообщений с шагом час, начиная с субботы 00:00
    const auto profile = rhythm_profile(sequence(kMonday + 5 * kDay, 3600, 30));
    REQUIRE(profile.available);
    REQUIRE(feature(profile, U"burst_share") == Approx(0.0));
    REQUIRE(feature(profile, U"series_len") == Approx(0.0));
    // суббота 00:00 + 30 часов: суббота (24 сообщения) и воскресенье (6 сообщений) — все в выходные
    REQUIRE(feature(profile, U"weekend") == Approx(1.0));
    REQUIRE(feature(profile, U"night") == Approx(12.0 / 30.0));
    REQUIRE(feature(profile, U"morning") == Approx(6.0 / 30.0));
    REQUIRE(feature(profile, U"day") == Approx(6.0 / 30.0));
    REQUIRE(feature(profile, U"evening") == Approx(6.0 / 30.0));
    // шаг час: медиана 3600 секунд
    REQUIRE(feature(profile, U"gap_median") == Approx(std::log10(3601.0) / kGapNorm));
}

TEST_CASE("rhythm: input order does not matter and shares sum to one") {
    auto times = sequence(kMonday, 4000, 50);
    const auto forward = rhythm_profile(times);
    std::vector<std::int64_t> reversed(times.rbegin(), times.rend());
    const auto backward = rhythm_profile(reversed);
    REQUIRE(rhythm_similarity(forward, backward) == Approx(1.0));
    const double parts = feature(forward, U"night") + feature(forward, U"morning") +
                         feature(forward, U"day") + feature(forward, U"evening");
    REQUIRE(parts == Approx(1.0));
}

TEST_CASE("rhythm: overnight breaks do not count as pauses") {
    // 15 сообщений вечером и 15 следующим утром: единственная большая пауза — ночь (больше 6 часов)
    auto times = sequence(kMonday + 20 * 3600, 60, 15);
    const auto morning = sequence(kMonday + kDay + 8 * 3600, 60, 15);
    times.insert(times.end(), morning.begin(), morning.end());
    const auto profile = rhythm_profile(times);
    REQUIRE(profile.available);
    // все остальные паузы по 60 секунд: медиана 60
    REQUIRE(feature(profile, U"gap_median") == Approx(std::log10(61.0) / kGapNorm));
}

TEST_CASE("rhythm: similarity is 1 for equal profiles and 0 when unavailable") {
    const auto a = rhythm_profile(sequence(kMonday, 30, 40));
    REQUIRE(rhythm_similarity(a, a) == Approx(1.0));
    REQUIRE(rhythm_similarity(a, RhythmProfile{}) == Approx(0.0));
    REQUIRE(rhythm_similarity(RhythmProfile{}, RhythmProfile{}) == Approx(0.0));
}

TEST_CASE("rhythm: day and night authors are less similar than two day authors") {
    const auto day_one = rhythm_profile(sequence(kMonday + 11 * 3600, 3000, 40));
    const auto day_two = rhythm_profile(sequence(kMonday + 12 * 3600, 3100, 40));
    const auto night = rhythm_profile(sequence(kMonday + 1 * 3600, 60, 40));
    REQUIRE(rhythm_similarity(day_one, day_two) > rhythm_similarity(day_one, night));
}

TEST_CASE("rhythm: negative times before 1970 are handled") {
    // 1969-12-29 (понедельник) 12:00: время отрицательное
    const auto profile = rhythm_profile(sequence(-3 * kDay + 12 * 3600, 10, 40));
    REQUIRE(profile.available);
    REQUIRE(feature(profile, U"day") == Approx(1.0));
    REQUIRE(feature(profile, U"weekend") == Approx(0.0));
}
