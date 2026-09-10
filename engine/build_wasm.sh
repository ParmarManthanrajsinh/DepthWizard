#!/bin/bash
# DepthWizard - Emscripten WASM Build Script (Raylib 6.0 · C++20)
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_DIR="${SCRIPT_DIR}/../app/static/viewer"
RAYLIB_WEB="${SCRIPT_DIR}/raylib_web/raylib-6.0_webassembly"
mkdir -p "${OUTPUT_DIR}"

echo "=== Building DepthWizard Raylib 6.0 Flythrough for WebAssembly (C++20) ==="

if ! command -v emcc &> /dev/null; then
    echo "Error: emcc not found. Please source your emsdk environment:"
    echo "  source /path/to/emsdk/emsdk_env.sh"
    exit 1
fi

em++ \
    "${SCRIPT_DIR}/src/main.cpp" \
    "${SCRIPT_DIR}/src/camera.cpp" \
    "${SCRIPT_DIR}/src/terrain.cpp" \
    -o "${OUTPUT_DIR}/raylib_viewer.js" \
    -std=c++20 \
    -O2 \
    -DPLATFORM_WEB \
    -I "${RAYLIB_WEB}/include" \
    "${RAYLIB_WEB}/lib/libraylib.web.a" \
    -sUSE_GLFW=3 \
    -sALLOW_MEMORY_GROWTH=1 \
    -sEXPORTED_RUNTIME_METHODS="['ccall','cwrap','FS']" \
    -sEXPORTED_FUNCTIONS="['_main','_LoadTerrainFromMemory','_ToggleWireframe','_ResetCamera','_GetCameraAlt','_GetCameraPosX','_GetCameraPosZ','_GetCameraPitch','_GetEngineFPS']"

echo "=== Build Complete! Output: ${OUTPUT_DIR}/raylib_viewer.js ==="
