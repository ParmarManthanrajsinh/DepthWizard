#include "raylib.h"
#include "raymath.h"
#include "camera.h"
#include "terrain.h"
#include "game_modes.h"
#include "world.h"
#include "sky.h"
#include "plane.h"
#include "walker.h"
#include "clouds.h"
#include "rl_local.h"
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
static FWorldDressing GWorld;
static FSkyDome GSky;
static FVolumetricCloudRenderer GClouds;
static FArcadePlane GPlane;
static FFPSWalker GWalker;
static EGameMode GGameMode = EGameMode::FreeFly;
static Vector3 GSmChasePos = { 0.0f, 0.0f, 0.0f };
static Vector3 GSmChaseTarget = { 0.0f, 0.0f, 0.0f };
static bool bChaseInit = false;
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

static void ClearProbes()
{
    bHasProbeA = false;
    bHasProbeB = false;
    GProbeDeltaH = 0.0f;
}

static void SetGameModeInternal(EGameMode InMode)
{
    if (GGameMode == InMode)
    {
        return;
    }
    GGameMode = InMode;
    if (GGameMode == EGameMode::Plane)
    {
        // Resume from the plane's current pose (initial spawn after mesh load).
        // Seed the damped chase so entry glides instead of snapping.
        GPlane.GetChasePose(GSmChasePos, GSmChaseTarget);
        bChaseInit = true;
        GCamera.Camera.position = GSmChasePos;
        GCamera.Camera.target = GSmChaseTarget;
    }
    else if (GGameMode == EGameMode::FPS)
    {
        // Drop to the ground under the current camera XZ, preserving current look orientation.
        GWalker.Spawn(GTerrain.bIsLoaded ? &GTerrain : nullptr,
                      GCamera.Camera.position.x, GCamera.Camera.position.z,
                      GCamera.Yaw, GCamera.Pitch);
        Vector3 EyePos = { 0.0f, 0.0f, 0.0f };
        Vector3 LookAt = { 0.0f, 0.0f, 0.0f };
        GWalker.GetEyePose(EyePos, LookAt);
        GCamera.Camera.position = EyePos;
        GCamera.Camera.target = LookAt;
    }
}

static void ResetActiveMode()
{
    if (GGameMode == EGameMode::Plane)
    {
        GPlane.Spawn(GTerrain.bIsLoaded ? &GTerrain : nullptr);
    }
    else if (GGameMode == EGameMode::FPS)
    {
        GWalker.Spawn(GTerrain.bIsLoaded ? &GTerrain : nullptr, 0.0f, 60.0f);
    }
    else
    {
        GCamera.Reset();
    }
    ClearProbes();
}

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
            GWorld.Rebuild(&GTerrain);
            GPlane.Spawn(&GTerrain);
            GWalker.Spawn(&GTerrain, 0.0f, 60.0f);
            GGameMode = EGameMode::FreeFly;
            ClearProbes();
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
    void ResetCamera() { ResetActiveMode(); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int LoadPlaneModel(const char* InFilePath)
    {
        if (!InFilePath) return 0;
        return GPlane.LoadPlaneModel(InFilePath) ? 1 : 0;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int LoadPlaneTexture(const char* InFilePath)
    {
        if (!InFilePath) return 0;
        return GPlane.LoadPlaneTexture(InFilePath) ? 1 : 0;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void SetGameMode(int InMode) { SetGameModeInternal(ClampGameMode(InMode)); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int GetGameMode() { return static_cast<int>(GGameMode); }

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
    float GetAirspeedKmh() { return GPlane.GetSpeedKmh(); }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetThrottlePct() { return GPlane.GetThrottlePct(); }

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

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ToggleClouds()
    {
        GClouds.ToggleEnabled();
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int32_t GetCloudsEnabled()
    {
        return GClouds.IsEnabled() ? 1 : 0;
    }
}

void UpdateDrawFrame()
{
    const float DeltaTime = GetFrameTime();

    // Mode switching: 1 = Free-fly, 2 = Plane, 3 = FPS, V = cycle.
    if (IsKeyPressed(KEY_ONE)) SetGameModeInternal(EGameMode::FreeFly);
    if (IsKeyPressed(KEY_TWO)) SetGameModeInternal(EGameMode::Plane);
    if (IsKeyPressed(KEY_THREE)) SetGameModeInternal(EGameMode::FPS);
    if (IsKeyPressed(KEY_V))
    {
        SetGameModeInternal(ClampGameMode((static_cast<int32_t>(GGameMode) + 1) % kGameModeCount));
    }
    if (IsKeyPressed(KEY_R)) ResetActiveMode();

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

    // Per-mode locomotion; each mode owns the camera while active.
    // Chase pose is exponentially damped so the view glides, not snaps.
    if (GGameMode == EGameMode::Plane)
    {
        GPlane.Update(DeltaTime, GTerrain.bIsLoaded ? &GTerrain : nullptr);
        Vector3 ChasePos = { 0.0f, 0.0f, 0.0f };
        Vector3 ChaseTarget = { 0.0f, 0.0f, 0.0f };
        GPlane.GetChasePose(ChasePos, ChaseTarget);
        if (!bChaseInit)
        {
            GSmChasePos = ChasePos;
            GSmChaseTarget = ChaseTarget;
            bChaseInit = true;
        }
        const float DtSafe = fmaxf(DeltaTime, 0.0001f);
        const float PosK = 1.0f - expf(-6.0f * DtSafe);
        const float TgtK = 1.0f - expf(-10.0f * DtSafe);
        GSmChasePos = Vector3{
            GSmChasePos.x + (ChasePos.x - GSmChasePos.x) * PosK,
            GSmChasePos.y + (ChasePos.y - GSmChasePos.y) * PosK,
            GSmChasePos.z + (ChasePos.z - GSmChasePos.z) * PosK
        };
        GSmChaseTarget = Vector3{
            GSmChaseTarget.x + (ChaseTarget.x - GSmChaseTarget.x) * TgtK,
            GSmChaseTarget.y + (ChaseTarget.y - GSmChaseTarget.y) * TgtK,
            GSmChaseTarget.z + (ChaseTarget.z - GSmChaseTarget.z) * TgtK
        };
        GCamera.Camera.position = GSmChasePos;
        GCamera.Camera.target = GSmChaseTarget;
        // Gentle FOV kick with airspeed instead of jerking camera distance.
        const float TargetFov = 60.0f + 14.0f * GPlane.GetSpeedNorm();
        GCamera.Camera.fovy += (TargetFov - GCamera.Camera.fovy) * (1.0f - expf(-3.0f * DtSafe));
    }
    else
    {
        bChaseInit = false;
        GCamera.Camera.fovy += (60.0f - GCamera.Camera.fovy) * (1.0f - expf(-3.0f * fmaxf(DeltaTime, 0.0001f)));
        if (GGameMode == EGameMode::FPS)
        {
            GWalker.Update(DeltaTime, GTerrain.bIsLoaded ? &GTerrain : nullptr);
            Vector3 EyePos = { 0.0f, 0.0f, 0.0f };
            Vector3 LookAt = { 0.0f, 0.0f, 0.0f };
            GWalker.GetEyePose(EyePos, LookAt);
            GCamera.Camera.position = EyePos;
            GCamera.Camera.target = LookAt;
            GCamera.Camera.up = Vector3{ 0.0f, 1.0f, 0.0f };
        }
        else
        {
            GCamera.Update(DeltaTime);
        }
    }

    GWorld.Update(DeltaTime);
    GClouds.Update(DeltaTime);
    GTerrain.UpdateFog(GCamera.Camera.position);

    // Render offscreen half-resolution volumetric cloud slab
    GClouds.RenderSlab(GCamera.Camera, GSky.GetSunDir());

    BeginDrawing();
        ClearBackground(FWorldDressing::kHazeColor);
        BeginMode3D(GCamera.Camera);
            GSky.Draw(GCamera.Camera.position);
        EndMode3D();

    // Composite volumetric clouds right after the sky, BEFORE opaque
    // geometry. The composite quad carries no depth, so compositing it
    // last would paste clouds over terrain in front of them. Drawn here,
    // terrain/water/plane overwrite it wherever they are closer.
    rlDisableDepthMask();
    GClouds.DrawComposite(GetScreenWidth(), GetScreenHeight());
    rlEnableDepthMask();

        BeginMode3D(GCamera.Camera);
            if (GTerrain.bIsLoaded)
            {
                GTerrain.Draw();
            }
            else
            {
                DrawGrid(80, 5.0f);
            }

            // Draw ocean water surface with hardware depth testing
            GWorld.Draw(GCamera.Camera.position);
        EndMode3D();

    BeginMode3D(GCamera.Camera);
        // Player plane stays visible in every mode (parked pose when inactive).
        GPlane.Draw(GCamera.Camera.position, GTerrain.bIsLoaded ? &GTerrain : nullptr);

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
    const float ActivePitch = (GGameMode == EGameMode::FPS) ? GWalker.Pitch : GCamera.Pitch;
    const int32_t PitchDeg = static_cast<int32_t>(fabsf(ActivePitch) * (180.0f / 3.14159265f));
    const int32_t SurfaceSlopeDeg = static_cast<int32_t>(GSurfaceSlope);
    const int32_t CurrentFPS = GetFPS();
    const int32_t CurrentMode = static_cast<int32_t>(GTerrain.RenderMode);
    const int32_t DeltaHMeters = static_cast<int32_t>(GProbeDeltaH);
    const int32_t ProbeStatus = bHasProbeB ? 2 : (bHasProbeA ? 1 : 0);
    const int32_t GameMode = static_cast<int32_t>(GGameMode);
    const int32_t SpeedKmh = (GGameMode == EGameMode::Plane) ? static_cast<int32_t>(GPlane.GetSpeedKmh())
                           : (GGameMode == EGameMode::FPS) ? static_cast<int32_t>(GWalker.GetSpeedKmh())
                           : 0;
    const int32_t ThrottlePct = (GGameMode == EGameMode::Plane) ? static_cast<int32_t>(GPlane.GetThrottlePct()) : 0;

#ifdef PLATFORM_WEB
    EM_ASM({
        if (window.updateWasmHUD) {
            window.updateWasmHUD($0, $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
        }
    }, AltitudeMeters, PosX, PosZ, PitchDeg, SurfaceSlopeDeg, CurrentFPS, CurrentMode, DeltaHMeters, ProbeStatus, GameMode, SpeedKmh, ThrottlePct);
#else
    DrawRectangle(20, 20, 320, 268, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawRectangleLines(20, 20, 320, 268, Fade(Color{ 0, 240, 255, 255 }, 0.4f));

    DrawText("OPEN-WORLD TELEMETRY", 35, 30, 14, Color{ 0, 240, 255, 255 });

    const std::string ModeText = std::string("Mode: ") + GetGameModeName(GGameMode) + "  [1/2/3]";
    DrawText(ModeText.c_str(), 35, 52, 13, RAYWHITE);

    const std::string AltText = "Altitude: " + std::to_string(AltitudeMeters) + " m";
    DrawText(AltText.c_str(), 35, 74, 13, RAYWHITE);

    const std::string PosText = "Position: X=" + std::to_string(PosX) + " Z=" + std::to_string(PosZ);
    DrawText(PosText.c_str(), 35, 96, 13, LIGHTGRAY);

    const std::string SlopeText = "Ground Slope: " + std::to_string(SurfaceSlopeDeg) + " deg";
    DrawText(SlopeText.c_str(), 35, 118, 13, LIGHTGRAY);

    if (GGameMode == EGameMode::Plane)
    {
        const std::string SpeedText = "Airspeed: " + std::to_string(SpeedKmh) + " km/h  THR " + std::to_string(ThrottlePct) + "%";
        DrawText(SpeedText.c_str(), 35, 140, 13, Color{ 255, 200, 50, 255 });
    }
    else
    {
        const char* ModeName = (CurrentMode == 0) ? "MODE: OPTICAL RGB" : (CurrentMode == 1 ? "MODE: HILLSHADE" : "MODE: WIREFRAME");
        DrawText(ModeName, 35, 140, 13, (CurrentMode == 0) ? Color{ 0, 240, 255, 255 } : Color{ 255, 200, 50, 255 });
    }

    std::string ProbeText = (ProbeStatus == 2) ? ("Probe Delta H: " + std::to_string(DeltaHMeters) + " m") :
                            ((ProbeStatus == 1) ? "Probe: Set Target Point" : "Probe: Press P to mark point");
    DrawText(ProbeText.c_str(), 35, 162, 13, Color{ 255, 220, 0, 255 });

    DrawText(TextFormat("FPS: %i", CurrentFPS), 35, 186, 13, Color{ 0, 230, 118, 255 });

    const char* HelpText = nullptr;
    if (GGameMode == EGameMode::Plane)      HelpText = "Plane: W/S=Throttle Space/C=Boost/Brake A/D=Bank Mouse=Pitch R=Respawn";
    else if (GGameMode == EGameMode::FPS)   HelpText = "FPS: WASD=Walk Space=Jump Shift=Sprint Mouse=Look R=Respawn";
    else                                    HelpText = "Fly: WASD=Fly Space/C=Alt P=Measure T=Texture X=Wireframe";
    DrawText(HelpText, 35, 210, 12, GRAY);
    DrawText("Keys: 1=Fly 2=Plane 3=FPS V=Cycle", 35, 232, 12, GRAY);
    DrawText("R=Reset mode   P=Measure dH   T=Texture   X=Wireframe", 35, 254, 12, GRAY);

    DrawRectangle(20, GScreenHeight - 40, 560, 22, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawText("DepthWizard Open World — island DSM + arcade plane + first-person walker", 30, GScreenHeight - 34, 11, GRAY);
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
    InitWindow(GScreenWidth, GScreenHeight, "DepthWizard - Open World Flythrough (ISRO SIH26175)");
    SetTargetFPS(60);

    // World scale is kilometers: default raylib clip planes (~0.01/1000)
    // would slice the far sea and sky dome. Near 1.0 / far 6000 keeps the
    // 8km sea + sky inside while cutting depth ratio 90k -> 6k, so the
    // waterline feather slope no longer shimmers (16-bit WebGL depth).
    rlSetClipPlanes(1.0, 6000.0);

    GCamera.Reset();
    GPlane.BuildModels();
    GSky.Build();
    GWorld.Build();
    GClouds.Build(GScreenWidth, GScreenHeight);
    GTerrain.Load(std::string_view(GMeshPath));
    GWorld.Rebuild(GTerrain.bIsLoaded ? &GTerrain : nullptr);
    GPlane.Spawn(GTerrain.bIsLoaded ? &GTerrain : nullptr);
    GWalker.Spawn(GTerrain.bIsLoaded ? &GTerrain : nullptr, 0.0f, 60.0f);

#ifdef PLATFORM_WEB
    emscripten_set_main_loop(UpdateDrawFrame, 0, 1);
#else
    while (!WindowShouldClose())
    {
        UpdateDrawFrame();
    }
    GPlane.UnloadModels();
    GSky.Unload();
    GClouds.Unload();
    GWorld.Unload();
    GTerrain.Unload();
    CloseWindow();
#endif

    return 0;
}
