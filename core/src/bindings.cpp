#include <pybind11/pybind11.h>
#include <string>

namespace chatstyle {
    std::string version() {
        return "0.1.0";
    }
}

PYBIND11_MODULE(_core, m) {
    m.doc() = "chatstyle core";
    m.def("version", &chatstyle::version, "Версия ядра");
}
