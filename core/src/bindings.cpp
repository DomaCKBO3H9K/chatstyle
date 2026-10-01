#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <chatstyle/compare.hpp>
#include <chatstyle/style_features.hpp>
#include <chatstyle/text.hpp>
#include <chatstyle/version.hpp>
#include <map>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

std::vector<std::u32string> to_u32(const std::vector<std::string>& texts) {
    std::vector<std::u32string> result;
    result.reserve(texts.size());
    for (const auto& text : texts) {
        result.push_back(chatstyle::utf8_to_u32(text));
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(_core, m) {
    m.doc() = "chatstyle core";
    m.def("version", &chatstyle::version, "Версия ядра");

    m.def("compare",
        [](const std::vector<std::string>& unknown, const py::dict& candidates) -> py::dict {
            std::vector<std::string> names;
            std::vector<std::vector<std::string>> texts;

            for (auto item : candidates) {
                names.push_back(item.first.cast<std::string>());
                texts.push_back(item.second.cast<std::vector<std::string>>());
            }

            auto scores = chatstyle::compare_to_unknown(unknown, texts);

            py::dict result;
            for (std::size_t i = 0; i < names.size(); ++i) {
                result[py::str(names[i])] = scores[i];
            }
            return result;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        "Compare an unknown author with each candidate; returns {name: similarity in [0, 1]}"
    );

    m.def("style_features",
        [](const std::vector<std::string>& messages,
           const std::vector<std::string>& function_words,
           const std::vector<std::string>& filler_words,
           const std::vector<std::string>& ignored_tokens) {
            const chatstyle::StyleLexicon lexicon{
                to_u32(function_words), to_u32(filler_words), to_u32(ignored_tokens)};
            const auto features = chatstyle::style_features(to_u32(messages), lexicon);
            std::map<std::string, double> result;
            for (const auto& [key, value] : features) {
                result[chatstyle::u32_to_utf8(key)] = value;
            }
            return result;
        },
        py::arg("messages"),
        py::arg("function_words"),
        py::arg("filler_words"),
        py::arg("ignored_tokens"),
        "Style features of an author (without n-grams); returns {name: value}"
    );
}
