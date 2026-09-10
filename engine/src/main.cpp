#include "raylib.h"
#include "camera.h"
#include "terrain.h"
#include <string>

#ifdef PLATFORM_WEB
    #include <emscripten/emscripten.h>
#endif

// Global application state
static FreeFlyCamera gCamera;
static TerrainRenderer gTerrain;
static int gScreenWidth = 1280;
static int gScreenHeight = 720;
static std::string gMeshPath = "data/outputs/sample_terrain.glb";

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
    ClearBackground(Color{ 7, 9, 14, 255 });

    BeginMode3D(gCamera.camera);
        // Draw terrain mesh
        if (gTerrain.isLoaded) {
            gTerrain.Draw();
        } else {
            // Draw grid plane placeholder
            DrawGrid(40, 2.5f);
        }
    EndMode3D();

    // Telemetry HUD Overlay
    DrawRectangle(20, 20, 280, 160, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawRectangleLines(20, 20, 280, 160, Fade(Color{ 0, 240, 255, 255 }, 0.4f));

    DrawText("FLYTHROUGH TELEMETRY", 35, 32, 14, Color{ 0, 240, 255, 255 });
    
    std::string altText = "Altitude: " + std::to_string((int)(gCamera.camera.position.y * 10.0f)) + " m";
    DrawText(altText.c_str(), 35, 56, 13, RAYWHITE);

    std::string posText = "Position: X=" + std::to_string((int)gCamera.camera.position.x) + " Z=" + std::to_string((int)gCamera.camera.position.z);
    DrawText(posText.c_str(), 35, 78, 13, LIGHTGRAY);

    std::string slopeText = "Pitch: " + std::to_string((int)(fabs(gCamera.pitch) * (180.0f / 3.1415f))) + " deg";
    DrawText(slopeText.c_str(), 35, 100, 13, LIGHTGRAY);

    DrawText(TextFormat("FPS: %i", GetFPS()), 35, 124, 13, Color{ 0, 230, 118, 255 });

    // Controls reminder
    DrawRectangle(20, gScreenHeight - 65, 380, 45, Fade(Color{ 10, 14, 24, 255 }, 0.85f));
    DrawText("Controls: WASD=Fly | Space/C=Climb/Descend | X=Wireframe", 30, gScreenHeight - 52, 11, GRAY);

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
