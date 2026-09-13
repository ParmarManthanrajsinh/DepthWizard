#include "sky.h"
#include <cstdint>

#if defined(PLATFORM_WEB)
#include "shaders_gen/sky_web_vs.h"

#include "shaders_gen/sky_web_fs.h"
#else
#include "shaders_gen/sky_desktop_vs.h"

#include "shaders_gen/sky_desktop_fs.h"
#endif

FSkyDome::FSkyDome()
    : DomeModel({ 0 })
    , DomeShader({ 0 })
    , SunDirLoc(-1)
    , bReady(false)
{
}

Vector3 FSkyDome::GetSunDir()
{
    return Vector3{ 0.55f, 0.75f, 0.35f };
}

void FSkyDome::Build()
{
    if (bReady)
    {
        return;
    }

    Mesh DomeMesh = GenMeshSphere(kDomeRadius, 32, 32);
    // Viewed from the inside: flip triangle winding so front faces point in.
    // (Avoids any rlgl cull-state dependency in both native and WASM builds.)
    if (DomeMesh.indices != nullptr)
    {
        const int32_t TriCount = DomeMesh.triangleCount;
        for (int32_t Index = 0; Index < TriCount; ++Index)
        {
            const int32_t Base = Index * 3;
            const unsigned short Temp = DomeMesh.indices[Base];
            DomeMesh.indices[Base] = DomeMesh.indices[Base + 2];
            DomeMesh.indices[Base + 2] = Temp;
        }
    }
    DomeModel = LoadModelFromMesh(DomeMesh);
    DomeShader = LoadShaderFromMemory(kSkyVS, kSkyFS);
    SunDirLoc = GetShaderLocation(DomeShader, "uSunDir");

    if (DomeModel.meshCount > 0 && DomeShader.id > 0)
    {
        for (int32_t Index = 0; Index < DomeModel.materialCount; ++Index)
        {
            DomeModel.materials[Index].shader = DomeShader;
        }
        const Vector3 SunDir = GetSunDir();
        if (SunDirLoc >= 0)
        {
            SetShaderValue(DomeShader, SunDirLoc, &SunDir, SHADER_UNIFORM_VEC3);
        }
        bReady = true;
    }
}

void FSkyDome::Unload()
{
    if (!bReady)
    {
        return;
    }
    UnloadModel(DomeModel);
    UnloadShader(DomeShader);
    DomeModel = { 0 };
    DomeShader = { 0 };
    bReady = false;
}

void FSkyDome::Draw(const Vector3& InCameraPos) const
{
    if (!bReady)
    {
        return;
    }
    DrawModel(DomeModel, InCameraPos, 1.0f, WHITE);
}
