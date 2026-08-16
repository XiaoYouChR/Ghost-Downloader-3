cmake_minimum_required(VERSION 3.20)
project(gd3-updater C)

set(CMAKE_C_STANDARD 11)

if(APPLE)
    set(CMAKE_OSX_ARCHITECTURES "x86_64;arm64")
endif()

add_executable(updater updater.c)

if(WIN32)
    set_property(TARGET updater PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
    target_link_libraries(updater PRIVATE shell32 advapi32 user32)
endif()
