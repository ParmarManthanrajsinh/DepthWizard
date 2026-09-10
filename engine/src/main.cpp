#include "raylib.h"
#include "raymath.h"
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

// Structural height analysis probe state
static bool bHasProbeA = false;
static bool bHasProbeB = false;
static Vector3 GProbeA = { 0.0f, 0.0f, 0.0f };
static Vector3 GProbeB = { 0.0f, 0.0f, 0.0f };
static float GProbeDeltaH = 0.0f;
static float GSurfaceSlope = 0.0f;

static void HandleProbePoint(const Vector3& InHitPoint)
{
    if (!bHasProbeA)
    {
        GProbeA = InHitPoint;
        bHasProbeA = true;
        bHasProbeB = false;
        GProbeDeltaH = 0.0f;
    }
    else if (!bHasProbeB)
    {
        GProbeB = InHitPoint;
        bHasProbeB = true;
        GProbeDeltaH = fabsf((GProbeB.y - GProbeA.y) * 10.0f);
    }
    else
    {
        // Reset measurement
        bHasProbeA = false;
        bHasProbeB = false;
        GProbeDeltaH = 0.0f;
    }
}

static bool GetBestTerrainHit(Vector3& OutHitPoint, Vector3& OutHitNormal)
{
    // 1. Mouse cursor raycast if hovering inside canvas
    const Vector2 MousePos = GetMousePosition();
    if (MousePos.x >= 0.0f && MousePos.x <= static_cast<float>(GetScreenWidth()) &&
        MousePos.y >= 0.0f && MousePos.y <= static_cast<float>(GetScreenHeight()))
    {
        const Ray MouseRay = GetScreenToWorldRay(MousePos, GCamera.Camera);
        if (GTerrain.Raycast(MouseRay, OutHitPoint, OutHitNormal))
        {
            return true;
        }
    }

    // 2. Center crosshair raycast along camera forward vector
    const Vector3 CamForward = Vector3Normalize(Vector3Subtract(GCamera.Camera.target, GCamera.Camera.position));
    const Ray CenterRay = { GCamera.Camera.position, CamForward };
    if (GTerrain.Raycast(CenterRay, OutHitPoint, OutHitNormal))
    {
        return true;
    }

    // 3. Nadir downcast beneath current flight altitude
    const Ray DownRay = { GCamera.Camera.position, Vector3{ 0.0f, -1.0f, 0.0f } };
    if (GTerrain.Raycast(DownRay, OutHitPoint, OutHitNormal))
    {
        return true;
    }

    return false;
}

extern "C"
{
#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int LoadTerrainFromMemory(const char* InFilePath)
    {
        if (!InFilePath) return 0;
        const bool bSuccess = GTerrain.Load(std::string_view(InFilePath));
        if (bSuccess)
        {
            GCamera.Reset();
            bHasProbeA = false;
            bHasProbeB = false;
            GProbeDeltaH = 0.0f;
        }
        return bSuccess ? 1 : 0;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ToggleWireframe() { GTerrain.ToggleWireframe(); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void CycleRenderMode() { GTerrain.CycleRenderMode(); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int GetRenderMode() { return static_cast<int>(GTerrain.RenderMode); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ResetCamera() { GCamera.Reset(); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraAlt()   { return GCamera.Camera.position.y * 10.0f; }
    float GetCameraPosX()  { return GCamera.Camera.position.x; }
    float GetCameraPosZ()  { return GCamera.Camera.position.z; }
    float GetCameraPitch() { return fabsf(GCamera.Pitch) * (180.0f / 3.14159265f); }
    int GetEngineFPS()     { return GetFPS(); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetProbeDeltaH() { return GProbeDeltaH; }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetGroundSlope() { return GSurfaceSlope; }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void TriggerProbe()
    {
        Vector3 HitPoint = { 0 };
        Vector3 HitNormal = { 0.0f, 1.0f, 0.0f };
        if (GetBestTerrainHit(HitPoint, HitNormal))
        {
            HandleProbePoint(HitPoint);
        }
    }
}

void UpdateDrawFrame()
{
    const float DeltaTime = GetFrameTime();

    // Toggle wireframe mode via X key
    if (IsKeyPressed(KEY_X))
    {
        GTerrain.ToggleWireframe();
    }

    // Cycle shading mode (Optical RGB vs Hillshade) via T key
    if (IsKeyPressed(KEY_T))
    {
        GTerrain.CycleRenderMode();
    }

    // Raycast to terrain surface (mouse cursor -> center crosshair -> nadir downcast)
    Vector3 HitPoint = { 0 };
    Vector3 HitNormal = { 0.0f, 1.0f, 0.0f };
    const bool bHit = GetBestTerrainHit(HitPoint, HitNormal);

    if (bHit)
    {
        const float NormalY = fminf(fmaxf(HitNormal.y, -1.0f), 1.0f);
        GSurfaceSlope = acosf(NormalY) * (180.0f / 3.14159265f);
    }
    else
    {
        GSurfaceSlope = 0.0f;
    }

    // Trigger structural height probe via P key
    if (IsKeyPressed(KEY_P) && bHit)
    {
        HandleProbePoint(HitPoint);
    }

    GCamera.Update(DeltaTime);

    BeginDrawing();
    ClearBackground(Color{ 10, 12, 16, 255 });

    BeginMode3D(GCamera.Camera);
        DrawGrid(80, 5.0f);

        if (GTerrain.bIsLoaded)
        {
            GTerrain.Draw();
        }

        // Draw 3D probe markers & measurement line
        if (bHasProbeA)
        {
            DrawSphere(GProbeA, 0.9f, Color{ 0, 240, 255, 255 });
        }
        if (bHasProbeB)
        {
            DrawSphere(GProbeB, 0.9f, Color{ 255, 51, 51, 255 });
            DrawLine3D(GProbeA, GProbeB, Color{ 255, 220, 0, 255 });
        }
    EndMode3D();

    const int32_t AltitudeMeters = static_cast<int32_t>(GCamera.Camera.position.y * 10.0f);
    const int32_t PosX = static_cast<int32_t>(GCamera.Camera.position.x);
    const int32_t PosZ = static_cast<int32_t>(GCamera.Camera.position.z);
    const int32_t PitchDeg = static_cast<int32_t>(fabsf(GCamera.Pitch) * (180.0f / 3.14159265f));
    const int32_t SurfaceSlopeDeg = static_cast<int32_t>(GSurfaceSlope);
    const int32_t CurrentFPS = GetFPS();
    const int32_t CurrentMode = static_cast<int32_t>(GTerrain.RenderMode);
    const int32_t DeltaHMeters = static_cast<int32_t>(GProbeDeltaH);
    const int32_t ProbeStatus = bHasProbeB ? 2 : (bHasProbeA ? 1 : 0);

#ifdef PLATFORM_WEB
    EM_ASM({
        if (window.updateWasmHUD) {
            window.updateWasmHUD($0, $1, $2, $3, $4, $5, $6, $7, $8);
        }
    }, AltitudeMeters, PosX, PosZ, PitchDeg, SurfaceSlopeDeg, CurrentFPS, CurrentMode, DeltaHMeters, ProbeStatus);
#else
    DrawRectangle(20, 20, 300, 210, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawRectangleLines(20, 20, 300, 210, Fade(Color{ 0, 240, 255, 255 }, 0.4f));

    DrawText("FLYTHROUGH TELEMETRY", 35, 30, 14, Color{ 0, 240, 255, 255 });
    
    const std::string AltText = "Altitude: " + std::to_string(AltitudeMeters) + " m";
    DrawText(AltText.c_str(), 35, 52, 13, RAYWHITE);

    const std::string PosText = "Position: X=" + std::to_string(PosX) + " Z=" + std::to_string(PosZ);
    DrawText(PosText.c_str(), 35, 72, 13, LIGHTGRAY);

    const std::string SlopeText = "Ground Slope: " + std::to_string(SurfaceSlopeDeg) + " deg";
    DrawText(SlopeText.c_str(), 35, 92, 13, LIGHTGRAY);

    const char* ModeName = (CurrentMode == 0) ? "MODE: OPTICAL RGB" : (CurrentMode == 1 ? "MODE: HILLSHADE" : "MODE: WIREFRAME");
    DrawText(ModeName, 35, 114, 13, (CurrentMode == 0) ? Color{ 0, 240, 255, 255 } : Color{ 255, 200, 50, 255 });

    std::string ProbeText = (ProbeStatus == 2) ? ("Probe Delta H: " + std::to_string(DeltaHMeters) + " m") :
                            ((ProbeStatus == 1) ? "Probe: Set Target Point" : "Probe: Press P to mark point");
    DrawText(ProbeText.c_str(), 35, 136, 13, Color{ 255, 220, 0, 255 });

    DrawText(TextFormat("FPS: %i", CurrentFPS), 35, 160, 13, Color{ 0, 230, 118, 255 });

    DrawRectangle(20, GScreenHeight - 65, 510, 45, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawText("Controls: WASD=Fly | Space/C=Alt | P=Measure dH | T=Texture | X=Wireframe", 30, GScreenHeight - 52, 11, GRAY);
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

    GCamera.Reset();
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
