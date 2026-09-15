#include "world.h"
#include "rlgl.h"
#include "raymath.h"
#include <cmath>
#include <cstdint>

#if defined(PLATFORM_WEB)
#include "shaders_gen/water_web_vs.h"

#include "shaders_gen/water_web_fs.h"

#include "shaders_gen/seabed_web_vs.h"

#include "shaders_gen/seabed_web_fs.h"
#else
#include "shaders_gen/water_desktop_vs.h"

#include "shaders_gen/water_desktop_fs.h"

#include "shaders_gen/seabed_desktop_vs.h"

#include "shaders_gen/seabed_desktop_fs.h"
#endif

FWorldDressing::FWorldDressing()
    : Time(0.0f)
    , WaterLevelY(kWaterLevelY)
    , SeabedLevelY(kSeabedLevelY)
    , WaterModel({ 0 })
    , WaterShader({ 0 })
    , SeabedModel({ 0 })
    , SeabedShader({ 0 })
    , SunDirLoc(-1)
    , CamPosLoc(-1)
    , TimeLoc(-1)
    , HazeColorLoc(-1)
    , FogStartLoc(-1)
    , FogEndLoc(-1)
    , SkyTopLoc(-1)
    , SkyHorizonLoc(-1)
    , DeepColorLoc(-1)
    , ShallowColorLoc(-1)
    , SeabedCamPosLoc(-1)
    , SeabedTimeLoc(-1)
    , SeabedFogStartLoc(-1)
    , SeabedFogEndLoc(-1)
    , SeabedHazeColorLoc(-1)
    , bReady(false)
    , bSeabedReady(false)
{
}

FWorldDressing::~FWorldDressing()
{
    Unload();
}

static void SetVec3(Shader InShader, int32_t InLoc, float InX, float InY, float InZ)
{
    if (InLoc >= 0)
    {
        const float V[3] = { InX, InY, InZ };
        SetShaderValue(InShader, InLoc, V, SHADER_UNIFORM_VEC3);
    }
}

static void SetFloat(Shader InShader, int32_t InLoc, float InValue)
{
    if (InLoc >= 0)
    {
        SetShaderValue(InShader, InLoc, &InValue, SHADER_UNIFORM_FLOAT);
    }
}

void FWorldDressing::BuildPlanes()
{
    // (Re)build the water + seabed planes at the current adaptive levels.
    // Vertex Y is baked so vertexPosition == world position in-shader.
    if (WaterModel.meshCount > 0)
    {
        UnloadModel(WaterModel);
        WaterModel = { 0 };
    }
    if (SeabedModel.meshCount > 0)
    {
        UnloadModel(SeabedModel);
        SeabedModel = { 0 };
    }
    // NOTE: raylib Mesh uses 16-bit indices (max 65535). 255 segments =
    // 256^2 = 65536 verts, the largest watertight grid that fits.
    Mesh PlaneMesh = GenMeshPlane(kWorldRadius * 2.0f, kWorldRadius * 2.0f, 255, 255);
    for (int32_t Index = 0; Index < PlaneMesh.vertexCount; ++Index)
    {
        PlaneMesh.vertices[Index * 3 + 1] += WaterLevelY;
    }
    WaterModel = LoadModelFromMesh(PlaneMesh);

    // Sandy seabed bottom layer, visible through the transparent water.
    Mesh SeabedMesh = GenMeshPlane(kWorldRadius * 2.0f, kWorldRadius * 2.0f, 128, 128);
    for (int32_t Index = 0; Index < SeabedMesh.vertexCount; ++Index)
    {
        SeabedMesh.vertices[Index * 3 + 1] += SeabedLevelY;
    }
    SeabedModel = LoadModelFromMesh(SeabedMesh);

    // Re-attach already-compiled shaders to the rebuilt models.
    if (WaterShader.id > 0)
    {
        for (int i = 0; i < WaterModel.materialCount; ++i)
        {
            WaterModel.materials[i].shader = WaterShader;
        }
    }
    if (SeabedShader.id > 0)
    {
        for (int i = 0; i < SeabedModel.materialCount; ++i)
        {
            SeabedModel.materials[i].shader = SeabedShader;
        }
    }
}

void FWorldDressing::Build()
{
    if (bReady && bSeabedReady) return;
    BuildPlanes();
    if (!bReady)
    {
        WaterShader = LoadShaderFromMemory(kWaterVS, kWaterFS);
    }

    if (!bSeabedReady)
    {
        SeabedShader = LoadShaderFromMemory(kSeabedVS, kSeabedFS);
    }

    // Horizon-matched haze (same as sky horizon) so the far sea edge
    // melts seamlessly into the sky (shared by water + seabed).
    const float WaterHaze[3] = { 0.68f, 0.82f, 0.94f };

    if (!bReady && WaterModel.meshCount > 0 && WaterShader.id > 0)
    {
        for (int i = 0; i < WaterModel.materialCount; ++i)
        {
            WaterModel.materials[i].shader = WaterShader;
        }
        SunDirLoc = GetShaderLocation(WaterShader, "uSunDir");
        CamPosLoc = GetShaderLocation(WaterShader, "uCamPos");
        TimeLoc = GetShaderLocation(WaterShader, "uTime");
        SkyTopLoc = GetShaderLocation(WaterShader, "uSkyTop");
        SkyHorizonLoc = GetShaderLocation(WaterShader, "uSkyHorizon");
        DeepColorLoc = GetShaderLocation(WaterShader, "uDeepColor");
        ShallowColorLoc = GetShaderLocation(WaterShader, "uShallowColor");
        HazeColorLoc = GetShaderLocation(WaterShader, "uHazeColor");
        FogStartLoc = GetShaderLocation(WaterShader, "uFogStart");
        FogEndLoc = GetShaderLocation(WaterShader, "uFogEnd");

        // Scene sun/sky match (same light dir as the terrain shader).
        SetVec3(WaterShader, SunDirLoc, 0.55f, 0.75f, 0.35f);
        SetVec3(WaterShader, SkyTopLoc, 0.10f, 0.38f, 0.88f);
        SetVec3(WaterShader, SkyHorizonLoc, 0.68f, 0.82f, 0.94f);
        // Vivid deep ocean navy + rich tropical turquoise shallows
        SetVec3(WaterShader, DeepColorLoc, 0.02f, 0.12f, 0.28f);
        SetVec3(WaterShader, ShallowColorLoc, 0.25f, 0.65f, 0.75f);
        // Water fog melts the far edge fully into the horizon haze.
        SetFloat(WaterShader, FogStartLoc, 900.0f);
        SetFloat(WaterShader, FogEndLoc, 4200.0f);
        if (HazeColorLoc >= 0) SetShaderValue(WaterShader, HazeColorLoc, WaterHaze, SHADER_UNIFORM_VEC3);

        bReady = true;
        TraceLog(LOG_INFO, "[Water] surface live (shader id=%d)", WaterShader.id);
    }
    else
    {
        TraceLog(LOG_WARNING, "[Water] surface FAILED (meshes=%d shader id=%d)",
                 WaterModel.meshCount, WaterShader.id);
    }

    // Seabed is independent: it must never take the water surface down with it.
    if (!bSeabedReady && SeabedModel.meshCount > 0 && SeabedShader.id > 0)
    {
        for (int i = 0; i < SeabedModel.materialCount; ++i)
        {
            SeabedModel.materials[i].shader = SeabedShader;
        }

        // Seabed shares sun-independent lighting; fog matches the water.
        SeabedCamPosLoc = GetShaderLocation(SeabedShader, "uCamPos");
        SeabedTimeLoc = GetShaderLocation(SeabedShader, "uTime");
        SeabedFogStartLoc = GetShaderLocation(SeabedShader, "uFogStart");
        SeabedFogEndLoc = GetShaderLocation(SeabedShader, "uFogEnd");
        SeabedHazeColorLoc = GetShaderLocation(SeabedShader, "uHazeColor");
        SetFloat(SeabedShader, SeabedFogStartLoc, 900.0f);
        SetFloat(SeabedShader, SeabedFogEndLoc, 4200.0f);
        if (SeabedHazeColorLoc >= 0) SetShaderValue(SeabedShader, SeabedHazeColorLoc, WaterHaze, SHADER_UNIFORM_VEC3);

        bSeabedReady = true;
        TraceLog(LOG_INFO, "[Water] seabed live (shader id=%d)", SeabedShader.id);
    }
    else
    {
        TraceLog(LOG_WARNING, "[Water] seabed FAILED (meshes=%d shader id=%d)",
                 SeabedModel.meshCount, SeabedShader.id);
    }

    if (bReady || bSeabedReady)
    {
        TraceLog(LOG_INFO, "[Water] WebGL2/ES ocean water shader live");
    }
}

void FWorldDressing::Unload()
{
    if (bReady)
    {
        UnloadModel(WaterModel);
        UnloadShader(WaterShader);
        WaterModel = { 0 };
        WaterShader = { 0 };
        bReady = false;
    }
    if (bSeabedReady)
    {
        UnloadModel(SeabedModel);
        UnloadShader(SeabedShader);
        SeabedModel = { 0 };
        SeabedShader = { 0 };
        bSeabedReady = false;
    }
}

void FWorldDressing::Rebuild(const FTerrainRenderer* InTerrain)
{
    if (!bReady || !bSeabedReady)
    {
        Build();
    }
    // Adaptive sea level: float the sea just below the cached lowland p10
    // so legacy flat/renormalized meshes are not broadly submerged, while
    // new beach-lifted tiles keep the default level.
    float TargetWater = kWaterLevelY;
    float LowP10 = 0.0f;
    if (InTerrain != nullptr && InTerrain->GetLowlandP10(LowP10))
    {
        // 0.4m freeboard below lowland; never above default, never so low
        // the beach intersection (rim -1.0) disappears entirely.
        TargetWater = LowP10 - 0.4f;
        if (TargetWater > kWaterLevelY) TargetWater = kWaterLevelY;
        if (TargetWater < -0.7f) TargetWater = -0.7f;
    }

    if (fabsf(TargetWater - WaterLevelY) > 0.01f)
    {
        WaterLevelY = TargetWater;
        SeabedLevelY = WaterLevelY - 7.0f;
        BuildPlanes();
        TraceLog(LOG_INFO, "[Water] adaptive level: water=%.2f seabed=%.2f",
                 WaterLevelY, SeabedLevelY);
    }
    Time = 0.0f;
}

void FWorldDressing::Update(float InDeltaTime)
{
    Time += InDeltaTime;
}

void FWorldDressing::Draw(const Vector3& InCameraPos) const
{
    if (bSeabedReady)
    {
        SetFloat(SeabedShader, SeabedTimeLoc, Time);
        if (SeabedCamPosLoc >= 0) SetShaderValue(SeabedShader, SeabedCamPosLoc, &InCameraPos, SHADER_UNIFORM_VEC3);

        // Opaque sandy bottom first so the transparent surface has depth behind it.
        // No depth writes: with a 16-bit depth buffer the 7 m water/seabed gap
        // quantizes to the same depth at flight distances, which z-fights sand
        // on top of the sea. Draw order alone decides seabed-vs-water layering;
        // depth testing against terrain still works.
        rlDisableDepthMask();
        DrawModel(SeabedModel, Vector3{ 0.0f, 0.0f, 0.0f }, 1.0f, WHITE);
        rlEnableDepthMask();
    }

    if (!bReady)
    {
        return;
    }

    SetFloat(WaterShader, TimeLoc, Time);
    if (CamPosLoc >= 0) SetShaderValue(WaterShader, CamPosLoc, &InCameraPos, SHADER_UNIFORM_VEC3);

    // Transparent sea surface: blend over the seabed, depth write off but
    // depth test on so island terrain still occludes the water correctly.
    BeginBlendMode(BLEND_ALPHA);
    rlDisableDepthMask();
    DrawModel(WaterModel, Vector3{ 0.0f, 0.0f, 0.0f }, 1.0f, WHITE);
    rlEnableDepthMask();
    EndBlendMode();
}

bool FWorldDressing::ClampToWorld(Vector3& InOutPos)
{
    const float DistSq = InOutPos.x * InOutPos.x + InOutPos.z * InOutPos.z;
    const float MaxDist = kWorldRadius * 0.92f;
    if (DistSq > MaxDist * MaxDist)
    {
        const float Dist = sqrtf(DistSq);
        InOutPos.x = (InOutPos.x / Dist) * MaxDist;
        InOutPos.z = (InOutPos.z / Dist) * MaxDist;
        return true;
    }
    return false;
}
