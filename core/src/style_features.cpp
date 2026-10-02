#include "chatstyle/style_features.hpp"

#include <cstddef>
#include <functional>
#include <unordered_map>
#include <unordered_set>

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

struct Span {
    std::size_t begin;
    std::size_t end;  // [begin, end)
};

// Слово: серия букв, внутри допускается один дефис между буквами («что-то»)
std::vector<Span> word_spans(const std::u32string& text) {
    std::vector<Span> spans;
    const std::size_t size = text.size();
    std::size_t i = 0;
    while (i < size) {
        if (!is_letter(text[i])) {
            ++i;
            continue;
        }
        std::size_t j = i + 1;
        while (j < size) {
            if (is_letter(text[j])) {
                ++j;
            } else if (text[j] == U'-' && j + 1 < size && is_letter(text[j + 1])) {
                j += 2;
            } else {
                break;
            }
        }
        spans.push_back({i, j});
        i = j;
    }
    return spans;
}

std::size_t count_words(const std::u32string& lowered,
                        std::unordered_map<std::u32string, std::size_t>* counts) {
    const auto spans = word_spans(lowered);
    if (counts != nullptr) {
        for (const auto& span : spans) {
            ++(*counts)[lowered.substr(span.begin, span.end - span.begin)];
        }
    }
    return spans.size();
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

// --- дополнительные группы признаков: привычки пунктуации, орфографии, слов и предложений ---

struct Habits {
    // пунктуация
    double commas = 0;
    double conj_total = 0;
    double conj_with_comma = 0;
    double comma_no_space = 0;
    double marks = 0;
    double marks_space_before = 0;
    double dashes = 0;
    double guillemets = 0;
    double quotes_all = 0;
    double end_none = 0;
    // орфография
    double caps_words = 0;
    double after_dot_total = 0;
    double after_dot_upper = 0;
    double repeat_runs = 0;
    double tsya = 0;
    double tsya_soft = 0;
    double mixed_script = 0;
    double double_spaces = 0;
    // слова
    double word_letters = 0;
    double long_words = 0;
    double short_words = 0;
    std::vector<std::size_t> tokens;  // хэши слов в порядке следования, для MATTR
    // предложения
    double sentences = 0;
    double sentence_words = 0;
    double short_sentences = 0;
    double long_sentences = 0;
    double multi_messages = 0;
};

constexpr std::size_t kMattrWindow = 50;
constexpr std::size_t kLongWordLetters = 9;
constexpr std::size_t kShortWordLetters = 2;
constexpr std::size_t kShortSentenceWords = 3;
constexpr std::size_t kLongSentenceWords = 15;

bool is_digit(char32_t cp) {
    return cp >= U'0' && cp <= U'9';
}

bool is_cyrillic(char32_t cp) {
    return cp >= 0x0400 && cp <= 0x04FF;
}

bool is_sentence_end(char32_t cp) {
    return cp == U'.' || cp == U'!' || cp == U'?' || cp == 0x2026 || cp == U'\n';
}

// Буквы слова без дефисов
std::size_t letter_count(const std::u32string& text, const Span& span) {
    std::size_t letters = 0;
    for (std::size_t k = span.begin; k < span.end; ++k) {
        if (is_letter(text[k])) {
            ++letters;
        }
    }
    return letters;
}

bool ends_with(const std::u32string& text, const Span& span, const std::u32string& suffix) {
    const std::size_t length = span.end - span.begin;
    return length >= suffix.size() &&
           text.compare(span.end - suffix.size(), suffix.size(), suffix) == 0;
}

void count_punctuation_habits(const std::u32string& text, const std::vector<Span>& spans,
                              const std::unordered_set<std::u32string>& conjunctions,
                              const std::u32string& lowered, Habits& h) {
    const std::size_t size = text.size();
    for (std::size_t i = 0; i < size; ++i) {
        const char32_t ch = text[i];
        if (ch == U',') {
            h.commas += 1;
            if (i + 1 < size && is_letter(text[i + 1])) {
                h.comma_no_space += 1;
            }
        }
        if (ch == U',' || ch == U'.' || ch == U'!' || ch == U'?') {
            h.marks += 1;
            if (i > 0 && is_space(text[i - 1])) {
                h.marks_space_before += 1;
            }
        }
        if (ch == 0x2013 || ch == 0x2014) {
            h.dashes += 1;
        } else if (ch == U'-' && i > 0 && i + 1 < size && is_space(text[i - 1]) &&
                   is_space(text[i + 1])) {
            h.dashes += 1;
        }
        if (ch == 0xAB || ch == 0xBB) {
            h.guillemets += 1;
            h.quotes_all += 1;
        } else if (ch == U'"' || ch == 0x201C || ch == 0x201D || ch == 0x201E) {
            h.quotes_all += 1;
        }
    }
    if (is_letter(text.back()) || is_digit(text.back())) {
        h.end_none += 1;
    }
    if (conjunctions.empty()) {
        return;
    }
    for (const auto& span : spans) {
        if (conjunctions.count(lowered.substr(span.begin, span.end - span.begin)) == 0) {
            continue;
        }
        std::size_t p = span.begin;
        while (p > 0 && is_space(text[p - 1])) {
            --p;
        }
        if (p == 0 || is_sentence_end(text[p - 1])) {
            continue;  // начало сообщения или предложения: запятой перед союзом не бывает
        }
        h.conj_total += 1;
        if (text[p - 1] == U',') {
            h.conj_with_comma += 1;
        }
    }
}

void count_orthography_habits(const std::u32string& text, const std::vector<Span>& spans,
                              const std::u32string& lowered, Habits& h) {
    const std::size_t size = text.size();
    for (const auto& span : spans) {
        std::size_t letters = 0;
        bool all_upper = true;
        bool cyrillic = false;
        bool latin = false;
        for (std::size_t k = span.begin; k < span.end; ++k) {
            if (!is_letter(text[k])) {
                continue;
            }
            ++letters;
            if (!is_upper(text[k])) {
                all_upper = false;
            }
            (is_cyrillic(text[k]) ? cyrillic : latin) = true;
        }
        if (letters >= 2 && all_upper) {
            h.caps_words += 1;
        }
        if (cyrillic && latin) {
            h.mixed_script += 1;
        }
        if (ends_with(lowered, span, U"ться")) {
            h.tsya_soft += 1;
        } else if (ends_with(lowered, span, U"тся")) {
            h.tsya += 1;
        }
    }
    std::size_t i = 0;
    while (i < size) {
        if (is_letter(lowered[i])) {
            std::size_t j = i + 1;
            while (j < size && lowered[j] == lowered[i]) {
                ++j;
            }
            if (j - i >= 3) {
                h.repeat_runs += 1;
            }
            i = j;
        } else if (text[i] == U' ') {
            std::size_t j = i + 1;
            while (j < size && text[j] == U' ') {
                ++j;
            }
            if (j - i >= 2) {
                h.double_spaces += 1;
            }
            i = j;
        } else {
            ++i;
        }
    }
    for (std::size_t k = 0; k < size; ++k) {
        const char32_t ch = text[k];
        if ((ch == U'.' || ch == U'!' || ch == U'?') && k + 1 < size && is_space(text[k + 1])) {
            std::size_t j = k + 1;
            while (j < size && is_space(text[j])) {
                ++j;
            }
            if (j < size && is_letter(text[j])) {
                h.after_dot_total += 1;
                if (is_upper(text[j])) {
                    h.after_dot_upper += 1;
                }
            }
        }
    }
}

void count_word_habits(const std::u32string& text, const std::vector<Span>& spans,
                       const std::u32string& lowered, Habits& h) {
    for (const auto& span : spans) {
        const std::size_t letters = letter_count(text, span);
        h.word_letters += static_cast<double>(letters);
        if (letters >= kLongWordLetters) {
            h.long_words += 1;
        }
        if (letters <= kShortWordLetters) {
            h.short_words += 1;
        }
        h.tokens.push_back(
            std::hash<std::u32string>{}(lowered.substr(span.begin, span.end - span.begin)));
    }
}

void count_sentence_habits(const std::u32string& text, const std::vector<Span>& spans,
                           Habits& h) {
    std::size_t in_sentence = 0;
    std::size_t sentences = 0;
    auto close = [&]() {
        if (in_sentence == 0) {
            return;
        }
        ++sentences;
        h.sentences += 1;
        h.sentence_words += static_cast<double>(in_sentence);
        if (in_sentence <= kShortSentenceWords) {
            h.short_sentences += 1;
        }
        if (in_sentence >= kLongSentenceWords) {
            h.long_sentences += 1;
        }
        in_sentence = 0;
    };
    std::size_t previous_end = 0;
    for (const auto& span : spans) {
        for (std::size_t k = previous_end; k < span.begin; ++k) {
            if (is_sentence_end(text[k])) {
                close();
                break;
            }
        }
        ++in_sentence;
        previous_end = span.end;
    }
    close();
    if (sentences >= 2) {
        h.multi_messages += 1;
    }
}

// Скользящее разнообразие слов: среднее число различных слов в окне из kMattrWindow слов.
// Для текста короче окна — доля различных слов во всём тексте.
double mattr(const std::vector<std::size_t>& tokens) {
    if (tokens.empty()) {
        return 0.0;
    }
    std::unordered_map<std::size_t, std::size_t> counts;
    std::size_t types = 0;
    double sum = 0.0;
    std::size_t windows = 0;
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        if (counts[tokens[i]]++ == 0) {
            ++types;
        }
        if (i >= kMattrWindow) {
            const auto found = counts.find(tokens[i - kMattrWindow]);
            if (--found->second == 0) {
                --types;
                counts.erase(found);
            }
        }
        if (i + 1 >= kMattrWindow) {
            sum += static_cast<double>(types) / static_cast<double>(kMattrWindow);
            ++windows;
        }
    }
    if (windows == 0) {
        return static_cast<double>(types) / static_cast<double>(tokens.size());
    }
    return sum / static_cast<double>(windows);
}

std::unordered_set<std::u32string> lowered_set(const std::vector<std::u32string>& words) {
    std::unordered_set<std::u32string> result;
    for (const auto& word : words) {
        result.insert(to_lower(word));
    }
    return result;
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
    Habits habits;
    const auto conjunctions = lowered_set(lexicon.conjunctions);

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

        if (lexicon.groups != 0) {
            const auto spans = word_spans(lowered);
            if ((lexicon.groups & kGroupPunctuation) != 0) {
                count_punctuation_habits(text, spans, conjunctions, lowered, habits);
            }
            if ((lexicon.groups & kGroupOrthography) != 0) {
                count_orthography_habits(text, spans, lowered, habits);
            }
            if ((lexicon.groups & kGroupWords) != 0) {
                count_word_habits(text, spans, lowered, habits);
            }
            if ((lexicon.groups & kGroupSentences) != 0) {
                count_sentence_habits(text, spans, habits);
            }
        }
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

    const double words_n = static_cast<double>(total_words);
    if ((lexicon.groups & kGroupPunctuation) != 0) {
        result[U"p:comma_per_word"] = ratio(habits.commas, words_n);
        result[U"p:comma_before_conj"] = ratio(habits.conj_with_comma, habits.conj_total);
        result[U"p:no_space_after_comma"] = ratio(habits.comma_no_space, habits.commas);
        result[U"p:space_before_punct"] = ratio(habits.marks_space_before, habits.marks);
        result[U"p:dash"] = ratio(habits.dashes, messages_n);
        result[U"p:guillemets"] = ratio(habits.guillemets, habits.quotes_all);
        result[U"p:end_none"] = ratio(habits.end_none, messages_n);
    }
    if ((lexicon.groups & kGroupOrthography) != 0) {
        double nonstandard = 0.0;
        for (const auto& word : lowered_set(lexicon.nonstandard_words)) {
            const auto found = word_counts.find(word);
            if (found != word_counts.end()) {
                nonstandard += static_cast<double>(found->second);
            }
        }
        result[U"f:caps_words"] = ratio(habits.caps_words, messages_n);
        result[U"f:capital_after_dot"] = ratio(habits.after_dot_upper, habits.after_dot_total);
        result[U"o:repeat_letters"] = ratio(habits.repeat_runs, messages_n);
        result[U"o:tsya_share"] = ratio(habits.tsya, habits.tsya + habits.tsya_soft);
        result[U"o:mixed_script"] = ratio(habits.mixed_script, words_n);
        result[U"o:double_space"] = ratio(habits.double_spaces, messages_n);
        result[U"o:nonstandard"] = ratio(nonstandard, words_n);
        add_word_frequencies(result, U"ms:", lexicon.nonstandard_words, word_counts, total_words);
    }
    if ((lexicon.groups & kGroupWords) != 0) {
        result[U"w:mattr"] = mattr(habits.tokens);
        result[U"w:avg_word_len"] = ratio(habits.word_letters, words_n);
        result[U"w:long_words"] = ratio(habits.long_words, words_n);
        result[U"w:short_words"] = ratio(habits.short_words, words_n);
    }
    if ((lexicon.groups & kGroupSentences) != 0) {
        result[U"s:avg_sentence_words"] = ratio(habits.sentence_words, habits.sentences);
        result[U"s:per_message"] = ratio(habits.sentences, messages_n);
        result[U"s:short_share"] = ratio(habits.short_sentences, habits.sentences);
        result[U"s:long_share"] = ratio(habits.long_sentences, habits.sentences);
        result[U"s:multi_share"] = ratio(habits.multi_messages, messages_n);
    }

    add_word_frequencies(result, U"fw:", lexicon.function_words, word_counts, total_words);
    add_word_frequencies(result, U"fl:", lexicon.filler_words, word_counts, total_words);
    return result;
}

std::size_t word_count(const std::u32string& message,
                       const std::vector<std::u32string>& ignored_tokens) {
    return count_words(to_lower(clean_message(message, ignored_tokens)), nullptr);
}

}  // namespace chatstyle
