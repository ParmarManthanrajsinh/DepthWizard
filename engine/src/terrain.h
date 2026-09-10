#pragma once

#include "raylib.h"
#include <string_view>

/**
 * Procedural and glTF terrain mesh renderer with directional hillshade shader.
 * Follows Unreal Engine naming standards and conventions.
 */
class FTerrainRenderer
{
public:
    Model TerrainModel;
    Shader HillshadeShader;
    bool bIsLoaded;
    bool bWireframeMode;

    FTerrainRenderer();
    ~FTerrainRenderer();

    /**
     * Loads a 3D terrain model (glTF/GLB/OBJ) from the specified path.
     * 
     * @param InFilePath Virtual or physical filesystem path to the model file.
     * @return True if model loaded successfully with valid mesh count.
     */
    bool Load(std::string_view InFilePath);

    /**
     * Renders the terrain mesh with current shading or wireframe mode.
     */
    void Draw();

    /**
     * Releases GPU buffers and shader programs.
     */
    void Unload();

    /**
     * Computes scaled elevation in meters at the given world position.
     * 
     * @param InPosition Camera or sample world position.
     * @return Scaled elevation in meters.
     */
    float GetElevationAt(const Vector3& InPosition) const;

    /**
     * Toggles wireframe rendering mode.
     */
    void ToggleWireframe();
};
