#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <chatstyle/charlm.hpp>
#include <chatstyle/compare.hpp>
#include <chatstyle/delta.hpp>
#include <chatstyle/impostors.hpp>
#include <chatstyle/rhythm.hpp>
#include <chatstyle/style_features.hpp>
#include <chatstyle/text.hpp>
#include <chatstyle/version.hpp>
#include <cstdint>
#include <map>
#include <stdexcept>
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

            std::vector<double> scores;
            {
                py::gil_scoped_release release;  // расчёт не держит GIL: окно и потоки не замирают
                scores = chatstyle::compare_to_unknown(unknown, input.texts);
            }

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
            std::vector<chatstyle::CandidateReport> reports;
            {
                py::gil_scoped_release release;
                reports = chatstyle::compare_with_explanations(unknown, input.texts, top_k);
            }

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

    m.def("burrows_delta",
        [](const std::vector<std::string>& unknown,
           const py::dict& candidates,
           const std::vector<std::string>& function_words,
           const std::vector<std::string>& filler_words,
           const std::vector<std::string>& ignored_tokens,
           std::size_t chunk_words,
           std::size_t min_chunks,
           std::size_t top_words,
           std::size_t top_k,
           const std::vector<std::string>& nonstandard_words,
           const std::vector<std::string>& conjunctions,
           unsigned groups) {
            const auto input = read_candidates(candidates);
            std::vector<std::vector<std::u32string>> candidate_texts;
            for (const auto& texts : input.texts) {
                candidate_texts.push_back(to_u32(texts));
            }
            const chatstyle::StyleLexicon lexicon{
                to_u32(function_words), to_u32(filler_words), to_u32(ignored_tokens),
                to_u32(nonstandard_words), to_u32(conjunctions), groups};
            chatstyle::DeltaOptions options;
            options.chunk_words = chunk_words;
            options.min_chunks = min_chunks;
            options.top_words = top_words;
            const auto unknown_text = to_u32(unknown);
            std::vector<chatstyle::DeltaResult> results;
            {
                py::gil_scoped_release release;
                results = chatstyle::burrows_delta(unknown_text, candidate_texts, lexicon, options);
            }

            py::dict output;
            for (std::size_t i = 0; i < input.names.size(); ++i) {
                py::list differences;
                for (std::size_t k = 0; k < results[i].differences.size() && k < top_k; ++k) {
                    const auto& item = results[i].differences[k];
                    py::dict entry;
                    entry["feature"] = py::str(chatstyle::u32_to_utf8(item.feature));
                    entry["unknown_value"] = item.unknown_value;
                    entry["candidate_value"] = item.candidate_value;
                    entry["sigma"] = item.sigma;
                    entry["z_difference"] = item.z_difference;
                    differences.append(entry);
                }
                py::dict report;
                report["available"] = results[i].available;
                report["delta"] = results[i].delta;
                report["features_used"] = results[i].features_used;
                report["cosine_available"] = results[i].cosine_available;
                report["cosine"] = results[i].cosine;
                report["differences"] = differences;
                output[py::str(input.names[i])] = report;
            }
            return output;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        py::arg("function_words"),
        py::arg("filler_words"),
        py::arg("ignored_tokens"),
        py::arg("chunk_words") = 200,
        py::arg("min_chunks") = 6,
        py::arg("top_words") = 100,
        py::arg("top_k") = 20,
        py::arg("nonstandard_words") = std::vector<std::string>{},
        py::arg("conjunctions") = std::vector<std::string>{},
        py::arg("groups") = chatstyle::kGroupAll,
        "Burrows Delta of an unknown author against each candidate; returns "
        "{name: {available, delta, features_used, differences: [...]}}"
    );

    m.def("charlm_compare",
        [](const std::vector<std::string>& unknown,
           const py::dict& candidates,
           std::size_t order,
           bool balance) {
            const auto input = read_candidates(candidates);
            std::vector<std::vector<std::u32string>> candidate_texts;
            for (const auto& texts : input.texts) {
                candidate_texts.push_back(to_u32(texts));
            }
            chatstyle::CharLmOptions options;
            options.order = order;
            options.balance = balance;
            const auto unknown_text = to_u32(unknown);
            std::vector<chatstyle::CharLmResult> results;
            {
                py::gil_scoped_release release;
                try {
                    results = chatstyle::charlm_compare(unknown_text, candidate_texts, options);
                } catch (const std::invalid_argument&) {
                    results.clear();
                }
            }
            if (results.empty() && !input.names.empty()) {
                throw py::value_error("order must be positive");
            }

            py::dict output;
            for (std::size_t i = 0; i < input.names.size(); ++i) {
                py::dict report;
                report["available"] = results[i].available;
                report["bits_candidate"] = results[i].bits_candidate;
                report["bits_rest"] = results[i].bits_rest;
                report["llr"] = results[i].llr;
                report["chars_scored"] = results[i].chars_scored;
                output[py::str(input.names[i])] = report;
            }
            return output;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        py::arg("order") = 4,
        py::arg("balance") = true,
        "Character language model: {name: {available, bits_candidate, bits_rest, llr, chars_scored}}"
    );

    m.def("rhythm_profile",
        [](const std::vector<std::int64_t>& times) {
            chatstyle::RhythmProfile profile;
            {
                py::gil_scoped_release release;
                profile = chatstyle::rhythm_profile(times);
            }
            py::dict features;
            for (const auto& item : profile.features) {
                features[py::str(chatstyle::u32_to_utf8(item.first))] = item.second;
            }
            py::dict report;
            report["available"] = profile.available;
            report["messages"] = profile.messages;
            report["features"] = features;
            return report;
        },
        py::arg("times"),
        "Rhythm profile from local message times (seconds): {available, messages, features}"
    );

    m.def("rhythm_compare",
        [](const std::vector<std::int64_t>& unknown, const py::dict& candidates) {
            std::vector<std::string> names;
            std::vector<std::vector<std::int64_t>> times;
            for (auto item : candidates) {
                names.push_back(item.first.cast<std::string>());
                times.push_back(item.second.cast<std::vector<std::int64_t>>());
            }
            std::vector<chatstyle::RhythmProfile> profiles;
            chatstyle::RhythmProfile known;
            {
                py::gil_scoped_release release;
                known = chatstyle::rhythm_profile(unknown);
                for (const auto& list : times) {
                    profiles.push_back(chatstyle::rhythm_profile(list));
                }
            }
            py::dict output;
            for (std::size_t i = 0; i < names.size(); ++i) {
                py::dict report;
                const bool available = known.available && profiles[i].available;
                report["available"] = available;
                report["similarity"] = available ? chatstyle::rhythm_similarity(known, profiles[i]) : 0.0;
                output[py::str(names[i])] = report;
            }
            return output;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        "Rhythm similarity of an unknown author with each candidate: {name: {available, similarity}}"
    );

    m.def("general_impostors",
        [](const std::vector<std::string>& unknown,
           const py::dict& candidates,
           const std::vector<std::vector<std::string>>& impostors,
           const std::vector<std::string>& ignored_tokens,
           std::size_t iterations,
           double feature_fraction,
           std::size_t max_impostors,
           std::size_t min_impostors,
           std::size_t min_chunks,
           std::size_t chunk_words,
           unsigned seed) {
            const auto input = read_candidates(candidates);
            std::vector<std::vector<std::u32string>> candidate_texts;
            for (const auto& texts : input.texts) {
                candidate_texts.push_back(to_u32(texts));
            }
            std::vector<std::vector<std::u32string>> impostor_texts;
            for (const auto& texts : impostors) {
                impostor_texts.push_back(to_u32(texts));
            }
            chatstyle::ImpostorsOptions options;
            options.iterations = iterations;
            options.feature_fraction = feature_fraction;
            options.max_impostors = max_impostors;
            options.min_impostors = min_impostors;
            options.min_chunks = min_chunks;
            options.chunk_words = chunk_words;
            options.seed = seed;
            const auto unknown_text = to_u32(unknown);
            const auto ignored = to_u32(ignored_tokens);
            std::vector<chatstyle::ImpostorsResult> results;
            {
                py::gil_scoped_release release;
                results = chatstyle::general_impostors(
                    unknown_text, candidate_texts, impostor_texts, ignored, options);
            }

            py::dict output;
            for (std::size_t i = 0; i < input.names.size(); ++i) {
                py::dict report;
                report["available"] = results[i].available;
                report["score"] = results[i].score;
                report["impostors"] = results[i].impostors;
                report["iterations"] = results[i].iterations;
                output[py::str(input.names[i])] = report;
            }
            return output;
        },
        py::arg("unknown"),
        py::arg("candidates"),
        py::arg("impostors"),
        py::arg("ignored_tokens"),
        py::arg("iterations") = 100,
        py::arg("feature_fraction") = 0.5,
        py::arg("max_impostors") = 25,
        py::arg("min_impostors") = 3,
        py::arg("min_chunks") = 2,
        py::arg("chunk_words") = 200,
        py::arg("seed") = 1,
        "General Impostors score of each candidate; returns "
        "{name: {available, score, impostors, iterations}}"
    );

    m.def("style_features",
        [](const std::vector<std::string>& messages,
           const std::vector<std::string>& function_words,
           const std::vector<std::string>& filler_words,
           const std::vector<std::string>& ignored_tokens,
           const std::vector<std::string>& nonstandard_words,
           const std::vector<std::string>& conjunctions,
           unsigned groups) {
            const chatstyle::StyleLexicon lexicon{
                to_u32(function_words), to_u32(filler_words), to_u32(ignored_tokens),
                to_u32(nonstandard_words), to_u32(conjunctions), groups};
            const auto message_text = to_u32(messages);
            chatstyle::SparseVector features;
            {
                py::gil_scoped_release release;
                features = chatstyle::style_features(message_text, lexicon);
            }
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
        py::arg("nonstandard_words") = std::vector<std::string>{},
        py::arg("conjunctions") = std::vector<std::string>{},
        py::arg("groups") = chatstyle::kGroupAll,
        "Style features of an author (without n-grams); returns {name: value}"
    );
}
