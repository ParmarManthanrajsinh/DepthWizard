#pragma once

#include "raylib.h"
#include <string_view>
#include <cstdint>

enum class ETerrainRenderMode : int32_t
{
    OpticalRGB = 0,
    Hillshade  = 1,
    Wireframe  = 2
};

/**
 * Procedural and glTF terrain mesh renderer with directional hillshade & optical texture shader.
 * Follows Unreal Engine naming standards and conventions.
 */
class FTerrainRenderer
{
public:
    Model TerrainModel;
    Shader TerrainShader;
    bool bIsLoaded;
    ETerrainRenderMode RenderMode;
    int32_t RenderModeLoc;

    FTerrainRenderer();
    ~FTerrainRenderer();

    /**
     * Loads a 3D terrain model (glTF/GLB) from the specified path.
     * 
     * @param InFilePath Virtual or physical filesystem path to the model file.
     * @return True if model loaded successfully with valid mesh count.
     */
    bool Load(std::string_view InFilePath);

    /**
     * Renders the terrain mesh with current optical RGB, hillshade, or wireframe mode.
     */
    void Draw();

    /**
     * Releases GPU buffers and shader programs.
     */
    void Unload();

    /**
     * Cycles between Optical RGB and Hillshade shading modes.
     */
    void CycleRenderMode();

    /**
     * Toggles wireframe rendering mode on/off.
     */
    void ToggleWireframe();

    /**
     * Sets specific render mode (0=OpticalRGB, 1=Hillshade, 2=Wireframe).
     */
    void SetRenderMode(int32_t InMode);

    /**
     * Casts a ray against the terrain mesh to detect hit point and surface normal.
     * 
     * @param InRay World-space ray origin and direction.
     * @param OutHitPoint Intersected surface point in world coordinates.
     * @param OutHitNormal Intersected surface normal vector.
     * @return True if ray intersects the terrain geometry.
     */
    bool Raycast(Ray InRay, Vector3& OutHitPoint, Vector3& OutHitNormal);
};
