#include "chatstyle/rhythm.hpp"

#include <algorithm>
#include <cmath>

namespace chatstyle {

namespace {

constexpr std::int64_t kBurstGap = 60;            // пауза не длиннее минуты — одна серия
constexpr std::int64_t kMaxSessionGap = 6 * 3600;  // длиннее — перерыв, а не пауза в разговоре
constexpr std::int64_t kSecondsPerDay = 86400;
constexpr std::size_t kFeatureCount = 8;
constexpr double kSeriesLengthCap = 10.0;  // серия в 10 сообщений и длиннее даёт 1

std::int64_t floor_mod(std::int64_t value, std::int64_t modulus) {
    const std::int64_t result = value % modulus;
    return result < 0 ? result + modulus : result;
}

std::int64_t floor_div(std::int64_t value, std::int64_t divisor) {
    return (value - floor_mod(value, divisor)) / divisor;
}

}  // namespace

RhythmProfile rhythm_profile(const std::vector<std::int64_t>& times) {
    RhythmProfile profile;
    profile.messages = times.size();
    if (times.size() < kRhythmMinMessages) {
        return profile;
    }

    std::vector<std::int64_t> sorted = times;
    std::sort(sorted.begin(), sorted.end());
    const double count = static_cast<double>(sorted.size());

    std::size_t burst_gaps = 0;
    std::size_t series = 1;
    std::vector<std::int64_t> session_gaps;
    for (std::size_t i = 1; i < sorted.size(); ++i) {
        const std::int64_t gap = sorted[i] - sorted[i - 1];
        if (gap <= kBurstGap) {
            ++burst_gaps;
        } else {
            ++series;
        }
        if (gap <= kMaxSessionGap) {
            session_gaps.push_back(gap);
        }
    }
    const double burst_share = static_cast<double>(burst_gaps) / (count - 1.0);
    const double mean_series = count / static_cast<double>(series);
    const double series_len = std::min((mean_series - 1.0) / (kSeriesLengthCap - 1.0), 1.0);

    double gap_median = 1.0;
    if (!session_gaps.empty()) {
        const std::size_t middle = session_gaps.size() / 2;
        std::nth_element(session_gaps.begin(), session_gaps.begin() + static_cast<std::ptrdiff_t>(middle),
                         session_gaps.end());
        double median = static_cast<double>(session_gaps[middle]);
        if (session_gaps.size() % 2 == 0) {
            const auto lower = std::max_element(session_gaps.begin(),
                                                session_gaps.begin() + static_cast<std::ptrdiff_t>(middle));
            median = (median + static_cast<double>(*lower)) / 2.0;
        }
        gap_median = std::min(std::log10(1.0 + median) / std::log10(1.0 + kMaxSessionGap), 1.0);
    }

    std::size_t parts[4] = {0, 0, 0, 0};
    std::size_t weekend = 0;
    for (const std::int64_t time : sorted) {
        const std::int64_t hour = floor_mod(time, kSecondsPerDay) / 3600;
        ++parts[hour / 6];
        // 1970-01-01 — четверг; понедельник — 0
        const std::int64_t weekday = floor_mod(floor_div(time, kSecondsPerDay) + 3, 7);
        if (weekday >= 5) {
            ++weekend;
        }
    }

    const double values[kFeatureCount] = {
        burst_share,
        series_len,
        gap_median,
        static_cast<double>(parts[0]) / count,
        static_cast<double>(parts[1]) / count,
        static_cast<double>(parts[2]) / count,
        static_cast<double>(parts[3]) / count,
        static_cast<double>(weekend) / count,
    };
    const char32_t* const names[kFeatureCount] = {U"burst_share", U"series_len", U"gap_median", U"night",
                                                  U"morning",     U"day",        U"evening",    U"weekend"};
    profile.available = true;
    for (std::size_t i = 0; i < kFeatureCount; ++i) {
        profile.features.emplace_back(names[i], values[i]);
    }
    return profile;
}

double rhythm_similarity(const RhythmProfile& a, const RhythmProfile& b) {
    if (!a.available || !b.available || a.features.size() != kFeatureCount ||
        b.features.size() != kFeatureCount) {
        return 0.0;
    }
    double distance = 0.0;
    for (std::size_t i = 0; i < kFeatureCount; ++i) {
        distance += std::fabs(a.features[i].second - b.features[i].second);
    }
    return 1.0 - distance / static_cast<double>(kFeatureCount);
}

}  // namespace chatstyle
