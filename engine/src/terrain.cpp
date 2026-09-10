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
    GLSL_HEADER
    GLSL_IN " vec3 vertexPosition;\n"
    GLSL_IN " vec2 vertexTexCoord;\n"
    GLSL_IN " vec3 vertexNormal;\n"
    GLSL_IN " vec4 vertexColor;\n"
    "uniform mat4 mvp;\n"
    "uniform mat4 matModel;\n"
    GLSL_OUT " vec2 fragTexCoord;\n"
    GLSL_OUT " vec4 fragColor;\n"
    GLSL_OUT " float fragLight;\n"
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

#if defined(PLATFORM_WEB)
static const char* kTerrainFS =
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
static const char* kTerrainFS =
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

void FTerrainRenderer::ToggleWireframe()
{
    bWireframeMode = !bWireframeMode;
}
