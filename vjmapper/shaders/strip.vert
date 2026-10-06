#version 330 core
in vec2 in_pos;     // NDC
in vec2 in_uv;      // u along the strip (overflows past 0..1 for the caps), v across (|v| <= 1 = core)
in vec3 in_col;
in vec3 in_col2;
in vec4 in_p0;      // effect, band value, speed, intensity
in vec4 in_p1;      // phase, length (px), seconds since last kick, reverse
in vec2 in_p2;      // half width (px), unused

out vec2 v_uv;
out vec3 v_col;
out vec3 v_col2;
flat out vec4 v_p0;
flat out vec4 v_p1;
flat out vec2 v_p2;

void main() {
    v_uv = in_uv;
    v_col = in_col;
    v_col2 = in_col2;
    v_p0 = in_p0;
    v_p1 = in_p1;
    v_p2 = in_p2;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
