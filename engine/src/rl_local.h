#pragma once

// Minimal rlgl declarations needed by the water depth-prepass.
// Signatures and attachment enum values verified against rlgl v6.0
// (raysan5/raylib, src/rlgl.h). Linked from raylib's rlgl module —
// no extra library or include path required.

#if defined(__cplusplus)
extern "C" {
#endif

extern unsigned int rlLoadTexture(const void* data, int width, int height, int format, int mipmapCount);
extern unsigned int rlLoadTextureDepth(int width, int height, bool useRenderBuffer);
extern unsigned int rlLoadFramebuffer(void);
extern void rlFramebufferAttach(unsigned int id, unsigned int texId, int attachType, int texType, int mipLevel);
extern bool rlFramebufferComplete(unsigned int id);
extern void rlUnloadTexture(unsigned int id);
extern void rlUnloadFramebuffer(unsigned int id);
extern void rlEnableFramebuffer(unsigned int id);
extern void rlDisableFramebuffer(void);
extern void rlViewport(int x, int y, int width, int height);
extern void rlDisableDepthTest(void);
extern void rlEnableDepthTest(void);
extern void rlDisableDepthMask(void);
extern void rlEnableDepthMask(void);
extern void rlSetClipPlanes(double nearPlane, double farPlane);
extern void rlSetUniformSampler(int locIndex, unsigned int textureId);

#if defined(__cplusplus)
}
#endif

// Framebuffer attachment points/types (rlgl values — do not renumber).
enum
{
    RL_LOCAL_ATTACH_COLOR0 = 0,
    RL_LOCAL_ATTACH_DEPTH = 100,
    RL_LOCAL_ATTACH_TEX2D = 100
};
