#pragma once

// Детерминированные синтетические «авторы» для тестов Delta и Impostors.
// Выбор слов идёт через mt19937 и rng % n, а не через std::uniform_int_distribution: его
// результат зависит от стандартной библиотеки, а тесты должны совпадать на всех платформах.

#include <cstddef>
#include <random>
#include <string>
#include <vector>

namespace synthetic {

using Messages = std::vector<std::u32string>;

struct Generator {
    std::mt19937 engine;
    explicit Generator(unsigned seed) : engine(seed) {}
    std::size_t below(std::size_t limit) { return engine() % limit; }
};

// count сообщений по 8-14 слов из words; capitalize — заглавная первая буква («а»..«я»);
// ending добавляется в ending_percent процентах сообщений (100 — всегда, без вызова генератора)
inline Messages generate(const Messages& words, unsigned seed, std::size_t count, bool capitalize,
                         const std::u32string& ending, std::size_t ending_percent) {
    Generator rng(seed);
    Messages messages;
    for (std::size_t m = 0; m < count; ++m) {
        std::u32string text;
        const std::size_t length = 8 + rng.below(7);
        for (std::size_t w = 0; w < length; ++w) {
            std::u32string word = words[rng.below(words.size())];
            if (capitalize && w == 0) {
                word[0] -= 0x20;
            }
            text += (w ? U" " : U"") + word;
        }
        if (ending_percent >= 100 || (ending_percent > 0 && rng.below(100) < ending_percent)) {
            text += ending;
        }
        messages.push_back(text);
    }
    return messages;
}

inline Messages casual(unsigned seed, std::size_t count) {
    static const Messages words = {U"ну", U"типа", U"короче", U"блин", U"я", U"и", U"не", U"щас"};
    return generate(words, seed, count, false, U"))", 60);
}

inline Messages formal(unsigned seed, std::size_t count) {
    static const Messages words = {U"что",    U"для", U"при", U"также",
                                   U"однако", U"это", U"в",   U"поэтому"};
    return generate(words, seed, count, true, U".", 100);
}

// ещё четыре непохожих друг на друга стиля для «посторонних»
inline Messages other(unsigned style, unsigned seed, std::size_t count) {
    static const Messages plans = {U"да", U"нет", U"может", U"сегодня", U"завтра", U"потом", U"вечером", U"утром"};
    static const Messages work = {U"работа", U"проект", U"срок", U"отчёт", U"задача", U"встреча", U"клиент", U"план"};
    static const Messages nature = {U"кот", U"дом", U"лес", U"река", U"поле", U"город", U"море", U"гора"};
    static const Messages culture = {U"книга", U"фильм", U"музыка", U"игра", U"спорт", U"кино", U"театр", U"сад"};
    switch (style % 4) {
        case 0:
            return generate(plans, seed, count, false, U"", 0);
        case 1:
            return generate(work, seed, count, true, U"!", 100);
        case 2:
            return generate(nature, seed, count, false, U"?", 50);
        default:
            return generate(culture, seed, count, false, U"...", 30);
    }
}

}  // namespace synthetic
