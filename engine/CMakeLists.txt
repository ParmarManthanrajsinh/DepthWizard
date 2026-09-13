cmake_minimum_required(VERSION 3.15)
project(DepthWizardFlythrough LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Source files
set(SOURCES
    src/main.cpp
    src/camera.cpp
    src/terrain.cpp
    src/world.cpp
    src/sky.cpp
    src/clouds.cpp
    src/plane.cpp
    src/walker.cpp
)

# GLSL shaders live in shaders/*.glsl and are embedded into
# src/shaders_gen/*.h before every build (see tools/embed_shaders.py).
# Runtime loading is unchanged (LoadShaderFromMemory).
find_program(DEPTHWIZARD_PYTHON python3 python)
if(DEPTHWIZARD_PYTHON)
    add_custom_target(embed_shaders ALL
        COMMAND ${DEPTHWIZARD_PYTHON} "${CMAKE_CURRENT_SOURCE_DIR}/tools/embed_shaders.py"
        COMMENT "Embedding GLSL shaders into src/shaders_gen/"
    )
else()
    message(WARNING "python3/python not found; using checked-in src/shaders_gen/ headers without regenerating")
endif()

# Detect if compiling with Emscripten for WebAssembly
if(EMSCRIPTEN)
    message(STATUS "Building for WebAssembly (Emscripten)")
    add_executable(raylib_viewer ${SOURCES})

    # Emscripten flags
    target_link_options(raylib_viewer PRIVATE
        "-std=c++20"
        "-sUSE_GLFW=3"
        "-sALLOW_MEMORY_GROWTH=1"
        "-sMAX_WEBGL_VERSION=2"
        "-sMIN_WEBGL_VERSION=2"
        "-sEXPORTED_RUNTIME_METHODS=['ccall','cwrap','FS']"
        "-sEXPORTED_FUNCTIONS=['_main','_LoadTerrainFromMemory','_LoadPlaneModel','_ToggleWireframe','_CycleRenderMode','_GetRenderMode','_TriggerProbe','_GetProbeDeltaH','_GetGroundSlope','_ResetCamera','_SetGameMode','_GetGameMode','_GetCameraAlt','_GetCameraPosX','_GetCameraPosZ','_GetCameraPitch','_GetEngineFPS','_GetAirspeedKmh','_GetThrottlePct']"
        "-O2"
    )
    
    # Destination output directly into app/static/viewer/
    set_target_properties(raylib_viewer PROPERTIES
        OUTPUT_NAME "raylib_viewer"
        SUFFIX ".js"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../app/static/viewer"
    )
    if(TARGET embed_shaders)
        add_dependencies(raylib_viewer embed_shaders)
    endif()
else()
    message(STATUS "Building for Native Desktop")
    find_package(raylib QUIET)
    
    add_executable(depthwizard_flythrough ${SOURCES})
    if(TARGET embed_shaders)
        add_dependencies(depthwizard_flythrough embed_shaders)
    endif()
    
    if(raylib_FOUND)
        target_link_libraries(depthwizard_flythrough PRIVATE raylib)
    else()
        message(WARNING "raylib package not found via find_package. Fetching from GitHub...")
        include(FetchContent)
        FetchContent_Declare(
            raylib
            GIT_REPOSITORY https://github.com/raysan5/raylib.git
            GIT_TAG master
        )
        FetchContent_MakeAvailable(raylib)
        target_link_libraries(depthwizard_flythrough PRIVATE raylib)
    endif()
endif()
