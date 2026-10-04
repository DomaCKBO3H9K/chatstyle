// Тесты для Unicode-функций: is_letter, is_upper, is_latin, is_cyrillic, is_ideographic,
// to_lower, word_count, style_features (признак f:latin_share).
// Проверяют работу с кодпоинтами разных алфавитов и граничными случаями.

#include <catch2/catch_test_macros.hpp>
#include <catch2/catch_approx.hpp>
#include <chatstyle/text.hpp>
#include <chatstyle/style_features.hpp>
#include <chatstyle/similarity.hpp>
#include <string>
#include <vector>

using chatstyle::is_letter;
using chatstyle::is_upper;
using chatstyle::is_latin;
using chatstyle::is_cyrillic;
using chatstyle::is_ideographic;
using chatstyle::to_lower;
using chatstyle::word_count;
using chatstyle::style_features;
using chatstyle::StyleLexicon;
using chatstyle::SparseVector;

// Тест 1: is_letter для разных алфавитов и комбинирующих знаков.
TEST_CASE("unicode: letters of many scripts", "[unicode]") {
    // Истинные значения: буквы и комбинирующие знаки.
    REQUIRE(is_letter(U'a'));
    REQUIRE(is_letter(0x00E9));   // é
    REQUIRE(is_letter(0x00FC));   // ü
    REQUIRE(is_letter(0x00F1));   // ñ
    REQUIRE(is_letter(0x0142));   // ł
    REQUIRE(is_letter(0x03B1));   // α
    REQUIRE(is_letter(0x05D0));   // א
    REQUIRE(is_letter(0x0628));   // ب
    REQUIRE(is_letter(0x0915));   // क
    REQUIRE(is_letter(0x093E));   // а (знак матры)
    REQUIRE(is_letter(0x0301));   // комбинирующее ударение
    REQUIRE(is_letter(0x4E2D));   // 中
    REQUIRE(is_letter(0x3042));   // あ
    REQUIRE(is_letter(0xD55C));   // 한
    REQUIRE(is_letter(0x044F));   // я
    REQUIRE(is_letter(0x0451));   // ё

    // Ложные значения: не буквы.
    REQUIRE_FALSE(is_letter(U'1'));
    REQUIRE_FALSE(is_letter(U' '));
    REQUIRE_FALSE(is_letter(U'-'));
    REQUIRE_FALSE(is_letter(U'_'));
    REQUIRE_FALSE(is_letter(U'!'));
    REQUIRE_FALSE(is_letter(0x1F600));  // смайлик
    REQUIRE_FALSE(is_letter(0x00D7));   // знак умножения
}

// Тест 2: to_lower для различных алфавитов, включая регрессию по русскому.
TEST_CASE("unicode: lower-casing of many alphabets", "[unicode]") {
    // Латиница с диакритикой.
    {
        std::u32string original;
        original.push_back(0x00C9);  // É
        original.push_back(0x00DC);  // Ü
        original.push_back(0x00D1);  // Ñ
        original.push_back(0x0141);  // Ł
        std::u32string expected;
        expected.push_back(0x00E9);  // é
        expected.push_back(0x00FC);  // ü
        expected.push_back(0x00F1);  // ñ
        expected.push_back(0x0142);  // ł
        REQUIRE(to_lower(original) == expected);
    }

    // Греческий.
    {
        std::u32string original;
        original.push_back(0x03A3);  // Σ
        std::u32string expected;
        expected.push_back(0x03C3);  // σ
        REQUIRE(to_lower(original) == expected);
    }
    {
        std::u32string original;
        original.push_back(0x03A9);  // Ω
        std::u32string expected;
        expected.push_back(0x03C9);  // ω
        REQUIRE(to_lower(original) == expected);
    }

    // Армянский.
    {
        std::u32string original;
        original.push_back(0x0531);  // Ա
        std::u32string expected;
        expected.push_back(0x0561);  // ա
        REQUIRE(to_lower(original) == expected);
    }

    // Грузинская.
    {
        std::u32string original;
        original.push_back(0x1C90);  // Ა
        std::u32string expected;
        expected.push_back(0x10D0);  // ა
        REQUIRE(to_lower(original) == expected);
    }

    // Кириллица: Ѐ -> ѐ, Ґ -> ґ.
    {
        std::u32string original;
        original.push_back(0x0400);  // Ѐ
        std::u32string expected;
        expected.push_back(0x0450);  // ё
        REQUIRE(to_lower(original) == expected);
    }
    {
        std::u32string original;
        original.push_back(0x0490);  // Ґ
        std::u32string expected;
        expected.push_back(0x0491);  // ґ
        REQUIRE(to_lower(original) == expected);
    }

    // Сербский: Ǆ -> ǆ.
    {
        std::u32string original;
        original.push_back(0x01C4);  // Ǆ
        std::u32string expected;
        expected.push_back(0x01C6);  // ǆ
        REQUIRE(to_lower(original) == expected);
    }

    // İ (0x0130) остаётся без изменений.
    {
        std::u32string original;
        original.push_back(0x0130);
        REQUIRE(to_lower(original) == original);
    }

    // Не буквы и строчные не меняются.
    {
        std::u32string original = U"123! 😀";
        REQUIRE(to_lower(original) == original);
    }

    // Русская регрессия.
    {
        std::u32string original = U"Привет, Ёжик!";
        std::u32string expected = U"привет, ёжик!";
        REQUIRE(to_lower(original) == expected);
    }

    // Пустая строка.
    {
        std::u32string original;
        REQUIRE(to_lower(original).empty());
    }
}

// Тест 3: is_upper.
TEST_CASE("unicode: is_upper predicate", "[unicode]") {
    REQUIRE(is_upper(0x00C9));   // É
    REQUIRE(is_upper(0x03A3));   // Σ
    REQUIRE(is_upper(U'A'));
    REQUIRE(is_upper(0x0416));   // Ж

    REQUIRE_FALSE(is_upper(0x00E9));  // é
    REQUIRE_FALSE(is_upper(0x4E2D));  // 中
    REQUIRE_FALSE(is_upper(U'1'));
    REQUIRE_FALSE(is_upper(0x05D0));  // א
}

// Тест 4: предикаты по скриптам.
TEST_CASE("unicode: script predicates", "[unicode]") {
    // is_latin.
    REQUIRE(is_latin(U'a'));
    REQUIRE(is_latin(U'Z'));
    REQUIRE(is_latin(0x00E9));  // é
    REQUIRE(is_latin(0x0142));  // ł
    REQUIRE(is_latin(0x00DF));  // ß
    REQUIRE_FALSE(is_latin(0x044F));  // я
    REQUIRE_FALSE(is_latin(0x03B1));  // α
    REQUIRE_FALSE(is_latin(0x4E2D));  // 中
    REQUIRE_FALSE(is_latin(U'1'));

    // is_cyrillic.
    REQUIRE(is_cyrillic(0x044F));  // я
    REQUIRE(is_cyrillic(0x0491));  // ґ
    REQUIRE(is_cyrillic(0x0501));  // Ё (расширенный кириллический)
    REQUIRE_FALSE(is_cyrillic(U'a'));
    REQUIRE_FALSE(is_cyrillic(0x00E9));  // é

    // is_ideographic.
    REQUIRE(is_ideographic(0x4E2D));   // 中
    REQUIRE(is_ideographic(0x3042));   // あ
    REQUIRE(is_ideographic(0x30A2));   // ア
    REQUIRE(is_ideographic(0xFF71));   // ｱ (полуширина)
    REQUIRE(is_ideographic(0x20000));  // китайский иероглиф
    REQUIRE_FALSE(is_ideographic(0xD55C));  // 한 (хангыль)
    REQUIRE_FALSE(is_ideographic(U'a'));
    REQUIRE_FALSE(is_ideographic(0x3099));  // комбинирующий знак (не иероглиф)
    REQUIRE_FALSE(is_ideographic(0x044F));  // я
    REQUIRE_FALSE(is_ideographic(U' '));
}

// Тест 5: word_count.
TEST_CASE("unicode: word counting across scripts", "[unicode]") {
    std::vector<std::u32string> empty_ignored;
    REQUIRE(word_count(U"Été à Paris", empty_ignored) == 3);
    REQUIRE(word_count(U"我喜欢猫", empty_ignored) == 4);  // 4 иероглифа
    REQUIRE(word_count(U"ありがとうございます", empty_ignored) == 10);
    REQUIRE(word_count(U"hello мир 中文", empty_ignored) == 4);
    REQUIRE(word_count(U"", empty_ignored) == 0);
    REQUIRE(word_count(U"что-то", empty_ignored) == 1);  // дефис внутри слова
    REQUIRE(word_count(U"Привет мир", empty_ignored) == 2);
}

// Тест 6: style_features — признак f:latin_share.
TEST_CASE("unicode: features by script (latin_share)", "[unicode]") {
    StyleLexicon lexicon{};  // пустой словарь

    // Целиком латиница.
    {
        std::vector<std::u32string> messages = {U"café déjà vu"};
        SparseVector features = style_features(messages, lexicon);
        REQUIRE(features.at(U"f:latin_share") == Catch::Approx(1.0).margin(1e-9));
    }

    // Целиком кириллица.
    {
        std::vector<std::u32string> messages = {U"привет мир"};
        SparseVector features = style_features(messages, lexicon);
        REQUIRE(features.at(U"f:latin_share") == Catch::Approx(0.0).margin(1e-9));
    }

    // Смесь: строго между 0 и 1.
    {
        std::vector<std::u32string> messages = {U"привет hello"};
        SparseVector features = style_features(messages, lexicon);
        double share = features.at(U"f:latin_share");
        REQUIRE(share > 0.0);
        REQUIRE(share < 1.0);
    }

    // Греческий текст — латинская доля 0.
    {
        std::vector<std::u32string> messages = {U"Ελληνικά"};
        SparseVector features = style_features(messages, lexicon);
        REQUIRE(features.at(U"f:latin_share") == Catch::Approx(0.0).margin(1e-9));
    }
}
