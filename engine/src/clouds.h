#pragma once

#include "raylib.h"
#include <cstdint>

/**
 * AAA physically-based volumetric cloud renderer (Horizon Zero Dawn / Schneider standard).
 * 
 * Features:
 * - Raymarched dual-shell atmospheric slab (Base: 260 m, Top: 640 m).
 * - Perlin-Worley 3D density modeling with wind advection.
 * - Radiative transfer: Beer-Lambert extinction + powder sugar effect.
 * - Dual-lobe Henyey-Greenstein phase function (silver-lining forward glare + backscatter).
 * - Multi-scatter directional sun lighting with secondary shadow raymarch.
 * - Half-resolution offscreen render target + blue-noise temporal dither + bilinear upsample for locked 60 FPS.
 */
class FVolumetricCloudRenderer
{
public:
    static constexpr float kCloudBaseY = 260.0f;
    static constexpr float kCloudTopY = 640.0f;

    FVolumetricCloudRenderer();
    ~FVolumetricCloudRenderer();

    /** Allocates half-resolution render target and compiles GLSL raymarching & composite shaders. */
    void Build(int32_t InScreenWidth, int32_t InScreenHeight);

    /** Releases GPU render targets and shaders. */
    void Unload();

    /** Reallocates render targets on window resize. */
    void Resize(int32_t InScreenWidth, int32_t InScreenHeight);

    /** Advances cloud wind advection. */
    void Update(float InDeltaTime);

    /** Raymarches volumetric clouds into half-res offscreen target. */
    void RenderSlab(const Camera3D& InCamera, const Vector3& InSunDir);

    /** Composites the half-res cloud buffer over the screen with bilinear upsample and alpha blending. */
    void DrawComposite(int32_t InScreenWidth, int32_t InScreenHeight) const;

    /** Toggles cloud rendering on/off for benchmarking. */
    void ToggleEnabled() { bEnabled = !bEnabled; }
    bool IsEnabled() const { return bEnabled; }

private:
    RenderTexture2D CloudTarget;
    Shader RaymarchShader;

    // Uniform locations
    int32_t CamPosLoc;
    int32_t CamForwardLoc;
    int32_t CamUpLoc;
    int32_t CamRightLoc;
    int32_t SunDirLoc;
    int32_t TanFovLoc;
    int32_t AspectLoc;
    int32_t TimeLoc;
    int32_t CloudBaseLoc;
    int32_t CloudTopLoc;

    float WindTime;
    int32_t TargetWidth;
    int32_t TargetHeight;
    bool bReady;
    bool bEnabled;
};
