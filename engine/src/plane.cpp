#include "plane.h"
#include "raymath.h"
#include "world.h"
#include <algorithm>
#include <cmath>

namespace
{
constexpr float kDegPerRad = 180.0f / 3.14159265f;

// Gentle stick tuning: lower = calmer, higher = twitchier.
constexpr float kMouseYawSens = 0.0016f;
constexpr float kMousePitchRate = 0.0022f;
constexpr float kArrowPitchRate = 1.1f;
constexpr float kMaxBank = 0.75f;

// jet.glb alignment: nose +Z, up +Y (matches body attitude directly).
constexpr float kModelAlignYaw = 0.0f;

struct FQuat
{
    float X, Y, Z, W;
};

static FQuat QuatFromAxisAngle(float InAxisX, float InAxisY, float InAxisZ, float InAngleRad)
{
    const float Half = InAngleRad * 0.5f;
    const float S = sinf(Half);
    return FQuat{ InAxisX * S, InAxisY * S, InAxisZ * S, cosf(Half) };
}

static FQuat QuatMul(const FQuat& A, const FQuat& B)
{
    return FQuat{
        A.W * B.X + A.X * B.W + A.Y * B.Z - A.Z * B.Y,
        A.W * B.Y - A.X * B.Z + A.Y * B.W + A.Z * B.X,
        A.W * B.Z + A.X * B.Y - A.Y * B.X + A.Z * B.W,
        A.W * B.W - A.X * B.X - A.Y * B.Y - A.Z * B.Z
    };
}

static Vector3 QuatRotate(const FQuat& Q, const Vector3& V)
{
    const Vector3 Qv = { Q.X, Q.Y, Q.Z };
    // v' = v + 2 * cross(qv, cross(qv, v) + w * v)
    const Vector3 Inner = {
        Qv.y * V.z - Qv.z * V.y + Q.W * V.x,
        Qv.z * V.x - Qv.x * V.z + Q.W * V.y,
        Qv.x * V.y - Qv.y * V.x + Q.W * V.z
    };
    const Vector3 Outer = {
        Qv.y * Inner.z - Qv.z * Inner.y,
        Qv.z * Inner.x - Qv.x * Inner.z,
        Qv.x * Inner.y - Qv.y * Inner.x
    };
    return Vector3{ V.x + 2.0f * Outer.x, V.y + 2.0f * Outer.y, V.z + 2.0f * Outer.z };
}
} // namespace

#if defined(PLATFORM_WEB)
#include "shaders_gen/plane_web_vs.h"

#include "shaders_gen/plane_web_fs.h"
#else
#include "shaders_gen/plane_desktop_vs.h"

#include "shaders_gen/plane_desktop_fs.h"
#endif

float FArcadePlane::Damp(float InRate, float InDeltaTime)
{
    return 1.0f - expf(-InRate * InDeltaTime);
}

FArcadePlane::FArcadePlane()
    : Position(Vector3{ 0.0f, 120.0f, 220.0f })
    , Yaw(3.14159265f)
    , Pitch(-0.08f)
    , Roll(0.0f)
    , Throttle(0.6f)
    , Speed(60.0f)
    , PropAngle(0.0f)
    , UnitCube({ 0 })
    , CustomModel({ 0 })
    , PlaneShader({ 0 })
    , SunDirLoc(-1)
    , CamPosLoc(-1)
    , CustomScale(1.0f)
    , CustomCenter({ 0.0f, 0.0f, 0.0f })
    , bModelsReady(false)
    , bHasCustomModel(false)
    , bShaderReady(false)
    , StickRoll(0.0f)
    , PitchRateSm(0.0f)
    , YawRateSm(0.0f)
{
}

void FArcadePlane::BuildModels()
{
    if (bModelsReady)
    {
        return;
    }
    UnitCube = LoadModelFromMesh(GenMeshCube(1.0f, 1.0f, 1.0f));
    bModelsReady = (UnitCube.meshCount > 0);

    PlaneShader = LoadShaderFromMemory(kPlaneVS, kPlaneFS);
    if (PlaneShader.id > 0)
    {
        PlaneShader.locs[SHADER_LOC_MAP_ALBEDO] = GetShaderLocation(PlaneShader, "texture0");
        SunDirLoc = GetShaderLocation(PlaneShader, "uSunDirLoc");
        CamPosLoc = GetShaderLocation(PlaneShader, "uViewDirLoc");
        bShaderReady = true;
    }
}

void FArcadePlane::UnloadModels()
{
    if (bHasCustomModel)
    {
        UnloadModel(CustomModel);
        CustomModel = { 0 };
        bHasCustomModel = false;
    }
    if (bShaderReady)
    {
        UnloadShader(PlaneShader);
        PlaneShader = { 0 };
        bShaderReady = false;
    }
    if (bModelsReady)
    {
        UnloadModel(UnitCube);
        UnitCube = { 0 };
        bModelsReady = false;
    }
}

bool FArcadePlane::LoadPlaneModel(const char* InFilePath)
{
    if (InFilePath == nullptr || !FileExists(InFilePath))
    {
        return false;
    }
    const Model Candidate = LoadModel(InFilePath);
    if (Candidate.meshCount == 0)
    {
        return false;
    }

    // Normalize: uniform scale so the largest dimension spans kCustomMaxDim,
    // and record the bounds center so the model pivots about its middle.
    BoundingBox Bounds = { Vector3{ 0, 0, 0 }, Vector3{ 0, 0, 0 } };
    bool bFirst = true;
    for (int32_t Index = 0; Index < Candidate.meshCount; ++Index)
    {
        const BoundingBox MeshBox = GetMeshBoundingBox(Candidate.meshes[Index]);
        if (bFirst)
        {
            Bounds = MeshBox;
            bFirst = false;
        }
        else
        {
            Bounds.min.x = fminf(Bounds.min.x, MeshBox.min.x);
            Bounds.min.y = fminf(Bounds.min.y, MeshBox.min.y);
            Bounds.min.z = fminf(Bounds.min.z, MeshBox.min.z);
            Bounds.max.x = fmaxf(Bounds.max.x, MeshBox.max.x);
            Bounds.max.y = fmaxf(Bounds.max.y, MeshBox.max.y);
            Bounds.max.z = fmaxf(Bounds.max.z, MeshBox.max.z);
        }
    }
    const float SpanX = Bounds.max.x - Bounds.min.x;
    const float SpanY = Bounds.max.y - Bounds.min.y;
    const float SpanZ = Bounds.max.z - Bounds.min.z;
    const float MaxDim = fmaxf(SpanX, fmaxf(SpanY, SpanZ));
    if (MaxDim <= 0.001f)
    {
        UnloadModel(Candidate);
        return false;
    }

    if (bHasCustomModel)
    {
        UnloadModel(CustomModel);
    }
    CustomModel = Candidate;
    CustomScale = kCustomMaxDim / MaxDim;
    CustomCenter = Vector3{
        (Bounds.min.x + Bounds.max.x) * 0.5f,
        (Bounds.min.y + Bounds.max.y) * 0.5f,
        (Bounds.min.z + Bounds.max.z) * 0.5f
    };
    bHasCustomModel = true;

    // Realistic multi-material tuning
    if (CustomModel.materialCount > 0)
    {
        // Material 0: fuselage & wings - pure white tint for livery texture
        CustomModel.materials[0].maps[MATERIAL_MAP_DIFFUSE].color = WHITE;
    }
    if (CustomModel.materialCount > 1)
    {
        // cam (cockpit windows) - sleek dark tinted glass
        CustomModel.materials[1].maps[MATERIAL_MAP_DIFFUSE].color = Color{ 24, 30, 40, 255 };
    }
    if (CustomModel.materialCount > 2)
    {
        // kantuc (wingtips) - Atlasjet red
        CustomModel.materials[2].maps[MATERIAL_MAP_DIFFUSE].color = Color{ 216, 32, 32, 255 };
    }
    if (CustomModel.materialCount > 3)
    {
        // motor (engine cowlings) - aviation white
        CustomModel.materials[3].maps[MATERIAL_MAP_DIFFUSE].color = Color{ 242, 244, 246, 255 };
    }
    if (CustomModel.materialCount > 4)
    {
        // motor-metal (intake / exhaust / fan) - metallic chrome
        CustomModel.materials[4].maps[MATERIAL_MAP_DIFFUSE].color = Color{ 75, 80, 90, 255 };
    }
    if (CustomModel.materialCount > 5)
    {
        // aerodynamic trim - dark charcoal
        CustomModel.materials[5].maps[MATERIAL_MAP_DIFFUSE].color = Color{ 36, 38, 42, 255 };
    }

    if (bShaderReady)
    {
        for (int32_t i = 0; i < CustomModel.materialCount; ++i)
        {
            CustomModel.materials[i].shader = PlaneShader;
        }
    }

    // Auto-discover livery texture if present in filesystem
    const char* TexCandidates[] = {
        "/atlasjet.png",
        "/static/viewer/atlasjet-texture/atlasjet-white.png",
        "app/static/viewer/atlasjet-texture/atlasjet-white.png"
    };
    for (const char* Cand : TexCandidates)
    {
        if (FileExists(Cand))
        {
            LoadPlaneTexture(Cand);
            break;
        }
    }

    return true;
}

bool FArcadePlane::LoadPlaneTexture(const char* InFilePath)
{
    if (!bHasCustomModel || InFilePath == nullptr || !FileExists(InFilePath))
    {
        return false;
    }
    Texture2D Tex = LoadTexture(InFilePath);
    if (Tex.id == 0)
    {
        return false;
    }
    GenTextureMipmaps(&Tex);
    SetTextureFilter(Tex, TEXTURE_FILTER_BILINEAR);
    if (CustomModel.materialCount > 0)
    {
        CustomModel.materials[0].maps[MATERIAL_MAP_DIFFUSE].color = WHITE;
        SetMaterialTexture(&CustomModel.materials[0], MATERIAL_MAP_DIFFUSE, Tex);
        if (bShaderReady)
        {
            CustomModel.materials[0].shader = PlaneShader;
        }
    }
    return true;
}

void FArcadePlane::Spawn(const FTerrainRenderer* InTerrain)
{
    float GroundY = FWorldDressing::kWaterLevelY;
    if (InTerrain != nullptr)
    {
        GroundY = InTerrain->GetGroundHeightOr(0.0f, 60.0f, GroundY);
    }
    Position = Vector3{ 0.0f, GroundY + 70.0f, 220.0f };
    Yaw = 3.14159265f;
    Pitch = -0.08f;
    Roll = 0.0f;
    Throttle = 0.6f;
    Speed = kMinSpeed + (kMaxSpeed - kMinSpeed) * Throttle;
    StickRoll = 0.0f;
    PitchRateSm = 0.0f;
    YawRateSm = 0.0f;
}

Vector3 FArcadePlane::GetForward() const
{
    return Vector3{
        cosf(Pitch) * sinf(Yaw),
        sinf(Pitch),
        cosf(Pitch) * cosf(Yaw)
    };
}

void FArcadePlane::GetBodyQuat(float& OutX, float& OutY, float& OutZ, float& OutW) const
{
    // Yaw about world Y, then pitch, then roll — matches GetForward exactly.
    const FQuat Qy = QuatFromAxisAngle(0.0f, 1.0f, 0.0f, Yaw);
    const FQuat Qx = QuatFromAxisAngle(1.0f, 0.0f, 0.0f, -Pitch);
    const FQuat Qz = QuatFromAxisAngle(0.0f, 0.0f, 1.0f, Roll);
    const FQuat Q = QuatMul(Qy, QuatMul(Qx, Qz));
    OutX = Q.X; OutY = Q.Y; OutZ = Q.Z; OutW = Q.W;
}

Vector3 FArcadePlane::RotateOffset(const Vector3& InOffset) const
{
    float Qx, Qy, Qz, Qw;
    GetBodyQuat(Qx, Qy, Qz, Qw);
    return QuatRotate(FQuat{ Qx, Qy, Qz, Qw }, InOffset);
}

void FArcadePlane::GetModelAxisAngle(Vector3& OutAxis, float& OutAngleDeg) const
{
    float Qx, Qy, Qz, Qw;
    GetBodyQuat(Qx, Qy, Qz, Qw);
    const FQuat QBody = { Qx, Qy, Qz, Qw };
    const FQuat QAlign = QuatFromAxisAngle(0.0f, 1.0f, 0.0f, kModelAlignYaw);
    const FQuat Q = QuatMul(QBody, QAlign);

    const float ClampedW = fminf(fmaxf(Q.W, -1.0f), 1.0f);
    const float S = sqrtf(fmaxf(1.0f - ClampedW * ClampedW, 0.0f));
    if (S < 1e-4f)
    {
        OutAxis = Vector3{ 0.0f, 1.0f, 0.0f };
        OutAngleDeg = 0.0f;
    }
    else
    {
        OutAxis = Vector3{ Q.X / S, Q.Y / S, Q.Z / S };
        OutAngleDeg = 2.0f * acosf(ClampedW) * kDegPerRad;
    }
}

void FArcadePlane::Update(float InDeltaTime, const FTerrainRenderer* InTerrain)
{
    const float Dt = fmaxf(InDeltaTime, 0.0001f);

    // --- Throttle spool (no jumps) ---
    float ThrottleTarget = Throttle;
    if (IsKeyDown(KEY_W)) ThrottleTarget += 1.0f;
    if (IsKeyDown(KEY_S)) ThrottleTarget -= 1.0f;
    if (IsKeyDown(KEY_SPACE)) ThrottleTarget += 1.0f;
    if (IsKeyDown(KEY_C) || IsKeyDown(KEY_LEFT_CONTROL)) ThrottleTarget -= 1.0f;
    // Net rate toward the held direction; spool lag comes from speed below.
    const float ThrottleRate = 0.55f;
    if (ThrottleTarget > Throttle) Throttle = fminf(Throttle + ThrottleRate * Dt, 1.0f);
    if (ThrottleTarget < Throttle) Throttle = fmaxf(Throttle - ThrottleRate * Dt, 0.0f);
    Throttle = std::clamp(Throttle, 0.0f, 1.0f);

    const float TargetSpeed = kMinSpeed + (kMaxSpeed - kMinSpeed) * Throttle;
    Speed += (TargetSpeed - Speed) * Damp(1.1f, Dt);

    // --- Bank stick with fast attack, airframe lag on the response ---
    float RollCommand = 0.0f;
    if (IsKeyDown(KEY_A) || IsKeyDown(KEY_LEFT)) RollCommand -= 1.0f;
    if (IsKeyDown(KEY_D) || IsKeyDown(KEY_RIGHT)) RollCommand += 1.0f;
    StickRoll += (RollCommand - StickRoll) * Damp(10.0f, Dt);
    const float TargetRoll = StickRoll * kMaxBank;
    Roll += (TargetRoll - Roll) * Damp(2.6f, Dt);

    // --- Pitch/heading rates, smoothed (mouse + arrows share one path) ---
    float PitchRateTarget = 0.0f;
    float YawRateTarget = 0.0f;
    if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) || IsMouseButtonDown(MOUSE_BUTTON_RIGHT))
    {
        // Pixel deltas are per-frame; divide by dt for true angular rates.
        const Vector2 MouseDelta = GetMouseDelta();
        YawRateTarget += -MouseDelta.x * kMouseYawSens / Dt;
        PitchRateTarget += -MouseDelta.y * kMousePitchRate / Dt;
    }
    if (IsKeyDown(KEY_UP)) PitchRateTarget += kArrowPitchRate;
    if (IsKeyDown(KEY_DOWN)) PitchRateTarget -= kArrowPitchRate;
    PitchRateSm += (PitchRateTarget - PitchRateSm) * Damp(7.0f, Dt);
    YawRateSm += (YawRateTarget - YawRateSm) * Damp(7.0f, Dt);

    Yaw += YawRateSm * Dt;
    Pitch = std::clamp(Pitch + PitchRateSm * Dt, -0.7f, 0.7f);

    // Coordinated banked turn: yaw follows roll; faster flight turns wider.
    const float TurnAuthority = 1.0f * (1.0f - 0.45f * (Speed / kMaxSpeed));
    Yaw -= Roll * TurnAuthority * Dt;

    // --- Integrate ---
    const Vector3 Forward = GetForward();
    Position = Vector3Add(Position, Vector3Scale(Forward, Speed * Dt));

    FWorldDressing::ClampToWorld(Position);
    if (Position.y > 600.0f) Position.y = 600.0f;
    if (InTerrain != nullptr)
    {
        const float FloorY = InTerrain->GetGroundHeightOr(Position.x, Position.z, FWorldDressing::kWaterLevelY)
            + kGroundClearance;
        if (Position.y < FloorY)
        {
            Position.y = FloorY;
            Pitch = std::max(Pitch, 0.05f);
            Speed = std::max(Speed * 0.985f, kMinSpeed * 0.6f);
        }
    }

    PropAngle += Dt * (6.0f + 30.0f * Throttle);
}

void FArcadePlane::GetChasePose(Vector3& OutCamPos, Vector3& OutCamTarget) const
{
    const Vector3 Forward = GetForward();
    const Vector3 Right = Vector3Normalize(Vector3{ -Forward.z, 0.0f, Forward.x });
    const float Distance = 17.0f + Speed * 0.06f;
    OutCamPos = Vector3Add(Position, Vector3Scale(Forward, -Distance));
    OutCamPos.y += 5.5f;
    OutCamPos = Vector3Add(OutCamPos, Vector3Scale(Right, Roll * 2.0f));
    OutCamTarget = Vector3Add(Position, Vector3Scale(Forward, 30.0f));
}

void FArcadePlane::Draw(const Vector3& InCameraPos, const FTerrainRenderer* InTerrain) const
{
    float Qx, Qy, Qz, Qw;
    GetBodyQuat(Qx, Qy, Qz, Qw);

    if (bShaderReady)
    {
        const Vector3 WorldSun = Vector3Normalize(Vector3{ 0.55f, 0.75f, 0.35f });
        const Vector3 WorldView = Vector3Normalize(Vector3Subtract(InCameraPos, Position));
        const FQuat InvBodyQ = { -Qx, -Qy, -Qz, Qw };
        const Vector3 LocalSun = QuatRotate(InvBodyQ, WorldSun);
        const Vector3 LocalView = QuatRotate(InvBodyQ, WorldView);
        if (SunDirLoc >= 0) SetShaderValue(PlaneShader, SunDirLoc, &LocalSun, SHADER_UNIFORM_VEC3);
        if (CamPosLoc >= 0) SetShaderValue(PlaneShader, CamPosLoc, &LocalView, SHADER_UNIFORM_VEC3);
    }

    // Dynamic ground shadow
    if (InTerrain != nullptr)
    {
        const float GroundY = InTerrain->GetGroundHeightOr(Position.x, Position.z, FWorldDressing::kWaterLevelY);
        const float Alt = Position.y - GroundY;
        if (Alt > 0.5f && Alt < 300.0f)
        {
            const float ShadowRadius = fminf(fmaxf(3.5f + Alt * 0.03f, 3.5f), 12.0f);
            const float AlphaNorm = 1.0f - (Alt / 300.0f);
            const unsigned char Alpha = (unsigned char)(AlphaNorm * AlphaNorm * 110.0f);
            if (Alpha > 5)
            {
                DrawCircle3D(Vector3{ Position.x, GroundY + 0.15f, Position.z },
                             ShadowRadius, Vector3{ 1.0f, 0.0f, 0.0f }, 90.0f,
                             Color{ 12, 16, 22, Alpha });
            }
        }
    }

    if (bHasCustomModel)
    {
        Vector3 Axis = { 0.0f, 1.0f, 0.0f };
        float AngleDeg = 0.0f;
        GetModelAxisAngle(Axis, AngleDeg);
        const Vector3 Recenter = QuatRotate(FQuat{ Qx, Qy, Qz, Qw }, Vector3{
            -CustomCenter.x * CustomScale,
            -CustomCenter.y * CustomScale,
            -CustomCenter.z * CustomScale
        });
        const Vector3 DrawPos = Vector3Add(Position, Recenter);
        DrawModelEx(CustomModel, DrawPos, Axis, AngleDeg,
                    Vector3{ CustomScale, CustomScale, CustomScale }, WHITE);
        return;
    }

    if (!bModelsReady)
    {
        return;
    }

    const Vector3 YawAxis = { 0.0f, 1.0f, 0.0f };
    const float YawDeg = Yaw * kDegPerRad;

    // Realistic light-aircraft livery: white body, grey trim, red fin.
    const FPart Parts[] = {
        { Vector3{ 0.0f, 0.0f, 0.0f },   Vector3{ 1.6f, 1.6f, 6.5f }, Color{ 235, 236, 240, 255 } },
        { Vector3{ 0.0f, 0.35f, 1.2f },  Vector3{ 1.2f, 0.9f, 2.2f }, Color{ 120, 150, 170, 255 } },
        { Vector3{ 0.0f, -0.1f, 0.6f },  Vector3{ 11.0f, 0.25f, 1.8f }, Color{ 228, 229, 233, 255 } },
        { Vector3{ 0.0f, 0.2f, -3.1f },  Vector3{ 4.4f, 0.2f, 1.1f }, Color{ 200, 202, 208, 255 } },
        { Vector3{ 0.0f, 1.0f, -3.1f },  Vector3{ 0.25f, 2.0f, 1.2f }, Color{ 178, 34, 34, 255 } },
        { Vector3{ 0.0f, 0.0f, 3.35f },  Vector3{ 0.5f, 0.5f, 0.5f }, Color{ 40, 42, 48, 255 } },
    };

    for (const FPart& Part : Parts)
    {
        const Vector3 WorldCenter = Vector3Add(Position, RotateOffset(Part.Offset));
        DrawModelEx(UnitCube, WorldCenter, YawAxis, YawDeg, Part.Size, Part.Tint);
    }

    const Vector3 BladeCenter = Vector3Add(Position, RotateOffset(Vector3{ 0.0f, 0.0f, 3.55f }));
    const Vector3 SpinAxis = GetForward();
    DrawModelEx(UnitCube, BladeCenter, SpinAxis, PropAngle * kDegPerRad,
                Vector3{ 0.35f, 3.4f, 0.15f }, Color{ 40, 42, 48, 255 });
}

void FArcadePlane::Draw() const
{
    Draw(Vector3{ 0.0f, 100.0f, 0.0f }, nullptr);
}
