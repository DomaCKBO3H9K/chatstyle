#include "chatstyle/style_features.hpp"

#include <cstddef>
#include <unordered_map>

#include "chatstyle/text.hpp"

namespace chatstyle {

namespace {

struct PunctuationCounts {
    double paren1 = 0;
    double paren2 = 0;
    double paren3 = 0;
    double ellipsis = 0;
    double excl1 = 0;
    double excl2 = 0;
    double quest1 = 0;
    double quest2 = 0;
};

bool is_space(char32_t cp) {
    return cp == U' ' || cp == U'\t' || cp == U'\n' || cp == U'\r' || cp == 0xA0;
}

bool is_emoji(char32_t cp) {
    if (cp >= 0x1F3FB && cp <= 0x1F3FF) {
        return false;  // модификаторы тона кожи входят в эмодзи, отдельно не считаются
    }
    return (cp >= 0x1F300 && cp <= 0x1FAFF) || (cp >= 0x2600 && cp <= 0x27BF) || cp == 0x2B50 ||
           cp == 0x2B55;
}

// Заменяет служебные метки на пробел и обрезает пробелы по краям
std::u32string clean_message(std::u32string text, const std::vector<std::u32string>& tokens) {
    for (const auto& token : tokens) {
        if (token.empty()) {
            continue;
        }
        std::size_t pos = 0;
        while ((pos = text.find(token, pos)) != std::u32string::npos) {
            text.replace(pos, token.size(), U" ");
            ++pos;
        }
    }
    std::size_t begin = 0;
    std::size_t end = text.size();
    while (begin < end && is_space(text[begin])) {
        ++begin;
    }
    while (end > begin && is_space(text[end - 1])) {
        --end;
    }
    return text.substr(begin, end - begin);
}

void count_punctuation(const std::u32string& text, PunctuationCounts& counts) {
    const std::size_t size = text.size();
    std::size_t i = 0;
    while (i < size) {
        const char32_t ch = text[i];
        std::size_t j = i;
        while (j < size && text[j] == ch) {
            ++j;
        }
        const std::size_t length = j - i;
        switch (ch) {
            case U')':
                (length == 1 ? counts.paren1 : length == 2 ? counts.paren2 : counts.paren3) += 1;
                break;
            case U'.':
                if (length >= 3) {
                    counts.ellipsis += 1;
                }
                break;
            case 0x2026:  // «…»
                counts.ellipsis += 1;
                break;
            case U'!':
                (length == 1 ? counts.excl1 : counts.excl2) += 1;
                break;
            case U'?':
                (length == 1 ? counts.quest1 : counts.quest2) += 1;
                break;
            default:
                break;
        }
        i = j;
    }
}

// Слово: серия букв, внутри допускается один дефис между буквами («что-то»)
std::size_t count_words(const std::u32string& lowered,
                        std::unordered_map<std::u32string, std::size_t>* counts) {
    const std::size_t size = lowered.size();
    std::size_t total = 0;
    std::size_t i = 0;
    while (i < size) {
        if (!is_letter(lowered[i])) {
            ++i;
            continue;
        }
        std::size_t j = i + 1;
        while (j < size) {
            if (is_letter(lowered[j])) {
                ++j;
            } else if (lowered[j] == U'-' && j + 1 < size && is_letter(lowered[j + 1])) {
                j += 2;
            } else {
                break;
            }
        }
        if (counts != nullptr) {
            ++(*counts)[lowered.substr(i, j - i)];
        }
        ++total;
        i = j;
    }
    return total;
}

double ratio(double part, double whole) {
    return whole > 0 ? part / whole : 0.0;
}

void add_word_frequencies(SparseVector& result, const char32_t* prefix,
                          const std::vector<std::u32string>& words,
                          const std::unordered_map<std::u32string, std::size_t>& counts,
                          std::size_t total_words) {
    for (const auto& word : words) {
        const std::u32string lowered = to_lower(word);
        const auto found = counts.find(lowered);
        const double count = found == counts.end() ? 0.0 : static_cast<double>(found->second);
        result[std::u32string(prefix) + lowered] = ratio(count, static_cast<double>(total_words));
    }
}

}  // namespace

SparseVector style_features(const std::vector<std::u32string>& messages,
                            const StyleLexicon& lexicon) {
    PunctuationCounts punctuation;
    std::unordered_map<std::u32string, std::size_t> word_counts;
    std::size_t used_messages = 0;
    std::size_t messages_with_letters = 0;
    std::size_t capital_starts = 0;
    std::size_t end_dots = 0;
    std::size_t total_chars = 0;
    std::size_t total_words = 0;
    std::size_t total_letters = 0;
    std::size_t latin_letters = 0;
    std::size_t yo_count = 0;
    std::size_t ye_count = 0;
    std::size_t emoji_count = 0;

    for (const auto& raw : messages) {
        const std::u32string text = clean_message(raw, lexicon.ignored_tokens);
        if (text.empty()) {
            continue;
        }
        ++used_messages;
        total_chars += text.size();

        count_punctuation(text, punctuation);
        if (text.back() == U'.' && (text.size() == 1 || text[text.size() - 2] != U'.')) {
            ++end_dots;
        }

        bool first_letter_seen = false;
        for (const char32_t cp : text) {
            if (is_emoji(cp)) {
                ++emoji_count;
            }
            if (!is_letter(cp)) {
                continue;
            }
            ++total_letters;
            if (cp < 0x80) {
                ++latin_letters;
            }
            if (!first_letter_seen) {
                first_letter_seen = true;
                ++messages_with_letters;
                if (is_upper(cp)) {
                    ++capital_starts;
                }
            }
        }

        const std::u32string lowered = to_lower(text);
        for (const char32_t cp : lowered) {
            if (cp == 0x0451) {
                ++yo_count;
            } else if (cp == 0x0435) {
                ++ye_count;
            }
        }
        total_words += count_words(lowered, &word_counts);
    }

    const auto messages_n = static_cast<double>(used_messages);
    SparseVector result;
    result[U"p:paren1"] = ratio(punctuation.paren1, messages_n);
    result[U"p:paren2"] = ratio(punctuation.paren2, messages_n);
    result[U"p:paren3+"] = ratio(punctuation.paren3, messages_n);
    result[U"p:ellipsis"] = ratio(punctuation.ellipsis, messages_n);
    result[U"p:excl1"] = ratio(punctuation.excl1, messages_n);
    result[U"p:excl2+"] = ratio(punctuation.excl2, messages_n);
    result[U"p:quest1"] = ratio(punctuation.quest1, messages_n);
    result[U"p:quest2+"] = ratio(punctuation.quest2, messages_n);
    result[U"p:end_dot"] = ratio(static_cast<double>(end_dots), messages_n);
    result[U"f:capital_start"] =
        ratio(static_cast<double>(capital_starts), static_cast<double>(messages_with_letters));
    result[U"f:yo_ratio"] =
        ratio(static_cast<double>(yo_count), static_cast<double>(yo_count + ye_count));
    result[U"f:latin_share"] =
        ratio(static_cast<double>(latin_letters), static_cast<double>(total_letters));
    result[U"f:emoji"] = ratio(static_cast<double>(emoji_count), messages_n);
    result[U"r:avg_chars"] = ratio(static_cast<double>(total_chars), messages_n);
    result[U"r:avg_words"] = ratio(static_cast<double>(total_words), messages_n);

    add_word_frequencies(result, U"fw:", lexicon.function_words, word_counts, total_words);
    add_word_frequencies(result, U"fl:", lexicon.filler_words, word_counts, total_words);
    return result;
}

std::size_t word_count(const std::u32string& message,
                       const std::vector<std::u32string>& ignored_tokens) {
    return count_words(to_lower(clean_message(message, ignored_tokens)), nullptr);
}

}  // namespace chatstyle
