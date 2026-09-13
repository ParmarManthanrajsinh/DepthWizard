precision highp float;
varying vec3 vWorldPos;
uniform vec3 uCamPos;
uniform float uTime;
uniform float uFogStart;
uniform float uFogEnd;
uniform vec3 uHazeColor;

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += vec2(dot(p, p + 45.32));
    return fract(p.x * p.y);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (vec2(3.0) - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// Animated caustic webbing: interfering wave sets sharpened into thin lines.
// ~1.4 m cells; scroll keeps the pattern dancing over the sand.
float caustic(vec2 p, float t) {
    vec2 q = p * 1.35 + vec2(t * 0.9, t * 0.65);
    float a = sin(q.x * 3.0 + t * 0.9) + sin(q.y * 3.4 - t * 1.1) + sin((q.x + q.y) * 2.2 + t * 0.6);
    return pow(1.0 - abs(a / 3.0), 8.0);
}

void main() {
    vec2 p = vWorldPos.xz;
    float distC = distance(vWorldPos, uCamPos);
    float detailFade = 1.0 - smoothstep(150.0, 450.0, distC);

    // Caribbean sand with fine grain
    float grain = vnoise(p * 1.4) * 0.5 + vnoise(p * 4.2) * 0.5;
    vec3 sand = vec3(0.84, 0.79, 0.58) * (0.92 + grain * 0.16);

    // Gentle large dunes shading
    float dunes = vnoise(p * 0.02 + vec2(3.7));
    sand *= 0.94 + dunes * 0.12;

    // Sunlit caustic webbing dancing on the sand
    float ca = caustic(p, uTime);
    sand += vec3(1.0, 0.98, 0.92) * ca * 0.38 * detailFade;

    // Falloff to deep-sea abyss away from the island shelf
    float shoreDist = length(p);
    vec3 abyss = vec3(0.04, 0.14, 0.28);
    vec3 col = mix(sand, abyss, smoothstep(200.0, 700.0, shoreDist));

    // Distance fog: melts the far edge fully into the horizon haze (matches water).
    float fogF = smoothstep(uFogStart, uFogEnd, distC);
    col = mix(col, uHazeColor, fogF);

    gl_FragColor = vec4(col, 1.0);
}
