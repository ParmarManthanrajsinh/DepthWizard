#include "walker.h"
#include "raymath.h"
#include "world.h"
#include <algorithm>
#include <cmath>

FFPSWalker::FFPSWalker()
    : Position(Vector3{ 0.0f, 20.0f, 60.0f })
    , Yaw(3.14159265f)
    , Pitch(-0.05f)
    , FallSpeed(0.0f)
    , CurrentSpeed(0.0f)
    , bGrounded(false)
{
}

void FFPSWalker::Spawn(const FTerrainRenderer* InTerrain, float InX, float InZ, float InYaw, float InPitch)
{
    float GroundY = FWorldDressing::kWaterLevelY;
    if (InTerrain != nullptr)
    {
        GroundY = InTerrain->GetGroundHeightOr(InX, InZ, GroundY);
    }
    Position = Vector3{ InX, GroundY, InZ };
    Yaw = InYaw;
    Pitch = InPitch;
    FallSpeed = 0.0f;
    CurrentSpeed = 0.0f;
    bGrounded = true;
}

void FFPSWalker::Update(float InDeltaTime, const FTerrainRenderer* InTerrain)
{
    // Look (shared drag-to-steer convention with fly/plane modes).
    if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsMouseButtonDown(MOUSE_BUTTON_RIGHT))
    {
        const Vector2 MouseDelta = GetMouseDelta();
        Yaw -= MouseDelta.x * 0.003f;
        Pitch -= MouseDelta.y * 0.003f;
        Pitch = std::clamp(Pitch, -1.5f, 1.5f);
    }

    const Vector3 Forward = { sinf(Yaw), 0.0f, cosf(Yaw) };
    const Vector3 Right = Vector3Normalize(Vector3{ -Forward.z, 0.0f, Forward.x });
    const bool bSprint = IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT);
    const float TargetSpeed = bSprint ? kSprintSpeed : kWalkSpeed;

    const float MoveX = static_cast<float>((IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) - (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT)));
    const float MoveZ = static_cast<float>((IsKeyDown(KEY_W) || IsKeyDown(KEY_UP)) - (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN)));

    Vector3 Step = Vector3Add(Vector3Scale(Forward, MoveZ), Vector3Scale(Right, MoveX));
    if (Vector3Length(Step) > 0.0f)
    {
        Step = Vector3Normalize(Step);
        CurrentSpeed = TargetSpeed;
        Position = Vector3Add(Position, Vector3Scale(Step, CurrentSpeed * InDeltaTime));
    }
    else
    {
        CurrentSpeed = 0.0f;
    }

    FWorldDressing::ClampToWorld(Position);

    // Vertical: jump + gravity, grounded on terrain (or water-top when off-mesh).
    float FloorY = FWorldDressing::kWaterLevelY;
    if (InTerrain != nullptr)
    {
        FloorY = InTerrain->GetGroundHeightOr(Position.x, Position.z, FloorY);
    }

    // Step height limit: prevent scaling vertical cliff walls (> 2.5m abrupt step)
    if (bGrounded && (FloorY - Position.y) > 2.5f)
    {
        Position = Vector3Subtract(Position, Vector3Scale(Step, CurrentSpeed * InDeltaTime));
        FloorY = InTerrain ? InTerrain->GetGroundHeightOr(Position.x, Position.z, FWorldDressing::kWaterLevelY) : FWorldDressing::kWaterLevelY;
    }

    // Walking off a ledge / drop: transition from grounded to falling
    if (bGrounded && FloorY < Position.y - 0.4f)
    {
        bGrounded = false;
    }

    if (bGrounded && IsKeyPressed(KEY_SPACE))
    {
        FallSpeed = kJumpVelocity;
        bGrounded = false;
    }

    if (!bGrounded)
    {
        FallSpeed += kGravity * InDeltaTime;
        Position.y += FallSpeed * InDeltaTime;
        if (Position.y <= FloorY)
        {
            Position.y = FloorY;
            FallSpeed = 0.0f;
            bGrounded = true;
        }
    }
    else
    {
        Position.y = FloorY;
    }
}

void FFPSWalker::GetEyePose(Vector3& OutEyePos, Vector3& OutLookAt) const
{
    OutEyePos = Vector3{ Position.x, Position.y + kEyeHeight, Position.z };
    const Vector3 Forward = {
        cosf(Pitch) * sinf(Yaw),
        sinf(Pitch),
        cosf(Pitch) * cosf(Yaw)
    };
    OutLookAt = Vector3Add(OutEyePos, Forward);
}
