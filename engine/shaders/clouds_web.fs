precision highp float;
uniform vec2 uResolution;
uniform vec3 uCamPos;
uniform vec3 uCamForward;
uniform vec3 uCamUp;
uniform vec3 uCamRight;
uniform vec3 uSunDir;
uniform float uTanFov;
uniform float uAspect;
uniform float uTime;
uniform float uCloudBase;
uniform float uCloudTop;

float hash31(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
}

float noise3D(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
    float n000 = hash31(i);
    float n100 = hash31(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash31(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash31(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash31(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash31(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash31(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash31(i + vec3(1.0, 1.0, 1.0));
    return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
               mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
}

float fbmBase(vec3 p) {
    float v = noise3D(p) * 0.55;
    v += noise3D(p * 2.05 + 0.15) * 0.30;
    v += noise3D(p * 4.10 + 0.35) * 0.15;
    return v;
}

float sampleDensity(vec3 pos, float yMin, float yMax, float time) {
    float h = clamp((pos.y - yMin) / (yMax - yMin), 0.0, 1.0);
    if (h <= 0.0 || h >= 1.0) return 0.0;
    
    // Smooth marshmallow profile: gentle ramp base, billowy round crown
    float heightProfile = smoothstep(0.0, 0.20, h) * (1.0 - smoothstep(0.68, 1.0, h));
    
    vec3 wind = vec3(time * 0.018, 0.0, time * 0.007);
    vec3 p = (pos * 0.0026) + wind;
    
    float shape = fbmBase(p);
    float coverage = 0.48;
    float d = shape - coverage;
    if (d <= 0.0) return 0.0;
    
    return smoothstep(0.0, 0.22, d) * heightProfile * 2.6;
}

bool intersectSlab(vec3 ro, vec3 rd, float yMin, float yMax, out float tEnter, out float tExit) {
    if (abs(rd.y) < 1e-4) {
        if (ro.y >= yMin && ro.y <= yMax) {
            tEnter = 0.0;
            tExit = 1500.0;
            return true;
        }
        return false;
    }
    float t1 = (yMin - ro.y) / rd.y;
    float t2 = (yMax - ro.y) / rd.y;
    float tNear = min(t1, t2);
    float tFar = max(t1, t2);
    
    if (ro.y >= yMin && ro.y <= yMax) {
        tEnter = 0.0;
        tExit = min(max(t1, t2), 1500.0);
        return tExit > 0.0;
    }
    if (tFar < 0.0) return false;
    tEnter = max(tNear, 0.0);
    tExit = min(tFar, 1500.0);
    return tExit > tEnter;
}

void main() {
    vec2 uv = gl_FragCoord.xy / uResolution;
    vec2 ndc = uv * 2.0 - 1.0;
    vec3 rd = normalize(uCamForward + uCamRight * (ndc.x * uAspect * uTanFov) + uCamUp * (ndc.y * uTanFov));
    
    float tEnter = 0.0;
    float tExit = 0.0;
    if (!intersectSlab(uCamPos, rd, uCloudBase, uCloudTop, tEnter, tExit)) {
        gl_FragColor = vec4(0.0);
        return;
    }
    
    // Smooth subtle dither without grainy noise
    float dither = (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.30 + 0.5;
    int kSteps = 32;
    float stepSize = (tExit - tEnter) / float(kSteps);
    float t = tEnter + dither * stepSize;
    
    vec3 sunDir = normalize(uSunDir);
    float cosTheta = dot(rd, sunDir);
    // Soft sunny forward scatter without specular metal shine
    float sunGlint = pow(max(cosTheta, 0.0), 3.0) * 0.30;
    
    float transmittance = 1.0;
    vec3 cloudColor = vec3(0.0);
    
    for (int i = 0; i < 32; ++i) {
        if (t > tExit || transmittance < 0.015) break;
        vec3 p = uCamPos + rd * t;
        float d = sampleDensity(p, uCloudBase, uCloudTop, uTime);
        if (d > 0.001) {
            float sunD = sampleDensity(p + sunDir * 22.0, uCloudBase, uCloudTop, uTime) +
                         sampleDensity(p + sunDir * 50.0, uCloudBase, uCloudTop, uTime);
            
            // Soft light penetration (never drops into dark charcoal!)
            float sunLight = exp(-sunD * 0.20);
            
            // Pure luminous white palette:
            // Underbelly shadow is 92% bright soft cloud-white
            // Sunlit face is 100% brilliant radiant cotton-white
            vec3 shade = mix(vec3(0.92, 0.95, 0.99), vec3(1.0, 1.0, 1.0), sunLight);
            shade += vec3(1.0, 0.98, 0.94) * sunGlint;
            
            vec3 S = shade;
            float stepExt = exp(-d * stepSize * 0.024);
            cloudColor += S * (1.0 - stepExt) * transmittance;
            transmittance *= stepExt;
        }
        t += stepSize;
    }
    
    float alpha = clamp(1.0 - transmittance, 0.0, 1.0);
    gl_FragColor = vec4(cloudColor, alpha);
}
