cmake_minimum_required(VERSION 3.20)
project(ghd C)

set(CMAKE_C_STANDARD 11)

add_executable(ghd ghd.c)
set_property(TARGET ghd PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
