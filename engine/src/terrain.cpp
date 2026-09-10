#include "terrain.h"
#include <string>
#include <cstdint>

#if defined(PLATFORM_WEB)
    #define GLSL_VERSION            100
#else
    #define GLSL_VERSION            330
#endif

static const char* kTerrainVS =
#if defined(PLATFORM_WEB)
    "precision mediump float;\n"
    "attribute vec3 vertexPosition;\n"
    "attribute vec2 vertexTexCoord;\n"
    "attribute vec3 vertexNormal;\n"
    "attribute vec4 vertexColor;\n"
    "uniform mat4 mvp;\n"
    "uniform mat4 matModel;\n"
    "varying vec2 fragTexCoord;\n"
    "varying vec4 fragColor;\n"
    "varying float fragLight;\n"
    "void main() {\n"
    "    fragTexCoord = vertexTexCoord;\n"
    "    vec3 lightDir = normalize(vec3(0.55, 0.75, 0.35));\n"
    "    vec3 norm = normalize(vec3(matModel * vec4(vertexNormal, 0.0)));\n"
    "    float diff = max(dot(norm, lightDir), 0.0);\n"
    "    fragLight = 0.30 + 0.70 * diff;\n"
    "    float hNorm = clamp(vertexPosition.y / 25.0, 0.0, 1.0);\n"
    "    vec3 lowColor = vec3(0.38, 0.48, 0.58);\n"
    "    vec3 midColor = vec3(0.65, 0.75, 0.82);\n"
    "    vec3 highColor = vec3(0.94, 0.96, 0.98);\n"
    "    vec3 terrainCol = (hNorm < 0.5) ? mix(lowColor, midColor, hNorm * 2.0) : mix(midColor, highColor, (hNorm - 0.5) * 2.0);\n"
    "    fragColor = vec4(terrainCol, 1.0);\n"
    "    gl_Position = mvp * vec4(vertexPosition, 1.0);\n"
    "}\n";
#else
    "#version 330\n"
    "in vec3 vertexPosition;\n"
    "in vec2 vertexTexCoord;\n"
    "in vec3 vertexNormal;\n"
    "in vec4 vertexColor;\n"
    "uniform mat4 mvp;\n"
    "uniform mat4 matModel;\n"
    "out vec2 fragTexCoord;\n"
    "out vec4 fragColor;\n"
    "out float fragLight;\n"
    "void main() {\n"
    "    fragTexCoord = vertexTexCoord;\n"
    "    vec3 lightDir = normalize(vec3(0.55, 0.75, 0.35));\n"
    "    vec3 norm = normalize(vec3(matModel * vec4(vertexNormal, 0.0)));\n"
    "    float diff = max(dot(norm, lightDir), 0.0);\n"
    "    fragLight = 0.30 + 0.70 * diff;\n"
    "    float hNorm = clamp(vertexPosition.y / 25.0, 0.0, 1.0);\n"
    "    vec3 lowColor = vec3(0.38, 0.48, 0.58);\n"
    "    vec3 midColor = vec3(0.65, 0.75, 0.82);\n"
    "    vec3 highColor = vec3(0.94, 0.96, 0.98);\n"
    "    vec3 terrainCol = (hNorm < 0.5) ? mix(lowColor, midColor, hNorm * 2.0) : mix(midColor, highColor, (hNorm - 0.5) * 2.0);\n"
    "    fragColor = vec4(terrainCol, 1.0);\n"
    "    gl_Position = mvp * vec4(vertexPosition, 1.0);\n"
    "}\n";
#endif

static const char* kTerrainFS =
#if defined(PLATFORM_WEB)
    "precision mediump float;\n"
    "varying vec2 fragTexCoord;\n"
    "varying vec4 fragColor;\n"
    "varying float fragLight;\n"
    "uniform vec4 colDiffuse;\n"
    "void main() {\n"
    "    vec3 finalRgb = fragColor.rgb * fragLight * colDiffuse.rgb;\n"
    "    gl_FragColor = vec4(finalRgb, 1.0);\n"
    "}\n";
#else
    "#version 330\n"
    "in vec2 fragTexCoord;\n"
    "in vec4 fragColor;\n"
    "in float fragLight;\n"
    "uniform vec4 colDiffuse;\n"
    "out vec4 finalColor;\n"
    "void main() {\n"
    "    vec3 finalRgb = fragColor.rgb * fragLight * colDiffuse.rgb;\n"
    "    finalColor = vec4(finalRgb, 1.0);\n"
    "}\n";
#endif

FTerrainRenderer::FTerrainRenderer()
    : TerrainModel({ 0 })
    , HillshadeShader({ 0 })
    , bIsLoaded(false)
    , bWireframeMode(false)
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

    // Raylib C API requires null-terminated C-string
    const std::string PathString(InFilePath);
    if (FileExists(PathString.c_str()))
    {
        TerrainModel = LoadModel(PathString.c_str());
        bIsLoaded = (TerrainModel.meshCount > 0);
        if (bIsLoaded)
        {
            if (HillshadeShader.id == 0)
            {
                HillshadeShader = LoadShaderFromMemory(kTerrainVS, kTerrainFS);
            }
            if (HillshadeShader.id > 0)
            {
                for (int32_t Index = 0; Index < TerrainModel.materialCount; ++Index)
                {
                    TerrainModel.materials[Index].shader = HillshadeShader;
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
    if (HillshadeShader.id > 0)
    {
        UnloadShader(HillshadeShader);
        HillshadeShader.id = 0;
    }
}

void FTerrainRenderer::Draw()
{
    if (!bIsLoaded)
    {
        return;
    }

    const Vector3 Position = { 0.0f, 0.0f, 0.0f };
    if (bWireframeMode)
    {
        // In wireframe mode, temporarily swap to default shader so pure Signal Red lines render crisply
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
        // Directional hillshaded surface
        DrawModel(TerrainModel, Position, 1.0f, WHITE);
    }
}

float FTerrainRenderer::GetElevationAt(const Vector3& InPosition) const
{
    return InPosition.y * 10.0f;
}

void FTerrainRenderer::ToggleWireframe()
{
    bWireframeMode = !bWireframeMode;
}
