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

struct Candidates {
    std::vector<std::string> names;
    std::vector<std::vector<std::string>> texts;
};

// Обходит словарь кандидатов в порядке вставки, чтобы результат шёл в том же порядке
Candidates read_candidates(const py::dict& candidates) {
    Candidates result;
    for (auto item : candidates) {
        result.names.push_back(item.first.cast<std::string>());
        result.texts.push_back(item.second.cast<std::vector<std::string>>());
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(_core, m) {
    m.doc() = "chatstyle core";
    m.def("version", &chatstyle::version, "Версия ядра");

    m.def("compare",
        [](const std::vector<std::string>& unknown, const py::dict& candidates) -> py::dict {
            const auto input = read_candidates(candidates);

            const auto scores = chatstyle::compare_to_unknown(unknown, input.texts);

            py::dict result;
            for (std::size_t i = 0; i < input.names.size(); ++i) {
                result[py::str(input.names[i])] = scores[i];
            }
            return result;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        "Compare an unknown author with each candidate; returns {name: similarity in [0, 1]}"
    );

    m.def("compare_detailed",
        [](const std::vector<std::string>& unknown, const py::dict& candidates, std::size_t top_k) {
            const auto input = read_candidates(candidates);
            const auto reports = chatstyle::compare_with_explanations(unknown, input.texts, top_k);

            py::dict result;
            for (std::size_t i = 0; i < input.names.size(); ++i) {
                py::list features;
                for (const auto& item : reports[i].top_features) {
                    py::dict entry;
                    entry["feature"] = py::str(chatstyle::u32_to_utf8(item.feature));
                    entry["contribution"] = item.contribution;
                    entry["unknown_count"] = item.unknown_count;
                    entry["candidate_count"] = item.candidate_count;
                    features.append(entry);
                }
                py::dict report;
                report["similarity"] = reports[i].similarity;
                report["features"] = features;
                result[py::str(input.names[i])] = report;
            }
            return result;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        py::arg("top_k") = 20,
        "Compare an unknown author with each candidate; returns "
        "{name: {similarity, features: [{feature, contribution, unknown_count, candidate_count}]}}"
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
