#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace chatstyle {

// Меньше сообщений с отметкой времени: профиля ритма нет
constexpr std::size_t kRhythmMinMessages = 30;

// Ритм письма автора по моментам его сообщений. Восемь признаков в фиксированном порядке,
// каждый в [0, 1]:
//   burst_share — доля пауз между соседними сообщениями не длиннее минуты;
//   series_len  — средняя длина серии (серия — сообщения с паузами до минуты): (длина - 1) / 9,
//                 не больше 1;
//   gap_median  — медианная пауза среди пауз до шести часов (ночной перерыв не считается):
//                 log10(1 + пауза) / log10(1 + 21600);
//   night, morning, day, evening — доли сообщений в часы [0, 6), [6, 12), [12, 18), [18, 24);
//   weekend     — доля сообщений в субботу и воскресенье.
struct RhythmProfile {
    bool available = false;
    std::size_t messages = 0;
    std::vector<std::pair<std::u32string, double>> features;
};

// times — моменты сообщений автора в секундах от 1970-01-01 по ЛОКАЛЬНОМУ времени автора
// (часовой пояс уже учтён); порядок любой, функция сортирует копию
RhythmProfile rhythm_profile(const std::vector<std::int64_t>& times);

// Сходство профилей в [0, 1]: 1 - (сумма модулей разностей восьми признаков) / 8;
// если хотя бы один профиль недоступен, результат 0
double rhythm_similarity(const RhythmProfile& a, const RhythmProfile& b);

}  // namespace chatstyle
