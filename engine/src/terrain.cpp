#include "terrain.h"
#include <iostream>

TerrainRenderer::TerrainRenderer() : isLoaded(false), wireframe(false) {
    model = { 0 };
}

TerrainRenderer::~TerrainRenderer() {
    Unload();
}

bool TerrainRenderer::Load(const std::string& filepath) {
    Unload();
    if (FileExists(filepath.c_str())) {
        model = LoadModel(filepath.c_str());
        isLoaded = (model.meshCount > 0);
        return isLoaded;
    }
    return false;
}

void TerrainRenderer::Unload() {
    if (isLoaded) {
        UnloadModel(model);
        isLoaded = false;
    }
}

void TerrainRenderer::Draw() {
    if (!isLoaded) return;
    
    Vector3 position = { 0.0f, 0.0f, 0.0f };
    if (wireframe) {
        DrawModelWires(model, position, 1.0f, DARKBLUE);
    } else {
        DrawModel(model, position, 1.0f, WHITE);
    }
}

float TerrainRenderer::GetElevationAt(Vector3 position) {
    // Basic approximate elevation query (extensible with ray-mesh intersection)
    return position.y * 10.0f;
}
