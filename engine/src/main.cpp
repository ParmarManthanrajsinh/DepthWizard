#include "raylib.h"
#include "camera.h"
#include "terrain.h"
#include <string>
#include <cmath>

#ifdef PLATFORM_WEB
    #include <emscripten/emscripten.h>
#endif

// Global application state
static FreeFlyCamera gCamera;
static TerrainRenderer gTerrain;
static int gScreenWidth = 1280;
static int gScreenHeight = 720;
static std::string gMeshPath = "data/outputs/sample_terrain.glb";

extern "C" {
#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int LoadTerrainFromMemory(const char* filepath) {
        if (!filepath) return 0;
        bool ok = gTerrain.Load(filepath);
        if (ok) {
            gCamera.Init(Vector3{ 0.0f, 45.0f, 85.0f }, Vector3{ 0.0f, 20.0f, 0.0f });
        }
        return ok ? 1 : 0;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ToggleWireframe() {
        gTerrain.wireframe = !gTerrain.wireframe;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    void ResetCamera() {
        gCamera.Init(Vector3{ 0.0f, 45.0f, 85.0f }, Vector3{ 0.0f, 20.0f, 0.0f });
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraAlt() {
        return gCamera.camera.position.y * 10.0f;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraPosX() {
        return gCamera.camera.position.x;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraPosZ() {
        return gCamera.camera.position.z;
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    float GetCameraPitch() {
        return fabsf(gCamera.pitch) * (180.0f / 3.14159265f);
    }

#ifdef PLATFORM_WEB
    EMSCRIPTEN_KEEPALIVE
#endif
    int GetEngineFPS() {
        return GetFPS();
    }
}

void UpdateDrawFrame() {
    float dt = GetFrameTime();

    // Toggle wireframe mode
    if (IsKeyPressed(KEY_X)) {
        gTerrain.wireframe = !gTerrain.wireframe;
    }

    // Update free-fly camera
    gCamera.Update(dt);

    // Draw
    BeginDrawing();
    ClearBackground(Color{ 10, 12, 16, 255 });

    BeginMode3D(gCamera.camera);
        // Always draw spatial reference grid beneath terrain
        DrawGrid(60, 4.0f);

        // Draw terrain mesh
        if (gTerrain.isLoaded) {
            gTerrain.Draw();
        }
    EndMode3D();

    int alt = (int)(gCamera.camera.position.y * 10.0f);
    int posX = (int)gCamera.camera.position.x;
    int posZ = (int)gCamera.camera.position.z;
    int pitchDeg = (int)(fabsf(gCamera.pitch) * (180.0f / 3.14159265f));
    int fps = GetFPS();

#ifdef PLATFORM_WEB
    // Push live telemetry directly to HTML HUD
    EM_ASM({
        if (window.updateWasmHUD) {
            window.updateWasmHUD($0, $1, $2, $3, $4);
        }
    }, alt, posX, posZ, pitchDeg, fps);
#else
    // Desktop Raylib Overlay
    DrawRectangle(20, 20, 280, 160, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawRectangleLines(20, 20, 280, 160, Fade(Color{ 0, 240, 255, 255 }, 0.4f));

    DrawText("FLYTHROUGH TELEMETRY", 35, 32, 14, Color{ 0, 240, 255, 255 });
    
    std::string altText = "Altitude: " + std::to_string(alt) + " m";
    DrawText(altText.c_str(), 35, 56, 13, RAYWHITE);

    std::string posText = "Position: X=" + std::to_string(posX) + " Z=" + std::to_string(posZ);
    DrawText(posText.c_str(), 35, 78, 13, LIGHTGRAY);

    std::string slopeText = "Pitch: " + std::to_string(pitchDeg) + " deg";
    DrawText(slopeText.c_str(), 35, 100, 13, LIGHTGRAY);

    DrawText(TextFormat("FPS: %i", fps), 35, 124, 13, Color{ 0, 230, 118, 255 });

    DrawRectangle(20, gScreenHeight - 65, 380, 45, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawText("Controls: WASD=Fly | Space/C=Climb/Descend | X=Wireframe", 30, gScreenHeight - 52, 11, GRAY);
#endif

    EndDrawing();
}

int main(int argc, char* argv[]) {
    // Check if mesh path passed in args
    if (argc > 1) {
        gMeshPath = argv[1];
    }

    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_WINDOW_RESIZABLE);
    InitWindow(gScreenWidth, gScreenHeight, "DepthWizard - 3D Terrain Flythrough (ISRO SIH26175)");
    SetTargetFPS(60);

    // Initialize camera starting above terrain
    gCamera.Init(Vector3{ 0.0f, 45.0f, 85.0f }, Vector3{ 0.0f, 20.0f, 0.0f });

    // Try loading mesh
    gTerrain.Load(gMeshPath);

#ifdef PLATFORM_WEB
    emscripten_set_main_loop(UpdateDrawFrame, 0, 1);
#else
    while (!WindowShouldClose()) {
        UpdateDrawFrame();
    }
    gTerrain.Unload();
    CloseWindow();
#endif

    return 0;
}

