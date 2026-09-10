#pragma once
#include "raylib.h"
#include <cmath>

inline Vector3 Vector3Add(Vector3 v1, Vector3 v2) { return { v1.x + v2.x, v1.y + v2.y, v1.z + v2.z }; }
inline Vector3 Vector3Subtract(Vector3 v1, Vector3 v2) { return { v1.x - v2.x, v1.y - v2.y, v1.z - v2.z }; }
inline Vector3 Vector3Scale(Vector3 v, float scale) { return { v.x * scale, v.y * scale, v.z * scale }; }
inline float Vector3Length(Vector3 v) { return sqrtf(v.x * v.x + v.y * v.y + v.z * v.z); }
inline Vector3 Vector3Normalize(Vector3 v) {
    float l = Vector3Length(v);
    return (l > 0.0f) ? Vector3Scale(v, 1.0f / l) : Vector3{ 0.0f, 0.0f, 0.0f };
}
