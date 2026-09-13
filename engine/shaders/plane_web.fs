precision mediump float;
varying vec2 fragTexCoord;
varying vec3 fragNormal;
uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform vec3 uSunDirLoc;
uniform vec3 uViewDirLoc;
void main() {
    vec4 texCol = texture2D(texture0, fragTexCoord);
    vec4 baseColor = texCol * colDiffuse;
    vec3 norm = normalize(fragNormal);
    vec3 sunDir = normalize(uSunDirLoc);
    vec3 viewDir = normalize(uViewDirLoc);
    vec3 halfVec = normalize(sunDir + viewDir);
    float diff = max(dot(norm, sunDir), 0.0);
    vec3 ambient = vec3(0.36, 0.40, 0.46);
    vec3 direct = vec3(1.10, 1.06, 0.95) * diff;
    float spec = pow(max(dot(norm, halfVec), 0.0), 32.0) * 0.48 * diff;
    vec3 finalRgb = baseColor.rgb * (ambient + direct) + vec3(1.0, 1.0, 1.0) * spec;
    gl_FragColor = vec4(finalRgb, baseColor.a);
}
