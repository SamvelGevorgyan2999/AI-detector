cmake_minimum_required(VERSION 3.16)

project(origincheck_forensics LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_forensics
    cpp/src/forensics.cpp
    cpp/src/bindings.cpp
)

target_include_directories(_forensics PRIVATE
    cpp/include
)

target_link_libraries(_forensics PRIVATE
    Python3::Python
)

set_target_properties(_forensics PROPERTIES
    OUTPUT_NAME "_forensics"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/origincheck"
)