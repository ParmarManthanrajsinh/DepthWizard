#pragma once

#include "raylib.h"
#include "terrain.h"

/**
 * Forgiving arcade flight model with smoothed, analog-feel inputs:
 * sticks ramp like a real stick, attitude follows with airframe lag,
 * throttle spools instead of jumping. Tuned for easy control.
 *
 * Rendering uses procedural parts by default; LoadPlaneModel() swaps in a
 * user-supplied .glb (forward = +Z, normalized to ~11 m wingspan) with the
 * same flight behavior.
 */
class FArcadePlane
{
public:
    static constexpr float kMinSpeed = 25.0f;
    static constexpr float kMaxSpeed = 110.0f;
    static constexpr float kGroundClearance = 3.0f;
    static constexpr float kCustomMaxDim = 11.0f;

    Vector3 Position;
    float Yaw;
    float Pitch;
    float Roll;
    float Throttle; // 0..1
    float Speed;
    float PropAngle;

    FArcadePlane();

    /** Builds the shared unit-cube model (call once after InitWindow). */
    void BuildModels();
    /** Releases the shared model (call once before CloseWindow). */
    void UnloadModels();

    /**
     * Loads a user-supplied airplane .glb (nose = +Z, up = +Y, e.g. jet.glb).
     * Normalized so its largest dimension spans kCustomMaxDim meters and its
     * center sits on the flight position. Returns false when missing/invalid;
     * the procedural fallback stays active.
     */
    bool LoadPlaneModel(const char* InFilePath);

    /** Loads a custom livery texture for the airplane model. */
    bool LoadPlaneTexture(const char* InFilePath);

    /** Places the plane above the terrain at cruise throttle. */
    void Spawn(const FTerrainRenderer* InTerrain);

    /** Reads input and integrates flight. Camera-agnostic. */
    void Update(float InDeltaTime, const FTerrainRenderer* InTerrain);

    /** Chase camera pose for the current frame (unsmoothed; caller damps). */
    void GetChasePose(Vector3& OutCamPos, Vector3& OutCamTarget) const;

    /** Forward vector from current attitude. */
    Vector3 GetForward() const;

    float GetSpeedKmh() const { return Speed * 3.6f; }
    float GetThrottlePct() const { return Throttle * 100.0f; }
    float GetSpeedNorm() const { return (Speed - kMinSpeed) / (kMaxSpeed - kMinSpeed); }

    /** Draws the plane with dynamic sun lighting and ground shadow. */
    void Draw(const Vector3& InCameraPos, const FTerrainRenderer* InTerrain) const;
    void Draw() const;

private:
    struct FPart
    {
        Vector3 Offset;
        Vector3 Size;
        Color Tint;
    };

    /** Rotates a local offset by the current body attitude. */
    Vector3 RotateOffset(const Vector3& InOffset) const;

    /** Body attitude as a unit quaternion (yaw -> pitch -> roll). */
    void GetBodyQuat(float& OutX, float& OutY, float& OutZ, float& OutW) const;

    /** Full custom-model attitude (body composed with model alignment). */
    void GetModelAxisAngle(Vector3& OutAxis, float& OutAngleDeg) const;

    /** Frame-rate independent damping factor: 1 - exp(-k*dt). */
    static float Damp(float InRate, float InDeltaTime);

    Model UnitCube;
    Model CustomModel;
    Shader PlaneShader;
    int32_t SunDirLoc;
    int32_t CamPosLoc;
    float CustomScale;
    Vector3 CustomCenter; // bounds center in model units (for recentering)
    bool bModelsReady;
    bool bHasCustomModel;
    bool bShaderReady;

    // Smoothed stick state (the "analog feel" layer).
    float StickRoll;   // -1..1 bank command
    float PitchRateSm; // smoothed pitch rate (rad/s)
    float YawRateSm;   // smoothed mouse yaw rate (rad/s)
};
