#include "chatstyle/text.hpp"
#include <cstdint>
#include <cstddef>

namespace chatstyle {

namespace {
    constexpr char32_t kReplacement = 0xFFFD;

    char32_t lower_codepoint(char32_t cp) {
        if (cp >= 0x41 && cp <= 0x5A) {
            return cp + 0x20;
        }
        if (cp >= 0x0410 && cp <= 0x042F) {
            return cp + 0x20;
        }
        if (cp == 0x0401) {
            return 0x0451;
        }
        if (cp >= 0x0402 && cp <= 0x040F) {
            return cp + 0x50;
        }
        if (cp == 0x0490) {
            return 0x0491;
        }
        return cp;
    }
} // namespace

std::u32string utf8_to_u32(const std::string& text) {
    std::u32string result;
    const std::uint8_t* data = reinterpret_cast<const std::uint8_t*>(text.data());
    const std::size_t size = text.size();
    std::size_t i = 0;

    while (i < size) {
        std::uint8_t b = data[i];
        int need = 0;
        std::uint8_t lo = 0, hi = 0;

        if (b < 0x80) {
            result.push_back(static_cast<char32_t>(b));
            ++i;
            continue;
        }

        switch (b) {
            case 0xC2: case 0xC3: case 0xC4: case 0xC5: case 0xC6: case 0xC7:
            case 0xC8: case 0xC9: case 0xCA: case 0xCB: case 0xCC: case 0xCD:
            case 0xCE: case 0xCF: case 0xD0: case 0xD1: case 0xD2: case 0xD3:
            case 0xD4: case 0xD5: case 0xD6: case 0xD7: case 0xD8: case 0xD9:
            case 0xDA: case 0xDB: case 0xDC: case 0xDD: case 0xDE: case 0xDF:
                need = 1;
                lo = 0x80;
                hi = 0xBF;
                break;
            case 0xE0:
                need = 2;
                lo = 0xA0;
                hi = 0xBF;
                break;
            case 0xE1: case 0xE2: case 0xE3: case 0xE4: case 0xE5: case 0xE6:
            case 0xE7: case 0xE8: case 0xE9: case 0xEA: case 0xEB: case 0xEC:
                need = 2;
                lo = 0x80;
                hi = 0xBF;
                break;
            case 0xED:
                need = 2;
                lo = 0x80;
                hi = 0x9F;
                break;
            case 0xEE: case 0xEF:
                need = 2;
                lo = 0x80;
                hi = 0xBF;
                break;
            case 0xF0:
                need = 3;
                lo = 0x90;
                hi = 0xBF;
                break;
            case 0xF1: case 0xF2: case 0xF3:
                need = 3;
                lo = 0x80;
                hi = 0xBF;
                break;
            case 0xF4:
                need = 3;
                lo = 0x80;
                hi = 0x8F;
                break;
            default:
                result.push_back(kReplacement);
                ++i;
                continue;
        }

        char32_t cp;
        switch (need) {
            case 1: cp = b & 0x1F; break;
            case 2: cp = b & 0x0F; break;
            case 3: cp = b & 0x07; break;
            default: cp = 0; break;
        }
        std::size_t consumed = 1;
        bool valid = true;

        for (int k = 1; k <= need; ++k) {
            if (i + k >= size) {
                valid = false;
                break;
            }
            std::uint8_t cont = data[i + k];
            if (k == 1) {
                if (cont < lo || cont > hi) {
                    valid = false;
                    break;
                }
            } else {
                if (cont < 0x80 || cont > 0xBF) {
                    valid = false;
                    break;
                }
            }
            cp = (cp << 6) | (cont & 0x3F);
            ++consumed;
        }

        if (valid) {
            result.push_back(cp);
            i += consumed;
        } else {
            result.push_back(kReplacement);
            i += consumed;
        }
    }

    return result;
}

std::string u32_to_utf8(const std::u32string& text) {
    std::string result;

    for (char32_t cp : text) {
        if ((cp >= 0xD800 && cp <= 0xDFFF) || cp > 0x10FFFF) {
            result.push_back(static_cast<char>(0xEF));
            result.push_back(static_cast<char>(0xBF));
            result.push_back(static_cast<char>(0xBD));
            continue;
        }

        if (cp < 0x80) {
            result.push_back(static_cast<char>(cp));
        } else if (cp < 0x800) {
            result.push_back(static_cast<char>(0xC0 | (cp >> 6)));
            result.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else if (cp < 0x10000) {
            result.push_back(static_cast<char>(0xE0 | (cp >> 12)));
            result.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            result.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else {
            result.push_back(static_cast<char>(0xF0 | (cp >> 18)));
            result.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
            result.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            result.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        }
    }

    return result;
}

std::u32string to_lower(const std::u32string& text) {
    std::u32string result;
    result.reserve(text.size());
    for (char32_t cp : text) {
        result.push_back(lower_codepoint(cp));
    }
    return result;
}

} // namespace chatstyle
