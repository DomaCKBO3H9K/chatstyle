#include <catch2/catch_test_macros.hpp>
#include <chatstyle/text.hpp>
#include <string>

using chatstyle::utf8_to_u32;
using chatstyle::u32_to_utf8;
using chatstyle::to_lower;

TEST_CASE("text: round-trip for ASCII and Cyrillic", "[text]") {
    std::string original = "Привет";
    std::u32string u32 = utf8_to_u32(original);
    REQUIRE(u32.size() == 6);
    REQUIRE(u32_to_utf8(u32) == original);
}

TEST_CASE("text: emoji U+1F600", "[text]") {
    const char emoji_bytes[] = "\xF0\x9F\x98\x80";
    std::string original(emoji_bytes, 4);
    std::u32string u32 = utf8_to_u32(original);
    REQUIRE(u32.size() == 1);
    REQUIRE(u32[0] == 0x1F600);
    REQUIRE(u32_to_utf8(u32) == original);
}

TEST_CASE("text: empty string round-trip", "[text]") {
    std::string empty;
    std::u32string u32 = utf8_to_u32(empty);
    REQUIRE(u32.empty());
    REQUIRE(u32_to_utf8(u32) == empty);
}

TEST_CASE("text: invalid UTF-8 sequences", "[text]") {
    const char32_t REPL = 0xFFFD;

    // Test 1: single byte 0xFF
    {
        std::string invalid("\xFF", 1);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 1);
        REQUIRE(u32[0] == REPL);
    }

    // Test 2: 61 80 62 -> 'a', REPL, 'b'
    {
        std::string invalid("\x61\x80\x62", 3);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 3);
        REQUIRE(u32[0] == U'a');
        REQUIRE(u32[1] == REPL);
        REQUIRE(u32[2] == U'b');
    }

    // Test 3: D0 at end
    {
        std::string invalid("\xD0", 1);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 1);
        REQUIRE(u32[0] == REPL);
    }

    // Test 4: D0 61 -> REPL, 'a'
    {
        std::string invalid("\xD0\x61", 2);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 2);
        REQUIRE(u32[0] == REPL);
        REQUIRE(u32[1] == U'a');
    }

    // Test 5: E2 82 78 -> REPL, 'x'
    {
        std::string invalid("\xE2\x82\x78", 3);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 2);
        REQUIRE(u32[0] == REPL);
        REQUIRE(u32[1] == U'x');
    }

    // Test 6: F0 9F 98 -> REPL
    {
        std::string invalid("\xF0\x9F\x98", 3);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 1);
        REQUIRE(u32[0] == REPL);
    }

    // Test 7: C0 AF -> REPL, REPL
    {
        std::string invalid("\xC0\xAF", 2);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 2);
        REQUIRE(u32[0] == REPL);
        REQUIRE(u32[1] == REPL);
    }

    // Test 8: ED A0 80 -> REPL, REPL, REPL
    {
        std::string invalid("\xED\xA0\x80", 3);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 3);
        REQUIRE(u32[0] == REPL);
        REQUIRE(u32[1] == REPL);
        REQUIRE(u32[2] == REPL);
    }

    // Test 9: F4 90 80 80 -> REPL, REPL, REPL, REPL
    {
        std::string invalid("\xF4\x90\x80\x80", 4);
        std::u32string u32 = utf8_to_u32(invalid);
        REQUIRE(u32.size() == 4);
        REQUIRE(u32[0] == REPL);
        REQUIRE(u32[1] == REPL);
        REQUIRE(u32[2] == REPL);
        REQUIRE(u32[3] == REPL);
    }
}

TEST_CASE("text: u32_to_utf8 for invalid code points", "[text]") {
    std::u32string invalid1;
    invalid1.push_back(0xD800); // surrogate
    std::string utf8_1 = u32_to_utf8(invalid1);
    // Expected: EF BF BD (3 bytes for U+FFFD)
    REQUIRE(utf8_1 == "\xEF\xBF\xBD");

    std::u32string invalid2;
    invalid2.push_back(0x110000); // out of range
    std::string utf8_2 = u32_to_utf8(invalid2);
    REQUIRE(utf8_2 == "\xEF\xBF\xBD");
}

TEST_CASE("text: to_lower function", "[text]") {
    // Test 1: ЁЖИК -> ёжик
    {
        std::u32string original = U"ЁЖИК";
        std::u32string expected = U"ёжик";
        REQUIRE(to_lower(original) == expected);
    }

    // Test 2: Привет Мир -> привет мир
    {
        std::u32string original = U"Привет Мир";
        std::u32string expected = U"привет мир";
        REQUIRE(to_lower(original) == expected);
    }

    // Test 3: Hello Мир -> hello мир
    {
        std::u32string original = U"Hello Мир";
        std::u32string expected = U"hello мир";
        REQUIRE(to_lower(original) == expected);
    }

    // Test 4: ёлка remains ёлка
    {
        std::u32string original = U"ёлка";
        REQUIRE(to_lower(original) == original);
    }

    // Test 5: ґ (0x0490) -> ґ (0x0491)
    {
        std::u32string original;
        original.push_back(0x0490);
        std::u32string expected;
        expected.push_back(0x0491);
        REQUIRE(to_lower(original) == expected);
    }

    // Test 6: ў (0x040E) -> ў (0x045E)
    {
        std::u32string original;
        original.push_back(0x040E);
        std::u32string expected;
        expected.push_back(0x045E);
        REQUIRE(to_lower(original) == expected);
    }

    // Test 7: digits, punctuation, emoji unchanged
    {
        std::u32string original = U"123!@# 😀";
        REQUIRE(to_lower(original) == original);
    }

    // Test 8: empty string
    {
        std::u32string original;
        REQUIRE(to_lower(original).empty());
    }
}
