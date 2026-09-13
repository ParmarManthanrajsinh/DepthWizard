precision highp float;
varying vec3 vWorldPos;
varying vec3 vNormalW;
varying float vCrest;
uniform vec3 uCamPos;
uniform vec3 uSunDir;
uniform float uTime;
uniform vec3 uSkyTop;
uniform vec3 uSkyHorizon;
uniform vec3 uDeepColor;
uniform vec3 uShallowColor;
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

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 3; i++) {
        v += a * vnoise(p);
        p *= 2.03;
        a *= 0.5;
    }
    return v;
}

void main() {
    vec2 p = vWorldPos.xz;
    float distC = distance(vWorldPos, uCamPos);
    float detailFade = 1.0 - smoothstep(150.0, 450.0, distC);

    // Domain-warped micro-ripples from non-harmonic trigonometric waves
    vec2 p2 = p + fbm(p * 0.04) * 18.0;
    float r1 = sin(p2.x * 0.31 + p2.y * 0.19 + uTime * 0.6);
    float r2 = cos(-p2.x * 0.23 + p2.y * 0.37 + uTime * 0.5);
    float r3 = sin(p2.x * 0.47 - p2.y * 0.11 + uTime * 0.7);
    vec3 rippleNorm = vec3(r1 - r2, 0.0, r1 + r3) * 0.012 * detailFade;
    vec3 N = normalize(vNormalW + rippleNorm);

    vec3 V = normalize(uCamPos - vWorldPos);
    vec3 L = normalize(uSunDir);

    float shoreDist = length(p);
    float radialT = 1.0 - smoothstep(120.0, 650.0, shoreDist);
    float analytic = (1.0 - smoothstep(170.0, 210.0, shoreDist)) * smoothstep(130.0, 160.0, shoreDist);
    float shallowT = clamp(radialT * 0.85 + analytic * 0.5, 0.0, 1.0);
    vec3 body = mix(uDeepColor, uShallowColor, shallowT);

    vec3 R = reflect(-V, N);
    vec3 skyRef = mix(uSkyHorizon * 0.5, uSkyTop * 0.6, pow(clamp(R.y, 0.0, 1.0), 0.55));
    float rs = max(dot(R, L), 0.0);
    skyRef += (smoothstep(0.99935, 0.99965, rs) * 1.5 + pow(rs, 500.0) * 0.5 + pow(rs, 24.0) * 0.07) * vec3(1.0, 0.96, 0.88);

    float fres = clamp(0.02 + 0.98 * pow(1.0 - max(dot(N, V), 0.0), 5.0), 0.0, 0.35);
    vec3 col = mix(body, skyRef, fres);

    vec3 H = normalize(V + L);
    float ndh = max(dot(N, H), 0.0);
    col += min(pow(ndh, 400.0) * 0.6, 1.0) * detailFade * vec3(1.0, 0.97, 0.92);
    col += pow(ndh, 24.0) * 0.05 * vec3(1.0, 0.95, 0.85);

    float lap = 0.5 + 0.5 * sin(uTime * 0.45 - shoreDist * 0.18);
    float shoreFoam = smoothstep(0.30, 0.55, analytic + vCrest * 0.25) * smoothstep(0.35, 0.65, fbm(p * 0.05 + vec2(uTime * 0.15, uTime * 0.1)) * 0.7 + lap * 0.3);
    float crestFoam = smoothstep(0.15, 0.45, vCrest) * smoothstep(0.5, 0.8, fbm(p * 0.22 + vec2(uTime * 0.4))) * detailFade;
    // Whitecap fields: large wind-advected foam patches, visible at distance.
    // Streaked along the swell direction (0.85, 0.4), drifting with time.
    vec2 swellDir = vec2(0.85, 0.4);
    vec2 swellPerp = vec2(-swellDir.y, swellDir.x);
    float along = dot(p, swellDir) - uTime * 4.0;
    float across = dot(p, swellPerp);
    float patch = fbm(vec2(along * 0.030, across * 0.085));
    float caps = smoothstep(0.60, 0.70, patch + vCrest * 0.15);
    float foamM = clamp(shoreFoam + crestFoam + caps, 0.0, 1.0);
    col = mix(col, vec3(0.98, 0.99, 1.0), foamM * 1.0);

    // Distance fog: melts the far edge fully into the horizon haze.
    float fogF = smoothstep(uFogStart, uFogEnd, distC);
    col = mix(col, uHazeColor, fogF);

    // Real transparency over the seabed: clear looking down near the camera,
    // reflective/opaque at grazing angles and toward the horizon. Foam is solid.
    float alpha = clamp(0.45 + foamM * 0.55 + fres * 0.9 + smoothstep(150.0, 650.0, distC) * 0.5, 0.0, 1.0);
    gl_FragColor = vec4(col, alpha);
}
