@echo off
REM DepthWizard - Emscripten WASM Build Script (Windows)
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set OUTPUT_DIR=%SCRIPT_DIR%..\app\static\viewer
set RAYLIB_WEB=%SCRIPT_DIR%raylib_web\raylib-6.0_webassembly

echo === Building DepthWizard Raylib 6.0 Flythrough for WebAssembly (C++20) ===

where emcc >nul 2>nul
if %errorlevel% neq 0 (
    if exist "C:\raylib\emsdk\upstream\emscripten\emcc.bat" (
        echo Found EMSDK in C:\raylib\emsdk. Activating...
        set PATH=C:\raylib\emsdk\upstream\emscripten;C:\raylib\emsdk\upstream\bin;!PATH!
    ) else if exist "%USERPROFILE%\emsdk-main\upstream\emscripten\emcc.exe" (
        echo Found EMSDK in %USERPROFILE%\emsdk-main. Activating...
        set PATH=%USERPROFILE%\emsdk-main\upstream\emscripten;%USERPROFILE%\emsdk-main\upstream\bin;!PATH!
    ) else if exist "C:\emsdk\upstream\emscripten\emcc.exe" (
        echo Found EMSDK in C:\emsdk. Activating...
        set PATH=C:\emsdk\upstream\emscripten;C:\emsdk\upstream\bin;!PATH!
    )
)

where emcc >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: emcc not found in PATH.
    echo Please install or activate EMSDK:
    echo   emsdk_env.bat
    exit /b 1
)

REM Embed GLSL shaders from shaders\*.glsl into src\shaders_gen\*.h
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: python not found in PATH. Required to embed shaders before build.
    exit /b 1
)
python "%SCRIPT_DIR%tools\embed_shaders.py"
if %errorlevel% neq 0 (
    echo Error: shader embedding failed.
    exit /b 1
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

em++ ^
    "%SCRIPT_DIR%src\main.cpp" ^
    "%SCRIPT_DIR%src\camera.cpp" ^
    "%SCRIPT_DIR%src\terrain.cpp" ^
    "%SCRIPT_DIR%src\world.cpp" ^
    "%SCRIPT_DIR%src\sky.cpp" ^
    "%SCRIPT_DIR%src\clouds.cpp" ^
    "%SCRIPT_DIR%src\plane.cpp" ^
    "%SCRIPT_DIR%src\walker.cpp" ^
    -o "%OUTPUT_DIR%\raylib_viewer.js" ^
    -std=c++20 ^
    -O2 ^
    -DPLATFORM_WEB ^
    -I "%RAYLIB_WEB%\include" ^
    "%RAYLIB_WEB%\lib\libraylib.web.a" ^
    -sUSE_GLFW=3 ^
    -sALLOW_MEMORY_GROWTH=1 ^
    -sEXPORTED_RUNTIME_METHODS="['ccall','cwrap','FS']" ^
    -sEXPORTED_FUNCTIONS="['_main','_LoadTerrainFromMemory','_LoadPlaneModel','_LoadPlaneTexture','_ToggleWireframe','_CycleRenderMode','_GetRenderMode','_TriggerProbe','_GetProbeDeltaH','_GetGroundSlope','_ResetCamera','_SetGameMode','_GetGameMode','_GetCameraAlt','_GetCameraPosX','_GetCameraPosZ','_GetCameraPitch','_GetEngineFPS','_GetAirspeedKmh','_GetThrottlePct']"

echo === Build Complete! Output: %OUTPUT_DIR%\raylib_viewer.js ===

