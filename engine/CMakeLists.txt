cmake_minimum_required(VERSION 3.15)
project(DepthWizardFlythrough LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Source files
set(SOURCES
    src/main.cpp
    src/camera.cpp
    src/terrain.cpp
)

# Detect if compiling with Emscripten for WebAssembly
if(EMSCRIPTEN)
    message(STATUS "Building for WebAssembly (Emscripten)")
    add_executable(raylib_viewer ${SOURCES})

    # Emscripten flags
    target_link_options(raylib_viewer PRIVATE
        "-sUSE_GLFW=3"
        "-sASYNCIFY"
        "-sALLOW_MEMORY_GROWTH=1"
        "-sMAX_WEBGL_VERSION=2"
        "-sMIN_WEBGL_VERSION=2"
        "-sEXPORTED_RUNTIME_METHODS=['ccall','cwrap']"
        "-O3"
    )
    
    # Destination output directly into app/static/viewer/
    set_target_properties(raylib_viewer PROPERTIES
        OUTPUT_NAME "raylib_viewer"
        SUFFIX ".html"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../app/static/viewer"
    )
else()
    message(STATUS "Building for Native Desktop")
    find_package(raylib 5.0 QUIET)
    
    add_executable(depthwizard_flythrough ${SOURCES})
    
    if(raylib_FOUND)
        target_link_libraries(depthwizard_flythrough PRIVATE raylib)
    else()
        message(WARNING "raylib package not found via find_package. Fetching from GitHub...")
        include(FetchContent)
        FetchContent_Declare(
            raylib
            GIT_REPOSITORY https://github.com/raysan5/raylib.git
            GIT_TAG 5.0
        )
        FetchContent_MakeAvailable(raylib)
        target_link_libraries(depthwizard_flythrough PRIVATE raylib)
    endif()
endif()
