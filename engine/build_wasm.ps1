# DepthWizard - Emscripten WASM Build Script (PowerShell)
$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$outputDir = Join-Path $scriptDir "..\app\static\viewer"
$raylibWebDir = Join-Path $scriptDir "raylib_web\raylib-6.0_webassembly"

Write-Host "=== Building DepthWizard Raylib 6.0 Flythrough for WebAssembly (C++20) ===" -ForegroundColor Cyan

# Auto-discover EMSDK if not in current PATH
if (-not (Get-Command emcc -ErrorAction SilentlyContinue)) {
    $emsdkCandidates = @(
        "C:\raylib\emsdk",
        "$env:USERPROFILE\emsdk-main",
        "C:\emsdk",
        "$env:LOCALAPPDATA\emsdk"
    )
    foreach ($cand in $emsdkCandidates) {
        $emccPath = Join-Path $cand "upstream\emscripten"
        $binPath = Join-Path $cand "upstream\bin"
        if (Test-Path (Join-Path $emccPath "emcc.bat")) {
            Write-Host "Found EMSDK at $cand. Activating environment..." -ForegroundColor Green
            $env:PATH = "$emccPath;$binPath;$env:PATH"
            break
        } elseif (Test-Path (Join-Path $emccPath "emcc.exe")) {
            Write-Host "Found EMSDK at $cand. Activating environment..." -ForegroundColor Green
            $env:PATH = "$emccPath;$binPath;$env:PATH"
            break
        }
    }
}

if (-not (Get-Command emcc -ErrorAction SilentlyContinue)) {
    Write-Error "emcc not found in PATH or standard EMSDK locations. Please install or activate EMSDK."
    exit 1
}

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$srcFiles = @(
    (Join-Path $scriptDir "src\main.cpp"),
    (Join-Path $scriptDir "src\camera.cpp"),
    (Join-Path $scriptDir "src\terrain.cpp")
)

$targetJs = Join-Path $outputDir "raylib_viewer.js"
$raylibInc = Join-Path $raylibWebDir "include"
$raylibLib = Join-Path $raylibWebDir "lib\libraylib.web.a"

& em++ @srcFiles `
    -o $targetJs `
    -std=c++20 `
    -O2 `
    -DPLATFORM_WEB `
    -I "$raylibInc" `
    "$raylibLib" `
    -sUSE_GLFW=3 `
    -sALLOW_MEMORY_GROWTH=1 `
    -sEXPORTED_RUNTIME_METHODS="['ccall','cwrap','FS']" `
    -sEXPORTED_FUNCTIONS="['_main','_LoadTerrainFromMemory','_ToggleWireframe','_CycleRenderMode','_GetRenderMode','_TriggerProbe','_GetProbeDeltaH','_GetGroundSlope','_ResetCamera','_GetCameraAlt','_GetCameraPosX','_GetCameraPosZ','_GetCameraPitch','_GetEngineFPS']"

Write-Host "=== Build Complete! Output: $targetJs ===" -ForegroundColor Green

