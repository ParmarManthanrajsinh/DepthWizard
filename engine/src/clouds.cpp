#include "clouds.h"
#include "raymath.h"
#include "rlgl.h"
#include <cmath>
#include <algorithm>

#if defined(PLATFORM_WEB)
#include "shaders_gen/clouds_web_vs.h"

#include "shaders_gen/clouds_web_fs.h"
#else
#include "shaders_gen/clouds_desktop_vs.h"

#include "shaders_gen/clouds_desktop_fs.h"
#endif

FVolumetricCloudRenderer::FVolumetricCloudRenderer()
    : CloudTarget({ 0 })
    , RaymarchShader({ 0 })
    , CamPosLoc(-1)
    , CamForwardLoc(-1)
    , CamUpLoc(-1)
    , CamRightLoc(-1)
    , SunDirLoc(-1)
    , TanFovLoc(-1)
    , AspectLoc(-1)
    , TimeLoc(-1)
    , CloudBaseLoc(-1)
    , CloudTopLoc(-1)
    , WindTime(0.0f)
    , TargetWidth(0)
    , TargetHeight(0)
    , bReady(false)
    , bEnabled(true)
{
}

FVolumetricCloudRenderer::~FVolumetricCloudRenderer()
{
    Unload();
}

void FVolumetricCloudRenderer::Build(int32_t InScreenWidth, int32_t InScreenHeight)
{
    if (bReady)
    {
        return;
    }

    TargetWidth = std::max(InScreenWidth / 2, 320);
    TargetHeight = std::max(InScreenHeight / 2, 180);

    CloudTarget = LoadRenderTexture(TargetWidth, TargetHeight);
    SetTextureFilter(CloudTarget.texture, TEXTURE_FILTER_BILINEAR);

    RaymarchShader = LoadShaderFromMemory(kCloudRaymarchVS, kCloudRaymarchFS);
    if (RaymarchShader.id > 0)
    {
        CamPosLoc = GetShaderLocation(RaymarchShader, "uCamPos");
        CamForwardLoc = GetShaderLocation(RaymarchShader, "uCamForward");
        CamUpLoc = GetShaderLocation(RaymarchShader, "uCamUp");
        CamRightLoc = GetShaderLocation(RaymarchShader, "uCamRight");
        SunDirLoc = GetShaderLocation(RaymarchShader, "uSunDir");
        TanFovLoc = GetShaderLocation(RaymarchShader, "uTanFov");
        AspectLoc = GetShaderLocation(RaymarchShader, "uAspect");
        TimeLoc = GetShaderLocation(RaymarchShader, "uTime");
        CloudBaseLoc = GetShaderLocation(RaymarchShader, "uCloudBase");
        CloudTopLoc = GetShaderLocation(RaymarchShader, "uCloudTop");

        int32_t ResLoc = GetShaderLocation(RaymarchShader, "uResolution");
        if (ResLoc >= 0)
        {
            float Res[2] = { (float)TargetWidth, (float)TargetHeight };
            SetShaderValue(RaymarchShader, ResLoc, Res, SHADER_UNIFORM_VEC2);
        }

        const float BaseY = kCloudBaseY;
        const float TopY = kCloudTopY;
        if (CloudBaseLoc >= 0) SetShaderValue(RaymarchShader, CloudBaseLoc, &BaseY, SHADER_UNIFORM_FLOAT);
        if (CloudTopLoc >= 0) SetShaderValue(RaymarchShader, CloudTopLoc, &TopY, SHADER_UNIFORM_FLOAT);

        bReady = true;
    }
}

void FVolumetricCloudRenderer::Unload()
{
    if (!bReady)
    {
        return;
    }
    UnloadRenderTexture(CloudTarget);
    UnloadShader(RaymarchShader);
    CloudTarget = { 0 };
    RaymarchShader = { 0 };
    bReady = false;
}

void FVolumetricCloudRenderer::Resize(int32_t InScreenWidth, int32_t InScreenHeight)
{
    const int32_t NewW = std::max(InScreenWidth / 2, 320);
    const int32_t NewH = std::max(InScreenHeight / 2, 180);
    if (NewW == TargetWidth && NewH == TargetHeight)
    {
        return;
    }

    if (CloudTarget.id > 0)
    {
        UnloadRenderTexture(CloudTarget);
    }
    TargetWidth = NewW;
    TargetHeight = NewH;
    CloudTarget = LoadRenderTexture(TargetWidth, TargetHeight);
    SetTextureFilter(CloudTarget.texture, TEXTURE_FILTER_BILINEAR);

    if (RaymarchShader.id > 0)
    {
        int32_t ResLoc = GetShaderLocation(RaymarchShader, "uResolution");
        if (ResLoc >= 0)
        {
            float Res[2] = { (float)TargetWidth, (float)TargetHeight };
            SetShaderValue(RaymarchShader, ResLoc, Res, SHADER_UNIFORM_VEC2);
        }
    }
}

void FVolumetricCloudRenderer::Update(float InDeltaTime)
{
    WindTime += InDeltaTime;
}

void FVolumetricCloudRenderer::RenderSlab(const Camera3D& InCamera, const Vector3& InSunDir)
{
    if (!bReady || !bEnabled)
    {
        return;
    }

    // Camera orthonormal basis
    Vector3 Forward = Vector3Normalize(Vector3Subtract(InCamera.target, InCamera.position));
    Vector3 Right = Vector3Normalize(Vector3CrossProduct(Forward, InCamera.up));
    Vector3 Up = Vector3Normalize(Vector3CrossProduct(Right, Forward));

    const float TanFov = tanf(InCamera.fovy * 0.5f * (3.14159265f / 180.0f));
    const float Aspect = (float)TargetWidth / (float)TargetHeight;

    if (CamPosLoc >= 0) SetShaderValue(RaymarchShader, CamPosLoc, &InCamera.position, SHADER_UNIFORM_VEC3);
    if (CamForwardLoc >= 0) SetShaderValue(RaymarchShader, CamForwardLoc, &Forward, SHADER_UNIFORM_VEC3);
    if (CamUpLoc >= 0) SetShaderValue(RaymarchShader, CamUpLoc, &Up, SHADER_UNIFORM_VEC3);
    if (CamRightLoc >= 0) SetShaderValue(RaymarchShader, CamRightLoc, &Right, SHADER_UNIFORM_VEC3);
    if (SunDirLoc >= 0) SetShaderValue(RaymarchShader, SunDirLoc, &InSunDir, SHADER_UNIFORM_VEC3);
    if (TanFovLoc >= 0) SetShaderValue(RaymarchShader, TanFovLoc, &TanFov, SHADER_UNIFORM_FLOAT);
    if (AspectLoc >= 0) SetShaderValue(RaymarchShader, AspectLoc, &Aspect, SHADER_UNIFORM_FLOAT);
    if (TimeLoc >= 0) SetShaderValue(RaymarchShader, TimeLoc, &WindTime, SHADER_UNIFORM_FLOAT);

    // Offscreen half-resolution raymarch pass
    BeginTextureMode(CloudTarget);
        rlDisableColorBlend();
        ClearBackground(BLANK);
        BeginShaderMode(RaymarchShader);
            DrawRectangle(0, 0, TargetWidth, TargetHeight, WHITE);
        EndShaderMode();
        rlEnableColorBlend();
    EndTextureMode();
}

void FVolumetricCloudRenderer::DrawComposite(int32_t InScreenWidth, int32_t InScreenHeight) const
{
    if (!bReady || !bEnabled)
    {
        return;
    }

    // OpenGL render textures have inverted Y axis in Raylib
    const Rectangle Src = { 0.0f, 0.0f, (float)CloudTarget.texture.width, -(float)CloudTarget.texture.height };
    const Rectangle Dst = { 0.0f, 0.0f, (float)InScreenWidth, (float)InScreenHeight };
    BeginBlendMode(BLEND_ALPHA_PREMULTIPLY);
    DrawTexturePro(CloudTarget.texture, Src, Dst, Vector2{ 0.0f, 0.0f }, 0.0f, WHITE);
    EndBlendMode();
}
