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
    float TerrainMinY;
    float TerrainMaxY;
    float TerrainLowP10;
    ETerrainRenderMode RenderMode;
    int32_t RenderModeLoc;
    int32_t CamPosLoc;
    int32_t FogStartLoc;
    int32_t FogEndLoc;
    int32_t HazeColorLoc;
    int32_t PlainWhiteLoc;

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
     * Updates the per-frame camera position for distance fog.
     * Fog range/haze are configured once at load from FWorldDressing.
     */
    void UpdateFog(const Vector3& InCameraPos);

    /**
     * Casts a ray against the terrain mesh to detect hit point and surface normal.
     *
     * @param InRay World-space ray origin and direction.
     * @param OutHitPoint Intersected surface point in world coordinates.
     * @param OutHitNormal Intersected surface normal vector.
     * @return True if ray intersects the terrain geometry.
     */
    bool Raycast(Ray InRay, Vector3& OutHitPoint, Vector3& OutHitNormal);

    /**
     * Samples the terrain surface height at a world XZ position.
     *
     * @param InX World X coordinate.
     * @param InZ World Z coordinate.
     * @param OutHeightY Terrain surface Y at the position.
     * @return True if the terrain was hit, false if the position is off-mesh.
     */
    bool GetHeightAt(float InX, float InZ, float& OutHeightY) const;

    /**
     * Samples terrain height, returning a fallback when off-mesh (open water).
     */
    float GetGroundHeightOr(float InX, float InZ, float InFallbackY) const;

    /**
     * 10th percentile of interior (|x|,|z| <= 240) vertex heights, cached at
     * load. The ocean floats the sea just below it so legacy flat meshes do
     * not render broadly submerged. False when nothing is loaded.
     */
    bool GetLowlandP10(float& OutP10) const
    {
        if (!bIsLoaded) return false;
        OutP10 = TerrainLowP10;
        return true;
    }
};
