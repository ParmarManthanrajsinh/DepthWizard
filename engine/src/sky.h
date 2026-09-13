#pragma once

#include "raylib.h"
#include <cstdint>

/**
 * Procedural midday sky dome: gradient + analytic sun + horizon haze,
 * ACES-approximant tonemap folded into the shader (LDR-safe for WebGL2).
 * No textures, no .hdr download. The dome follows the camera and is drawn
 * first; ClearBackground uses the matching haze color as a seamless fallback.
 */
class FSkyDome
{
public:
    static constexpr float kDomeRadius = 6000.0f;

    FSkyDome();

    /** Builds dome mesh + shader (call once after InitWindow). */
    void Build();
    /** Releases GPU resources. */
    void Unload();

    /** Sun direction in world space (matches terrain shader light). */
    static Vector3 GetSunDir();

    /** Draws the dome centered on the camera position. */
    void Draw(const Vector3& InCameraPos) const;

private:
    Model DomeModel;
    Shader DomeShader;
    int32_t SunDirLoc;
    bool bReady;
};
