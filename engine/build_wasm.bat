@echo off
REM DepthWizard - Emscripten WASM Build Script (Windows)
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set OUTPUT_DIR=%SCRIPT_DIR%..\app\static\viewer

echo === Building DepthWizard Raylib Flythrough for WebAssembly ===

where emcc >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: emcc not found in PATH.
    echo Please install or activate EMSDK:
    echo   emsdk_env.bat
    exit /b 1
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

em++ ^
    "%SCRIPT_DIR%src\main.cpp" ^
    "%SCRIPT_DIR%src\camera.cpp" ^
    "%SCRIPT_DIR%src\terrain.cpp" ^
    -o "%OUTPUT_DIR%\raylib_viewer.html" ^
    -std=c++17 ^
    -O3 ^
    -DPLATFORM_WEB ^
    -lraylib ^
    -sUSE_GLFW=3 ^
    -sASYNCIFY ^
    -sALLOW_MEMORY_GROWTH=1 ^
    -sMAX_WEBGL_VERSION=2 ^
    -sMIN_WEBGL_VERSION=2 ^
    -sEXPORTED_RUNTIME_METHODS="['ccall','cwrap']"

echo === Build Complete! ===
