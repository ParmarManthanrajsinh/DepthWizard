#!/bin/bash
# DepthWizard - Emscripten WASM Build Script
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_DIR="${SCRIPT_DIR}/../app/static/viewer"
mkdir -p "${OUTPUT_DIR}"

echo "=== Building DepthWizard Raylib Flythrough for WebAssembly ==="

if ! command -v emcc &> /dev/null; then
    echo "Error: emcc not found. Please source your emsdk environment:"
    echo "  source /path/to/emsdk/emsdk_env.sh"
    exit 1
fi

em++ \
    "${SCRIPT_DIR}/src/main.cpp" \
    "${SCRIPT_DIR}/src/camera.cpp" \
    "${SCRIPT_DIR}/src/terrain.cpp" \
    -o "${OUTPUT_DIR}/raylib_viewer.html" \
    -std=c++17 \
    -O3 \
    -DPLATFORM_WEB \
    -lraylib \
    -sUSE_GLFW=3 \
    -sASYNCIFY \
    -sALLOW_MEMORY_GROWTH=1 \
    -sMAX_WEBGL_VERSION=2 \
    -sMIN_WEBGL_VERSION=2 \
    --shell-file "${SCRIPT_DIR}/src/minshell.html" \
    -sEXPORTED_RUNTIME_METHODS="['ccall','cwrap']"

echo "=== Build Complete! Outputs in app/static/viewer/ ==="
