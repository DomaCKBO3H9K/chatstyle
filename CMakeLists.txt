cmake_minimum_required(VERSION 3.20)
project(chatstyle LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(CHATSTYLE_BUILD_PYTHON "Build Python bindings" ON)

# Static library for core functionality
add_library(chatstyle_core STATIC core/src/version.cpp core/src/text.cpp)
target_include_directories(chatstyle_core PUBLIC core/include)
set_target_properties(chatstyle_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    target_compile_options(chatstyle_core PRIVATE /W4 /utf-8 /permissive-)
else()
    target_compile_options(chatstyle_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(CHATSTYLE_BUILD_PYTHON)
    find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
    find_package(pybind11 CONFIG REQUIRED)

    # Python bindings module
    pybind11_add_module(_core core/src/bindings.cpp)
    target_include_directories(_core PRIVATE core/include)
    target_link_libraries(_core PRIVATE chatstyle_core)

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
endif()

# Optional C++ tests
option(CHATSTYLE_BUILD_TESTS "Build C++ tests" OFF)

if(CHATSTYLE_BUILD_TESTS)
    enable_testing()
    include(FetchContent)
    FetchContent_Declare(
        Catch2
        GIT_REPOSITORY https://github.com/catchorg/Catch2.git
        GIT_TAG v3.7.1
    )
    FetchContent_MakeAvailable(Catch2)

    add_executable(core_tests core/tests/test_smoke.cpp core/tests/test_text.cpp)
    target_link_libraries(core_tests PRIVATE chatstyle_core Catch2::Catch2WithMain)

    if(MSVC)
        target_compile_options(core_tests PRIVATE /W4 /utf-8 /permissive-)
    else()
        target_compile_options(core_tests PRIVATE -Wall -Wextra -Wpedantic)
    endif()

    if(MINGW)
        target_link_options(core_tests PRIVATE -static)
    endif()

    list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)
    include(Catch)
    catch_discover_tests(core_tests)
endif()
