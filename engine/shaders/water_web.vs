attribute vec3 vertexPosition;
uniform mat4 mvp;
uniform float uTime;
varying vec3 vWorldPos;
varying vec3 vNormalW;
varying float vCrest;
void swell(vec2 p, vec2 dir, float amp, float len, float t, inout vec3 disp, inout vec2 grad) {
    vec2 D = normalize(dir);
    float k = 6.2831853 / len;
    float s = sqrt(9.81 * k);
    float f = k * dot(D, p) - s * t;
    disp.y += amp * sin(f);
    grad += D * (k * amp * cos(f));
}
void main() {
    vec2 p = vertexPosition.xz;
    vec3 disp = vec3(0.0);
    vec2 grad = vec2(0.0);
    swell(p, vec2(0.85, 0.4), 0.08, 115.0, uTime, disp, grad);
    swell(p, vec2(-0.65, 0.76), 0.05, 61.0, uTime, disp, grad);
    vNormalW = normalize(vec3(-grad.x, 1.0, -grad.y));
    vCrest = clamp(disp.y / 0.13, -1.0, 1.0);
    vec3 wp = vertexPosition + disp;
    vWorldPos = wp;
    gl_Position = mvp * vec4(wp, 1.0);
}
