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
    static constexpr float kDefaultWaterLevelY = 1.5f;
    static constexpr float kDefaultSeabedLevelY = -5.5f;
    // Kept for backward compatibility (fallback ground height, tests).
    static constexpr float kWaterLevelY = kDefaultWaterLevelY;
    static constexpr float kSeabedLevelY = kDefaultSeabedLevelY;
    static constexpr float kWorldRadius = 4000.0f;
    static constexpr float kFogStart = 350.0f;
    static constexpr float kFogEnd = 1600.0f;
    /** Half extent of the terrain tile the square-coast shader aligns to. */
    static constexpr float kIslandHalfExtent = 300.0f;
    /** Max Gerstner swell amplitude baked into the water vertex shader. */
    static constexpr float kWaveAmplitude = 0.13f;

    /** Tonemapped midday horizon haze; doubles as clear color and fog color. */
    static constexpr Color kHazeColor = { 186, 216, 238, 255 };

    FWorldDressing();
    ~FWorldDressing();

    /** Builds water model and shader. */
    void Build();
    /** Releases GPU buffers. */
    void Unload();

    /** Adapts the sea to a newly loaded tile, then keeps animating. */
    void Rebuild(const FTerrainRenderer* InTerrain);

    /** Current adaptive levels (default until Rebuild adapts them). */
    float GetWaterLevel() const { return WaterLevelY; }
    float GetSeabedLevel() const { return SeabedLevelY; }

    /** Advances water wave animation. */
    void Update(float InDeltaTime);

    /** Draws seabed then transparent water with whitecap foam. */
    void Draw(const Vector3& InCameraPos) const;

    /** Soft-clamps a position into the playable world cylinder. */
    static bool ClampToWorld(Vector3& InOutPos);

private:
    float Time;
    float WaterLevelY;
    float SeabedLevelY;
    void BuildPlanes();
    void ApplyWaterLevel();
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
