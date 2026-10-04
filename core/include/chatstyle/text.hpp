#pragma once
#include <string>

namespace chatstyle {
    // Преобразует UTF-8 в UTF-32 с заменой некорректных последовательностей на U+FFFD
    std::u32string utf8_to_u32(const std::string& text);
    // Преобразует UTF-32 в UTF-8 с заменой недопустимых кодпоинтов на U+FFFD
    std::string u32_to_utf8(const std::u32string& text);
    // Приводит к нижнему регистру по простым правилам Unicode (по кодпоинтам)
    std::u32string to_lower(const std::u32string& text);
    // Буква или комбинирующий знак любого алфавита Unicode
    bool is_letter(char32_t cp);
    // Заглавная буква, у которой есть простой нижний регистр
    bool is_upper(char32_t cp);
    // Латинский алфавит (ASCII, дополнительные диапазоны)
    bool is_latin(char32_t cp);
    // Кириллический алфавит
    bool is_cyrillic(char32_t cp);
    // Иероглиф или кана: в таких письменностях нет пробелов, поэтому каждый знак считается словом
    bool is_ideographic(char32_t cp);
}
