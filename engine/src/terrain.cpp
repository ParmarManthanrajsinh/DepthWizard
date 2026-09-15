#include "terrain.h"
#include "world.h"
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>
#include <cstdint>

// Manual override: set to true to force plain-white terrain (ignores the
// embedded optical texture). Default false: the optical texture is used
// whenever the GLB provides one (auto-detected in Load()).
static constexpr bool kForceWhiteAlbedo = false;

#if defined(PLATFORM_WEB)
#include "shaders_gen/terrain_web_vs.h"
#else
#include "shaders_gen/terrain_desktop_vs.h"
#endif

#if defined(PLATFORM_WEB)
#include "shaders_gen/terrain_web_fs.h"
#else
#include "shaders_gen/terrain_desktop_fs.h"
#endif

FTerrainRenderer::FTerrainRenderer()
    : TerrainModel({ 0 })
    , TerrainShader({ 0 })
    , bIsLoaded(false)
    , TerrainMinY(0.0f)
    , TerrainMaxY(0.0f)
    , TerrainLowP10(0.0f)
    , RenderMode(ETerrainRenderMode::OpticalRGB)
    , RenderModeLoc(-1)
    , CamPosLoc(-1)
    , FogStartLoc(-1)
    , FogEndLoc(-1)
    , HazeColorLoc(-1)
    , PlainWhiteLoc(-1)
{
}

FTerrainRenderer::~FTerrainRenderer()
{
    Unload();
}

bool FTerrainRenderer::Load(std::string_view InFilePath)
{
    Unload();
    if (InFilePath.empty())
    {
        return false;
    }

    const std::string PathString(InFilePath);
    if (FileExists(PathString.c_str()))
    {
        TerrainModel = LoadModel(PathString.c_str());
        bIsLoaded = (TerrainModel.meshCount > 0);
        if (bIsLoaded)
        {
            // Cache vertex Y bounds + interior lowland p10 for adaptive sea level.
            bool bFirst = true;
            float MinY = 0.0f, MaxY = 0.0f;
            std::vector<float> InteriorY;
            for (int32_t MeshIdx = 0; MeshIdx < TerrainModel.meshCount; ++MeshIdx)
            {
                const Mesh& M = TerrainModel.meshes[MeshIdx];
                for (int32_t V = 0; V < M.vertexCount; ++V)
                {
                    const float X = M.vertices[V * 3];
                    const float Y = M.vertices[V * 3 + 1];
                    const float Z = M.vertices[V * 3 + 2];
                    if (bFirst) { MinY = MaxY = Y; bFirst = false; }
                    else { if (Y < MinY) MinY = Y; if (Y > MaxY) MaxY = Y; }
                    if (fabsf(X) <= 240.0f && fabsf(Z) <= 240.0f) InteriorY.push_back(Y);
                }
            }
            TerrainMinY = MinY;
            TerrainMaxY = MaxY;
            if (!InteriorY.empty())
            {
                std::nth_element(InteriorY.begin(), InteriorY.begin() + InteriorY.size() / 10, InteriorY.end());
                TerrainLowP10 = InteriorY[InteriorY.size() / 10];
            }
            TraceLog(LOG_INFO, "[Terrain] Y range: min=%.2f max=%.2f lowP10=%.2f", TerrainMinY, TerrainMaxY, TerrainLowP10);

            int texID = 0;
            if (TerrainModel.materialCount > 0)
            {
                texID = TerrainModel.materials[0].maps[MATERIAL_MAP_ALBEDO].texture.id;
            }
            TraceLog(LOG_WARNING, "[Terrain] MeshCount=%d, MatCount=%d, TexID=%d",
                     TerrainModel.meshCount, TerrainModel.materialCount, texID);

            if (TerrainShader.id == 0)
            {
                TerrainShader = LoadShaderFromMemory(kTerrainVS, kTerrainFS);
                TerrainShader.locs[SHADER_LOC_MAP_ALBEDO] = GetShaderLocation(TerrainShader, "texture0");
                RenderModeLoc = GetShaderLocation(TerrainShader, "uRenderMode");
                PlainWhiteLoc = GetShaderLocation(TerrainShader, "uPlainWhite");
                CamPosLoc = GetShaderLocation(TerrainShader, "uCamPos");
                FogStartLoc = GetShaderLocation(TerrainShader, "uFogStart");
                FogEndLoc = GetShaderLocation(TerrainShader, "uFogEnd");
                HazeColorLoc = GetShaderLocation(TerrainShader, "uHazeColor");

                // Calm midday aerial perspective; matches FSkyDome horizon.
                const float FogStart = FWorldDressing::kFogStart;
                const float FogEnd = FWorldDressing::kFogEnd;
                const float Haze[3] = {
                    FWorldDressing::kHazeColor.r / 255.0f,
                    FWorldDressing::kHazeColor.g / 255.0f,
                    FWorldDressing::kHazeColor.b / 255.0f
                };
                if (FogStartLoc >= 0) SetShaderValue(TerrainShader, FogStartLoc, &FogStart, SHADER_UNIFORM_FLOAT);
                if (FogEndLoc >= 0) SetShaderValue(TerrainShader, FogEndLoc, &FogEnd, SHADER_UNIFORM_FLOAT);
                if (HazeColorLoc >= 0) SetShaderValue(TerrainShader, HazeColorLoc, Haze, SHADER_UNIFORM_VEC3);
            }
            if (RenderModeLoc >= 0)
            {
                int32_t ModeVal = (RenderMode == ETerrainRenderMode::OpticalRGB) ? 0 : 1;
                SetShaderValue(TerrainShader, RenderModeLoc, &ModeVal, SHADER_UNIFORM_INT);
            }
            if (PlainWhiteLoc >= 0)
            {
                // Use the embedded optical texture when the GLB provides one;
                // fall back to plain white only when no albedo texture exists.
                // (The shader additionally rejects near-black texels so broken
                // sampling can never turn the mesh black.)
                const int32_t PlainVal = (texID > 0 && !kForceWhiteAlbedo) ? 0 : 1;
                SetShaderValue(TerrainShader, PlainWhiteLoc, &PlainVal, SHADER_UNIFORM_INT);
            }
            if (TerrainShader.id > 0)
            {
                for (int32_t Index = 0; Index < TerrainModel.materialCount; ++Index)
                {
                    TerrainModel.materials[Index].shader = TerrainShader;
                }
            }
        }
        return bIsLoaded;
    }
    return false;
}

void FTerrainRenderer::Unload()
{
    if (bIsLoaded)
    {
        UnloadModel(TerrainModel);
        bIsLoaded = false;
    }
    if (TerrainShader.id > 0)
    {
        UnloadShader(TerrainShader);
        TerrainShader.id = 0;
    }
}

void FTerrainRenderer::SetRenderMode(int32_t InMode)
{
    RenderMode = static_cast<ETerrainRenderMode>(InMode);
    if (TerrainShader.id > 0 && RenderModeLoc >= 0)
    {
        int32_t ModeVal = (RenderMode == ETerrainRenderMode::OpticalRGB) ? 0 : 1;
        SetShaderValue(TerrainShader, RenderModeLoc, &ModeVal, SHADER_UNIFORM_INT);
    }
}

void FTerrainRenderer::CycleRenderMode()
{
    if (RenderMode == ETerrainRenderMode::OpticalRGB)
    {
        SetRenderMode(static_cast<int32_t>(ETerrainRenderMode::Hillshade));
    }
    else
    {
        SetRenderMode(static_cast<int32_t>(ETerrainRenderMode::OpticalRGB));
    }
}

void FTerrainRenderer::ToggleWireframe()
{
    if (RenderMode == ETerrainRenderMode::Wireframe)
    {
        SetRenderMode(static_cast<int32_t>(ETerrainRenderMode::OpticalRGB));
    }
    else
    {
        RenderMode = ETerrainRenderMode::Wireframe;
    }
}

void FTerrainRenderer::UpdateFog(const Vector3& InCameraPos)
{
    if (TerrainShader.id > 0 && CamPosLoc >= 0)
    {
        SetShaderValue(TerrainShader, CamPosLoc, &InCameraPos, SHADER_UNIFORM_VEC3);
    }
}

void FTerrainRenderer::Draw()
{
    if (!bIsLoaded)
    {
        return;
    }

    const Vector3 Position = { 0.0f, 0.0f, 0.0f };
    if (RenderMode == ETerrainRenderMode::Wireframe)
    {
        const Shader SavedShader = TerrainModel.materials[0].shader;
        const Shader DefaultShader = LoadMaterialDefault().shader;
        for (int32_t Index = 0; Index < TerrainModel.materialCount; ++Index)
        {
            TerrainModel.materials[Index].shader = DefaultShader;
        }
        DrawModelWires(TerrainModel, Position, 1.0f, Color{ 255, 51, 51, 255 });
        for (int32_t Index = 0; Index < TerrainModel.materialCount; ++Index)
        {
            TerrainModel.materials[Index].shader = SavedShader;
        }
    }
    else
    {
        DrawModel(TerrainModel, Position, 1.0f, WHITE);
    }
}

bool FTerrainRenderer::Raycast(Ray InRay, Vector3& OutHitPoint, Vector3& OutHitNormal)
{
    if (!bIsLoaded || TerrainModel.meshCount == 0)
    {
        return false;
    }

    bool bAnyHit = false;
    float ClosestDist = 1e9f;

    for (int32_t Index = 0; Index < TerrainModel.meshCount; ++Index)
    {
        const RayCollision Collision = GetRayCollisionMesh(InRay, TerrainModel.meshes[Index], TerrainModel.transform);
        if (Collision.hit && Collision.distance < ClosestDist)
        {
            ClosestDist = Collision.distance;
            OutHitPoint = Collision.point;
            OutHitNormal = Collision.normal;
            bAnyHit = true;
        }
    }

    return bAnyHit;
}

bool FTerrainRenderer::GetHeightAt(float InX, float InZ, float& OutHeightY) const
{
    if (!bIsLoaded || TerrainModel.meshCount == 0)
    {
        return false;
    }

    const Ray DownRay = { Vector3{ InX, 500.0f, InZ }, Vector3{ 0.0f, -1.0f, 0.0f } };
    bool bAnyHit = false;
    float ClosestDist = 1e9f;

    for (int32_t Index = 0; Index < TerrainModel.meshCount; ++Index)
    {
        const RayCollision Collision = GetRayCollisionMesh(DownRay, TerrainModel.meshes[Index], TerrainModel.transform);
        if (Collision.hit && Collision.distance < ClosestDist)
        {
            ClosestDist = Collision.distance;
            OutHeightY = Collision.point.y;
            bAnyHit = true;
        }
    }

    return bAnyHit;
}

float FTerrainRenderer::GetGroundHeightOr(float InX, float InZ, float InFallbackY) const
{
    float HeightY = InFallbackY;
    if (GetHeightAt(InX, InZ, HeightY))
    {
        return HeightY;
    }
    return InFallbackY;
}

