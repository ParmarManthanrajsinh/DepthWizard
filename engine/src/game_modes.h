#pragma once

#include <cstdint>

/**
 * Traversal modes for the open-world flythrough.
 * FreeFly is the legacy 6-DOF inspection camera; Plane and FPS are game modes.
 */
enum class EGameMode : int32_t
{
    FreeFly = 0,
    Plane   = 1,
    FPS     = 2
};

constexpr int32_t kGameModeCount = 3;

inline const char* GetGameModeName(EGameMode InMode)
{
    switch (InMode)
    {
    case EGameMode::FreeFly: return "FREE-FLY";
    case EGameMode::Plane:   return "PLANE";
    case EGameMode::FPS:     return "FIRST-PERSON";
    default:                 return "UNKNOWN";
    }
}

inline EGameMode ClampGameMode(int32_t InValue)
{
    if (InValue < 0) return EGameMode::FreeFly;
    if (InValue >= kGameModeCount) return EGameMode::FPS;
    return static_cast<EGameMode>(InValue);
}
