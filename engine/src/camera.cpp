#include "camera.h"
#include "raymath.h"
#include <algorithm>
#include <cmath>

FFreeFlyCamera::FFreeFlyCamera()
    : MoveSpeed(55.0f)
    , LookSpeed(0.003f)
    , Pitch(-0.44f)
    , Yaw(3.14159265f)
{
    Camera = { 0 };
    Camera.position = Vector3{ 0.0f, 95.0f, 180.0f };
    Camera.target = Vector3{ 0.0f, 15.0f, 0.0f };
    Camera.up = Vector3{ 0.0f, 1.0f, 0.0f };
    Camera.fovy = 60.0f;
    Camera.projection = CAMERA_PERSPECTIVE;
}

void FFreeFlyCamera::Initialize(const Vector3& InStartPos, const Vector3& InTargetPos)
{
    Camera.position = InStartPos;
    Camera.target = InTargetPos;

    const Vector3 Delta = Vector3Subtract(InTargetPos, InStartPos);
    const float DistXZ = hypotf(Delta.x, Delta.z);

    if (DistXZ > 0.001f)
    {
        Pitch = atan2f(Delta.y, DistXZ);
        Yaw = atan2f(Delta.x, Delta.z);
    }
    else
    {
        Pitch = -0.44f;
        Yaw = 3.14159265f;
    }
}

void FFreeFlyCamera::Reset()
{
    Initialize(Vector3{ 0.0f, 95.0f, 180.0f }, Vector3{ 0.0f, 15.0f, 0.0f });
}

void FFreeFlyCamera::Update(float InDeltaTime)
{
    if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsMouseButtonDown(MOUSE_BUTTON_RIGHT))
    {
        const Vector2 MouseDelta = GetMouseDelta();
        Yaw -= MouseDelta.x * LookSpeed;
        Pitch -= MouseDelta.y * LookSpeed;
        Pitch = std::clamp(Pitch, -1.5f, 1.5f);
    }

    const Vector3 Forward = {
        cosf(Pitch) * sinf(Yaw),
        sinf(Pitch),
        cosf(Pitch) * cosf(Yaw)
    };

    const Vector3 Right = Vector3Normalize(Vector3{ -Forward.z, 0.0f, Forward.x });
    const float CurrentSpeed = MoveSpeed * ((IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT)) ? 2.5f : 1.0f);

    const float MoveX = (float)((IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) - (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT)));
    const float MoveZ = (float)((IsKeyDown(KEY_W) || IsKeyDown(KEY_UP)) - (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN)));
    const float MoveY = (float)(IsKeyDown(KEY_SPACE) - (IsKeyDown(KEY_C) || IsKeyDown(KEY_LEFT_CONTROL)));

    Vector3 Movement = Vector3Add(
        Vector3Scale(Forward, MoveZ),
        Vector3Add(Vector3Scale(Right, MoveX), Vector3{ 0.0f, MoveY, 0.0f })
    );

    if (Vector3Length(Movement) > 0.0f)
    {
        Movement = Vector3Normalize(Movement);
        Camera.position = Vector3Add(Camera.position, Vector3Scale(Movement, CurrentSpeed * InDeltaTime));
    }

    if (Camera.position.y < 2.0f)
    {
        Camera.position.y = 2.0f;
    }

    Camera.target = Vector3Add(Camera.position, Forward);
}
