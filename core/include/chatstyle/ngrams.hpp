#pragma once

#include <cstddef>
#include <string>
#include <unordered_map>
#include <vector>

namespace chatstyle {
    using SparseVector = std::unordered_map<std::u32string, double>;
    constexpr char32_t kStartMarker = 0x02;
    constexpr char32_t kEndMarker = 0x03;
    // Считает символьные n-граммы длины n_min..n_max по сообщениям; n-граммы не пересекают границу сообщения.
    // Читаемый вид n-граммы для объяснений: пробел -> «␣», маркеры начала и конца -> «^» и «$»
    std::u32string readable_ngram(const std::u32string& ngram);
    SparseVector count_char_ngrams(const std::vector<std::u32string>& messages, std::size_t n_min, std::size_t n_max);
}
