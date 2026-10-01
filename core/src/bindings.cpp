#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <chatstyle/compare.hpp>
#include <chatstyle/version.hpp>
#include <string>
#include <vector>

namespace py = pybind11;

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
}
