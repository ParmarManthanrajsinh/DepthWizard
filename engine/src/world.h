#pragma once

#include "raylib.h"
#include "terrain.h"

/**
 * Open-world dressing around the real DSM tile.
 * Sky dome, Gerstner swell water, and procedural atmosphere.
 */
class FWorldDressing
{
public:
    static constexpr float kWaterLevelY = 1.5f;
    static constexpr float kSeabedLevelY = -5.5f;
    static constexpr float kWorldRadius = 4000.0f;
    static constexpr float kFogStart = 350.0f;
    static constexpr float kFogEnd = 1600.0f;

    /** Tonemapped midday horizon haze; doubles as clear color and fog color. */
    static constexpr Color kHazeColor = { 186, 216, 238, 255 };

    FWorldDressing();
    ~FWorldDressing();

    /** Builds water model and shader. */
    void Build();
    /** Releases GPU buffers. */
    void Unload();

    /** Kept as a hook for terrain reloads. */
    void Rebuild(const FTerrainRenderer* InTerrain);

    /** Advances water wave animation. */
    void Update(float InDeltaTime);

    /** Draws seabed then transparent water with whitecap foam. */
    void Draw(const Vector3& InCameraPos) const;

    /** Soft-clamps a position into the playable world cylinder. */
    static bool ClampToWorld(Vector3& InOutPos);

private:
    float Time;
    Model WaterModel;
    Shader WaterShader;
    Model SeabedModel;
    Shader SeabedShader;
    int32_t SunDirLoc;
    int32_t CamPosLoc;
    int32_t TimeLoc;
    int32_t HazeColorLoc;
    int32_t FogStartLoc;
    int32_t FogEndLoc;
    int32_t SkyTopLoc;
    int32_t SkyHorizonLoc;
    int32_t DeepColorLoc;
    int32_t ShallowColorLoc;
    int32_t SeabedCamPosLoc;
    int32_t SeabedTimeLoc;
    int32_t SeabedFogStartLoc;
    int32_t SeabedFogEndLoc;
    int32_t SeabedHazeColorLoc;
    bool bReady;
    bool bSeabedReady;
};
