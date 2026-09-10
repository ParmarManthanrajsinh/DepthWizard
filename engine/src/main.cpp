#include "raylib.h"
#include "camera.h"
#include "terrain.h"
#include <string>
#include <string_view>
#include <cmath>
#include <cstdint>

#ifdef PLATFORM_WEB
    #include <emscripten/emscripten.h>
#endif

// Global application state (Unreal standard G-prefix)
static FFreeFlyCamera GCamera;
static FTerrainRenderer GTerrain;
static int32_t GScreenWidth = 1280;
static int32_t GScreenHeight = 720;
static std::string GMeshPath = "data/outputs/sample_terrain.glb";

extern "C"
{
#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int LoadTerrainFromMemory(const char* InFilePath)
    {
        if (!InFilePath)
        {
            return 0;
        }

        const bool bSuccess = GTerrain.Load(std::string_view(InFilePath));
        if (bSuccess)
        {
            GCamera.Initialize(Vector3{ 0.0f, 45.0f, 85.0f }, Vector3{ 0.0f, 20.0f, 0.0f });
        }
        return bSuccess ? 1 : 0;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ToggleWireframe()
    {
        GTerrain.ToggleWireframe();
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ResetCamera()
    {
        GCamera.Reset();
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraAlt()
    {
        return GCamera.Camera.position.y * 10.0f;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraPosX()
    {
        return GCamera.Camera.position.x;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraPosZ()
    {
        return GCamera.Camera.position.z;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraPitch()
    {
        return fabsf(GCamera.Pitch) * (180.0f / 3.14159265f);
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int GetEngineFPS()
    {
        return GetFPS();
    }
}

void UpdateDrawFrame()
{
    const float DeltaTime = GetFrameTime();

    // Toggle wireframe mode via keyboard shortcut
    if (IsKeyPressed(KEY_X))
    {
        GTerrain.ToggleWireframe();
    }

    // Advance camera state
    GCamera.Update(DeltaTime);

    // Frame rendering pass
    BeginDrawing();
    ClearBackground(Color{ 10, 12, 16, 255 });

    BeginMode3D(GCamera.Camera);
        // Spatial reference grid
        DrawGrid(60, 4.0f);

        // Terrain surface or wireframe
        if (GTerrain.bIsLoaded)
        {
            GTerrain.Draw();
        }
    EndMode3D();

    const int32_t AltitudeMeters = static_cast<int32_t>(GCamera.Camera.position.y * 10.0f);
    const int32_t PosX = static_cast<int32_t>(GCamera.Camera.position.x);
    const int32_t PosZ = static_cast<int32_t>(GCamera.Camera.position.z);
    const int32_t PitchDegrees = static_cast<int32_t>(fabsf(GCamera.Pitch) * (180.0f / 3.14159265f));
    const int32_t CurrentFPS = GetFPS();

#ifdef PLATFORM_WEB
    // Push live telemetry directly to HTML HUD
    EM_ASM({
        if (window.updateWasmHUD) {
            window.updateWasmHUD($0, $1, $2, $3, $4);
        }
    }, AltitudeMeters, PosX, PosZ, PitchDegrees, CurrentFPS);
#else
    // Desktop Raylib Overlay
    DrawRectangle(20, 20, 280, 160, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawRectangleLines(20, 20, 280, 160, Fade(Color{ 0, 240, 255, 255 }, 0.4f));

    DrawText("FLYTHROUGH TELEMETRY", 35, 32, 14, Color{ 0, 240, 255, 255 });
    
    const std::string AltText = "Altitude: " + std::to_string(AltitudeMeters) + " m";
    DrawText(AltText.c_str(), 35, 56, 13, RAYWHITE);

    const std::string PosText = "Position: X=" + std::to_string(PosX) + " Z=" + std::to_string(PosZ);
    DrawText(PosText.c_str(), 35, 78, 13, LIGHTGRAY);

    const std::string SlopeText = "Pitch: " + std::to_string(PitchDegrees) + " deg";
    DrawText(SlopeText.c_str(), 35, 100, 13, LIGHTGRAY);

    DrawText(TextFormat("FPS: %i", CurrentFPS), 35, 124, 13, Color{ 0, 230, 118, 255 });

    DrawRectangle(20, GScreenHeight - 65, 380, 45, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawText("Controls: WASD=Fly | Space/C=Climb/Descend | X=Wireframe", 30, GScreenHeight - 52, 11, GRAY);
#endif

    EndDrawing();
}

int main(int argc, char* argv[])
{
    if (argc > 1 && argv[1] != nullptr)
    {
        GMeshPath = argv[1];
    }

    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_WINDOW_RESIZABLE);
    InitWindow(GScreenWidth, GScreenHeight, "DepthWizard - 3D Terrain Flythrough (ISRO SIH26175)");
    SetTargetFPS(60);

    GCamera.Initialize(Vector3{ 0.0f, 45.0f, 85.0f }, Vector3{ 0.0f, 20.0f, 0.0f });
    GTerrain.Load(std::string_view(GMeshPath));

#ifdef PLATFORM_WEB
    emscripten_set_main_loop(UpdateDrawFrame, 0, 1);
#else
    while (!WindowShouldClose())
    {
        UpdateDrawFrame();
    }
    GTerrain.Unload();
    CloseWindow();
#endif

    return 0;
}
