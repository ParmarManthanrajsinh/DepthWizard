#include "terrain.h"
#include <string>
#include <cstdint>

#if defined(PLATFORM_WEB)
    #define GLSL_HEADER "precision mediump float;\n"
    #define GLSL_IN     "attribute"
    #define GLSL_OUT    "varying"
#else
    #define GLSL_HEADER "#version 330\n"
    #define GLSL_IN     "in"
    #define GLSL_OUT    "out"
#endif

static const char* kTerrainVS =
    "attribute vec3 vertexPosition;\n"
    "attribute vec2 vertexTexCoord;\n"
    "attribute vec3 vertexNormal;\n"
    "attribute vec4 vertexColor;\n"
    "uniform mat4 mvp;\n"
    "varying vec2 fragTexCoord;\n"
    "varying vec4 fragColor;\n"
    "varying float fragLight;\n"
    "void main() {\n"
    "    fragTexCoord = vertexTexCoord;\n"
    "    vec3 lightDir = normalize(vec3(0.55, 0.75, 0.35));\n"
    "    vec3 norm = normalize(vertexNormal);\n"
    "    float diff = max(dot(norm, lightDir), 0.0);\n"
    "    fragLight = 0.45 + 0.55 * diff;\n"
    "    float hNorm = clamp(vertexPosition.y / 45.0, 0.0, 1.0);\n"
    "    vec3 lowColor = vec3(0.22, 0.46, 0.24);\n"
    "    vec3 midColor = vec3(0.74, 0.62, 0.38);\n"
    "    vec3 highColor = vec3(0.95, 0.96, 0.98);\n"
    "    vec3 terrainCol = (hNorm < 0.5) ? mix(lowColor, midColor, hNorm * 2.0) : mix(midColor, highColor, (hNorm - 0.5) * 2.0);\n"
    "    fragColor = vec4(terrainCol, 1.0);\n"
    "    gl_Position = mvp * vec4(vertexPosition, 1.0);\n"
    "}\n";

#if defined(PLATFORM_WEB)
static const char* kTerrainFS =
    "precision mediump float;\n"
    "varying vec2 fragTexCoord;\n"
    "varying vec4 fragColor;\n"
    "varying float fragLight;\n"
    "uniform sampler2D texture0;\n"
    "uniform vec4 colDiffuse;\n"
    "uniform int uRenderMode;\n"
    "void main() {\n"
    "    vec4 baseColor = fragColor;\n"
    "    if (uRenderMode == 0) {\n"
    "        vec4 texColor = texture2D(texture0, fragTexCoord);\n"
    "        if (texColor.a > 0.0) {\n"
    "            baseColor = texColor;\n"
    "        }\n"
    "    }\n"
    "    vec3 tint = (colDiffuse.r + colDiffuse.g + colDiffuse.b > 0.01) ? colDiffuse.rgb : vec3(1.0);\n"
    "    vec3 finalRgb = baseColor.rgb * fragLight * tint;\n"
    "    gl_FragColor = vec4(finalRgb, 1.0);\n"
    "}\n";
#else
static const char* kTerrainFS =
    "#version 330\n"
    "in vec2 fragTexCoord;\n"
    "in vec4 fragColor;\n"
    "in float fragLight;\n"
    "uniform sampler2D texture0;\n"
    "uniform vec4 colDiffuse;\n"
    "uniform int uRenderMode;\n"
    "out vec4 finalColor;\n"
    "void main() {\n"
    "    vec4 baseColor = fragColor;\n"
    "    if (uRenderMode == 0) {\n"
    "        vec4 texColor = texture(texture0, fragTexCoord);\n"
    "        if (texColor.a > 0.0) {\n"
    "            baseColor = texColor;\n"
    "        }\n"
    "    }\n"
    "    vec3 tint = (colDiffuse.r + colDiffuse.g + colDiffuse.b > 0.01) ? colDiffuse.rgb : vec3(1.0);\n"
    "    vec3 finalRgb = baseColor.rgb * fragLight * tint;\n"
    "    finalColor = vec4(finalRgb, 1.0);\n"
    "}\n";
#endif

FTerrainRenderer::FTerrainRenderer()
    : TerrainModel({ 0 })
    , TerrainShader({ 0 })
    , bIsLoaded(false)
    , RenderMode(ETerrainRenderMode::OpticalRGB)
    , RenderModeLoc(-1)
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
            }
            if (RenderModeLoc >= 0)
            {
                int32_t ModeVal = (RenderMode == ETerrainRenderMode::OpticalRGB) ? 0 : 1;
                SetShaderValue(TerrainShader, RenderModeLoc, &ModeVal, SHADER_UNIFORM_INT);
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

