#include "chatstyle/ngrams.hpp"
#include <stdexcept>

namespace chatstyle {
    SparseVector count_char_ngrams(const std::vector<std::u32string>& messages, std::size_t n_min, std::size_t n_max) {
        if (n_min == 0 || n_min > n_max) {
            throw std::invalid_argument("n_min must be > 0 and <= n_max");
        }

        SparseVector result;

        for (const auto& message : messages) {
            if (message.empty()) {
                continue;
            }

            std::u32string padded(1, kStartMarker);
            padded += message;
            padded += kEndMarker;

            for (std::size_t n = n_min; n <= n_max; ++n) {
                if (padded.size() < n) {
                    continue;
                }

                for (std::size_t i = 0; i <= padded.size() - n; ++i) {
                    std::u32string window = padded.substr(i, n);

                    if (n == 1 && (window[0] == kStartMarker || window[0] == kEndMarker)) {
                        continue;
                    }

                    result[window] += 1.0;
                }
            }
        }

        return result;
    }

    std::u32string readable_ngram(const std::u32string& ngram) {
        std::u32string result;
        result.reserve(ngram.size());
        for (const char32_t cp : ngram) {
            if (cp == kStartMarker) {
                result.push_back(U'^');
            } else if (cp == kEndMarker) {
                result.push_back(U'$');
            } else if (cp == U' ') {
                result.push_back(0x2423);  // «␣»
            } else {
                result.push_back(cp);
            }
        }
        return result;
    }
}
