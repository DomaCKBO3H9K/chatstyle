#include "chatstyle/text.hpp"
#include <cstdint>
#include <cstddef>
#include <algorithm>

namespace chatstyle {

namespace {
    constexpr char32_t kReplacement = 0xFFFD;

    struct CodepointRange {
        char32_t first;
        char32_t last;
    };

    struct LowerRange {
        char32_t first;
        char32_t last;
        std::int32_t delta;
        std::uint32_t step;
    };

    constexpr CodepointRange kLetterRanges[] = {
        #include "unicode_letters.inc"
    };

    constexpr LowerRange kLowerRanges[] = {
        #include "unicode_lower.inc"
    };

    char32_t lower_codepoint(char32_t cp) {
        auto it = std::upper_bound(std::begin(kLowerRanges), std::end(kLowerRanges), cp,
            [](char32_t val, const LowerRange& r) { return val < r.first; });
        if (it != std::begin(kLowerRanges)) {
            --it;
            if (cp <= it->last && (cp - it->first) % it->step == 0) {
                return cp + it->delta;
            }
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

bool is_letter(char32_t cp) {
    auto it = std::upper_bound(std::begin(kLetterRanges), std::end(kLetterRanges), cp,
        [](char32_t val, const CodepointRange& r) { return val < r.first; });
    if (it != std::begin(kLetterRanges)) {
        --it;
        if (cp >= it->first && cp <= it->last) {
            return true;
        }
    }
    return false;
}

bool is_upper(char32_t cp) {
    return lower_codepoint(cp) != cp;
}

bool is_latin(char32_t cp) {
    return (cp >= 0x41 && cp <= 0x5A) || (cp >= 0x61 && cp <= 0x7A) ||
           cp == 0xAA || cp == 0xBA ||
           (cp >= 0xC0 && cp <= 0xD6) || (cp >= 0xD8 && cp <= 0xF6) ||
           (cp >= 0xF8 && cp <= 0x2AF) ||
           (cp >= 0x1E00 && cp <= 0x1EFF) ||
           (cp >= 0x2C60 && cp <= 0x2C7F) ||
           (cp >= 0xA720 && cp <= 0xA7FF) ||
           (cp >= 0xFB00 && cp <= 0xFB06) ||
           (cp >= 0xFF21 && cp <= 0xFF3A) ||
           (cp >= 0xFF41 && cp <= 0xFF5A);
}

bool is_cyrillic(char32_t cp) {
    return (cp >= 0x0400 && cp <= 0x052F) ||
           (cp >= 0x1C80 && cp <= 0x1C8F) ||
           (cp >= 0x2DE0 && cp <= 0x2DFF) ||
           (cp >= 0xA640 && cp <= 0xA69F);
}

bool is_ideographic(char32_t cp) {
    if (!is_letter(cp)) return false;
    if (cp == 0x3099 || cp == 0x309A) return false;
    return (cp >= 0x3040 && cp <= 0x30FF) ||
           (cp >= 0x31F0 && cp <= 0x31FF) ||
           (cp >= 0x3400 && cp <= 0x4DBF) ||
           (cp >= 0x4E00 && cp <= 0x9FFF) ||
           (cp >= 0xF900 && cp <= 0xFAFF) ||
           (cp >= 0xFF66 && cp <= 0xFF9F) ||
           (cp >= 0x20000 && cp <= 0x2FA1F) ||
           (cp >= 0x30000 && cp <= 0x323AF);
}

} // namespace chatstyle
