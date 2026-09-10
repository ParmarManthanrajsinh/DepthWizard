#pragma once
#include "raylib.h"

class FreeFlyCamera {
public:
    Camera3D camera;
    float moveSpeed;
    float lookSpeed;
    float pitch;
    float yaw;

    FreeFlyCamera();
    void Init(Vector3 startPos, Vector3 targetPos);
    void Update(float deltaTime);
};
