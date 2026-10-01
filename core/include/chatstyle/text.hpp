#pragma once
#include <string>

namespace chatstyle {
    // Преобразует UTF-8 в UTF-32 с заменой некорректных последовательностей на U+FFFD
    std::u32string utf8_to_u32(const std::string& text);
    // Преобразует UTF-32 в UTF-8 с заменой недопустимых кодпоинтов на U+FFFD
    std::string u32_to_utf8(const std::u32string& text);
    // Приводит кириллицу и латиницу к нижнему регистру по кодпоинтам
    std::u32string to_lower(const std::u32string& text);
}
