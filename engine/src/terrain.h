#pragma once
#include "raylib.h"
#include <string>

class TerrainRenderer {
public:
    Model model;
    Shader hillshadeShader;
    bool isLoaded;
    bool wireframe;

    TerrainRenderer();
    ~TerrainRenderer();

    bool Load(const std::string& filepath);
    void Draw();
    void Unload();
    float GetElevationAt(Vector3 position);
};
