#include <pybind11/pybind11.h>
#include <chatstyle/version.hpp>
#include <string>

PYBIND11_MODULE(_core, m) {
    m.doc() = "chatstyle core";
    m.def("version", &chatstyle::version, "Версия ядра");
}
