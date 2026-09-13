#version 330
in vec3 vertexPosition;
uniform mat4 mvp;
out vec3 vWorldPos;
void main() {
    vWorldPos = vertexPosition;
    gl_Position = mvp * vec4(vertexPosition, 1.0);
}
