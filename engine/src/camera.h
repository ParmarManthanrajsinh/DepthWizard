#pragma once

#include "raylib.h"

/**
 * Free-flying 6-DOF inspection camera for 3D terrain visualization.
 * Conforms to Unreal Engine naming conventions and standards.
 */
class FFreeFlyCamera
{
public:
    Camera3D Camera;
    float MoveSpeed;
    float LookSpeed;
    float Pitch;
    float Yaw;

    FFreeFlyCamera();

    /**
     * Initializes camera transform and orientation looking towards target.
     * 
     * @param InStartPos Initial eye position.
     * @param InTargetPos Target focus point.
     */
    void Initialize(const Vector3& InStartPos, const Vector3& InTargetPos);

    /**
     * Advances camera input handling and positional integration.
     * 
     * @param InDeltaTime Frame elapsed time in seconds.
     */
    void Update(float InDeltaTime);

    /**
     * Resets camera to standard overhead perspective.
     */
    void Reset();
};
