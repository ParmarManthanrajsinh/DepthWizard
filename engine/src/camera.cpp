#include "camera.h"
#include "raymath.h"
#include <algorithm>
#include <cmath>

FFreeFlyCamera::FFreeFlyCamera()
    : MoveSpeed(35.0f)
    , LookSpeed(0.003f)
    , Pitch(-0.28f)
    , Yaw(3.14159265f)
{
    Camera = { 0 };
    Camera.position = Vector3{ 0.0f, 45.0f, 85.0f };
    Camera.target = Vector3{ 0.0f, 20.0f, 0.0f };
    Camera.up = Vector3{ 0.0f, 1.0f, 0.0f };
    Camera.fovy = 60.0f;
    Camera.projection = CAMERA_PERSPECTIVE;
}

void FFreeFlyCamera::Initialize(const Vector3& InStartPos, const Vector3& InTargetPos)
{
    Camera.position = InStartPos;
    Camera.target = InTargetPos;

    // Compute pitch and yaw from start position towards target position
    const Vector3 Delta = Vector3Subtract(InTargetPos, InStartPos);
    const float DistXZ = sqrtf(Delta.x * Delta.x + Delta.z * Delta.z);

    if (DistXZ > 0.001f)
    {
        Pitch = atan2f(Delta.y, DistXZ);
        Yaw = atan2f(Delta.x, Delta.z);
    }
    else
    {
        Pitch = -0.28f;
        Yaw = 3.14159265f;
    }
}

void FFreeFlyCamera::Reset()
{
    Initialize(Vector3{ 0.0f, 45.0f, 85.0f }, Vector3{ 0.0f, 20.0f, 0.0f });
}

void FFreeFlyCamera::Update(float InDeltaTime)
{
    // Mouse look when right mouse or left mouse is held
    if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsMouseButtonDown(MOUSE_BUTTON_RIGHT))
    {
        const Vector2 MouseDelta = GetMouseDelta();
        Yaw -= MouseDelta.x * LookSpeed;
        Pitch -= MouseDelta.y * LookSpeed;
        Pitch = std::clamp(Pitch, -1.5f, 1.5f);
    }

    // Direction vectors from pitch and yaw
    const Vector3 Forward = {
        cosf(Pitch) * sinf(Yaw),
        sinf(Pitch),
        cosf(Pitch) * cosf(Yaw)
    };

    // Right vector perpendicular to forward and world up in XZ plane
    Vector3 Right = { -Forward.z, 0.0f, Forward.x };
    const float RightLen = sqrtf(Right.x * Right.x + Right.z * Right.z);
    if (RightLen > 0.001f)
    {
        Right.x /= RightLen;
        Right.z /= RightLen;
    }
    else
    {
        Right = { 1.0f, 0.0f, 0.0f };
    }
    const Vector3 Up = { 0.0f, 1.0f, 0.0f };

    float CurrentSpeed = MoveSpeed;
    if (IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT))
    {
        CurrentSpeed *= 2.5f; // Turbo boost
    }

    Vector3 Movement = { 0 };

    if (IsKeyDown(KEY_W) || IsKeyDown(KEY_UP))
    {
        Movement = Vector3Add(Movement, Forward);
    }
    if (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN))
    {
        Movement = Vector3Subtract(Movement, Forward);
    }
    if (IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT))
    {
        Movement = Vector3Add(Movement, Right);
    }
    if (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT))
    {
        Movement = Vector3Subtract(Movement, Right);
    }
    if (IsKeyDown(KEY_SPACE))
    {
        Movement = Vector3Add(Movement, Up);
    }
    if (IsKeyDown(KEY_C) || IsKeyDown(KEY_LEFT_CONTROL))
    {
        Movement = Vector3Subtract(Movement, Up);
    }

    if (Vector3Length(Movement) > 0.0f)
    {
        Movement = Vector3Normalize(Movement);
        Camera.position = Vector3Add(Camera.position, Vector3Scale(Movement, CurrentSpeed * InDeltaTime));
    }

    // Camera height clamp (keep above minimum terrain ground plane)
    if (Camera.position.y < 2.0f)
    {
        Camera.position.y = 2.0f;
    }

    Camera.target = Vector3Add(Camera.position, Forward);
}
