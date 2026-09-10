#include "camera.h"
#include "raymath.h"
#include <algorithm>
#include <cmath>

FreeFlyCamera::FreeFlyCamera() 
    : moveSpeed(35.0f), lookSpeed(0.003f), pitch(-0.28f), yaw(3.14159265f) {
    camera = { 0 };
    camera.up = Vector3{ 0.0f, 1.0f, 0.0f };
    camera.fovy = 60.0f;
    camera.projection = CAMERA_PERSPECTIVE;
}

void FreeFlyCamera::Init(Vector3 startPos, Vector3 targetPos) {
    camera.position = startPos;
    camera.target = targetPos;

    // Compute pitch and yaw from startPos towards targetPos so camera looks directly at terrain
    Vector3 delta = Vector3Subtract(targetPos, startPos);
    float distXZ = sqrtf(delta.x * delta.x + delta.z * delta.z);
    if (distXZ > 0.001f) {
        pitch = atan2f(delta.y, distXZ);
        yaw = atan2f(delta.x, delta.z);
    } else {
        pitch = -0.28f;
        yaw = 3.14159265f;
    }
}

void FreeFlyCamera::Update(float deltaTime) {
    // Mouse look when right mouse or left mouse is held
    if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsMouseButtonDown(MOUSE_BUTTON_RIGHT)) {
        Vector2 mouseDelta = GetMouseDelta();
        yaw -= mouseDelta.x * lookSpeed;
        pitch -= mouseDelta.y * lookSpeed;
        pitch = std::clamp(pitch, -1.5f, 1.5f);
    }

    // Direction vectors from pitch and yaw
    Vector3 forward = {
        cosf(pitch) * sinf(yaw),
        sinf(pitch),
        cosf(pitch) * cosf(yaw)
    };

    // Right vector perpendicular to forward and world up in XZ plane (fixes inverted A/D controls)
    Vector3 right = { -forward.z, 0.0f, forward.x };
    float rLen = sqrtf(right.x * right.x + right.z * right.z);
    if (rLen > 0.001f) {
        right.x /= rLen;
        right.z /= rLen;
    } else {
        right = { 1.0f, 0.0f, 0.0f };
    }
    Vector3 up = { 0.0f, 1.0f, 0.0f };

    float speed = moveSpeed;
    if (IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT)) {
        speed *= 2.5f; // Turbo boost
    }

    Vector3 movement = { 0 };

    if (IsKeyDown(KEY_W) || IsKeyDown(KEY_UP))    movement = Vector3Add(movement, forward);
    if (IsKeyDown(KEY_S) || IsKeyDown(KEY_DOWN))  movement = Vector3Subtract(movement, forward);
    if (IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) movement = Vector3Add(movement, right);
    if (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT))  movement = Vector3Subtract(movement, right);
    if (IsKeyDown(KEY_SPACE))                      movement = Vector3Add(movement, up);
    if (IsKeyDown(KEY_C) || IsKeyDown(KEY_LEFT_CONTROL)) movement = Vector3Subtract(movement, up);

    if (Vector3Length(movement) > 0.0f) {
        movement = Vector3Normalize(movement);
        camera.position = Vector3Add(camera.position, Vector3Scale(movement, speed * deltaTime));
    }

    // Camera height clamp (keep above minimum terrain ground plane)
    if (camera.position.y < 2.0f) {
        camera.position.y = 2.0f;
    }

    camera.target = Vector3Add(camera.position, forward);
}

