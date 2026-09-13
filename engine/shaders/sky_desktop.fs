#version 330
in vec3 vDir;
uniform vec3 uSunDir;
out vec4 finalColor;
vec3 aces(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}
void main() {
    vec3 d = normalize(vDir);
    vec3 zen = vec3(0.10, 0.38, 0.88);
    vec3 hor = vec3(0.68, 0.82, 0.94);
    vec3 col;
    if (d.y >= 0.0) {
        col = mix(hor, zen, pow(d.y, 0.55));
    } else {
        col = mix(hor, hor * 0.55, clamp(-d.y * 4.0, 0.0, 1.0));
    }
    vec3 sunDir = normalize(uSunDir);
    float s = max(dot(d, sunDir), 0.0);
    float disc = smoothstep(0.99935, 0.99965, s) * 4.0;
    float glow = pow(s, 600.0) * 1.2 + pow(s, 24.0) * 0.18;
    col += disc * vec3(1.0, 0.97, 0.92) + glow * vec3(1.0, 0.95, 0.85);
    col = aces(col * 1.15);
    col = pow(col, vec3(1.0 / 2.2));
    finalColor = vec4(col, 1.0);
}
