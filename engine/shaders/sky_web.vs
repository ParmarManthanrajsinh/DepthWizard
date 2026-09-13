attribute vec3 vertexPosition;
uniform mat4 mvp;
varying vec3 vDir;
void main() {
    vDir = vertexPosition;
    gl_Position = mvp * vec4(vertexPosition, 1.0);
}
