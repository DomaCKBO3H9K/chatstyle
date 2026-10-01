cmake_minimum_required(VERSION 3.20)
project(chatstyle LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_core core/src/bindings.cpp)
target_include_directories(_core PRIVATE core/include)

if(MSVC)
    target_compile_options(_core PRIVATE /W4 /utf-8 /permissive-)
else()
    target_compile_options(_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(MINGW)
    target_link_options(_core PRIVATE -static)
endif()

install(TARGETS _core
    LIBRARY DESTINATION chatstyle
    RUNTIME DESTINATION chatstyle
)
