precision mediump float;
varying vec2 fragTexCoord;
varying vec4 fragColor;
varying vec3 fragNormal;
varying vec3 fragWorldPos;
uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform int uRenderMode;
uniform int uPlainWhite;
uniform vec3 uCamPos;
uniform float uFogStart;
uniform float uFogEnd;
uniform vec3 uHazeColor;
void main() {
    vec4 baseColor = fragColor;
    if (uRenderMode == 0) {
        vec4 texColor = (uPlainWhite != 0) ? vec4(1.0) : texture2D(texture0, fragTexCoord);
        // Accept the texel only if it carries real color: guards against
        // missing UVs / broken sampling that would paint the mesh black.
        if (texColor.a > 0.003 && dot(texColor.rgb, vec3(0.3333)) > 0.004) {
            baseColor = texColor;
        }
    }
    vec3 tint = (colDiffuse.r + colDiffuse.g + colDiffuse.b > 0.01) ? colDiffuse.rgb : vec3(1.0);
    vec3 norm = normalize(fragNormal);
    vec3 sunDir = normalize(vec3(0.55, 0.75, 0.35));
    vec3 viewDir = normalize(uCamPos - fragWorldPos);
    vec3 halfVec = normalize(sunDir + viewDir);
    float diff = max(dot(norm, sunDir), 0.0);
    float slopeAO = clamp(norm.y * 0.65 + 0.35, 0.25, 1.0);
    vec3 skyAmbient = vec3(0.34, 0.39, 0.46) * slopeAO;
    vec3 sunDirect = vec3(1.10, 1.06, 0.95) * diff;
    float isSnowOrHigh = step(40.0, fragWorldPos.y) * step(0.4, norm.y);
    float specPow = mix(20.0, 72.0, isSnowOrHigh);
    float specIntensity = mix(0.12, 0.45, isSnowOrHigh);
    float spec = pow(max(dot(norm, halfVec), 0.0), specPow) * specIntensity * diff;
    vec3 specularLight = vec3(1.0, 0.98, 0.92) * spec;
    vec3 finalRgb = (baseColor.rgb * (skyAmbient + sunDirect) * tint) + specularLight;
    float fogF = smoothstep(uFogStart, uFogEnd, distance(fragWorldPos, uCamPos));
    finalRgb = mix(finalRgb, uHazeColor, fogF);
    gl_FragColor = vec4(finalRgb, 1.0);
}
