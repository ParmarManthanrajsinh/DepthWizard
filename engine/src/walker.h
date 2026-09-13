#pragma once

#include "raylib.h"
#include "terrain.h"

/**
 * Ground-level first-person walker: gravity, jump, terrain clamp.
 * Walk + look only (no interaction), pointer-drag look shared with fly mode.
 */
class FFPSWalker
{
public:
    static constexpr float kEyeHeight = 1.7f;
    static constexpr float kWalkSpeed = 9.0f;
    static constexpr float kSprintSpeed = 15.0f;
    static constexpr float kJumpVelocity = 6.5f;
    static constexpr float kGravity = -18.0f;

    Vector3 Position; // feet position
    float Yaw;
    float Pitch;
    float FallSpeed;
    float CurrentSpeed;
    bool bGrounded;

    FFPSWalker();

    /** Drops the walker onto the terrain near the current XZ. */
    void Spawn(const FTerrainRenderer* InTerrain, float InX, float InZ, float InYaw = 3.14159265f, float InPitch = -0.05f);

    /** Reads input, integrates gravity, clamps to terrain. */
    void Update(float InDeltaTime, const FTerrainRenderer* InTerrain);

    /** Eye pose for the camera. */
    void GetEyePose(Vector3& OutEyePos, Vector3& OutLookAt) const;

    float GetSpeedKmh() const { return CurrentSpeed * 3.6f; }
};
