#version 330 core
in vec2 v_uv;
in vec3 v_col;
in vec3 v_col2;
flat in vec4 v_p0;
flat in vec4 v_p1;
flat in vec2 v_p2;

uniform float u_time;
uniform int   u_calib;      // 1 = plain white strips + endpoint markers (alignment on the wall)

out vec4 frag;

const float TAU = 6.2831853;

void main() {
    float len = max(v_p1.y, 1.0);
    float hw  = max(v_p2.x, 0.5);
    float u   = v_uv.x;

    // Distance to the segment in half-widths, with round caps past the ends
    float over = max(max(-u, u - 1.0), 0.0) * len / hw;
    float d    = length(vec2(over, v_uv.y));
    float core = smoothstep(1.0, 0.55, d);
    float glow = exp(-d * 1.4) * 0.45;

    if (u_calib == 1) {
        float ends = len / hw;     // marker radius ≈ 3 half-widths
        float ma = smoothstep(3.0, 2.0, length(vec2(u * ends, v_uv.y)));
        float mb = smoothstep(3.0, 2.0, length(vec2((u - 1.0) * ends, v_uv.y)));
        vec3 c = vec3(core) + vec3(1.0, 0.1, 0.1) * ma + vec3(0.1, 1.0, 0.2) * mb;
        frag = vec4(c, clamp(max(c.r, max(c.g, c.b)), 0.0, 1.0));
        return;
    }

    float uu    = clamp(v_p1.w > 0.5 ? 1.0 - u : u, 0.0, 1.0);
    int   fx    = int(v_p0.x + 0.5);
    float val   = v_p0.y;
    float spd   = v_p0.z;
    float inten = v_p0.w;
    float phase = v_p1.x;
    float since = v_p1.z;
    vec3  col   = v_col;
    float b     = 0.0;

    if (fx == 0) {                      // Pulse
        b = 0.06 + val * 1.2;
    } else if (fx == 1) {               // Chase: dashes travelling along the strip
        float n = max(len / (hw * 8.0), 1.0);
        float x = fract(uu * n - u_time * spd * 1.5 - phase * n);
        float dash = smoothstep(0.5, 0.15, abs(x - 0.5));
        b = dash * (0.15 + val * 1.3);
        col = mix(v_col, v_col2, x);
    } else if (fx == 2) {               // VU: fills with the band, bright tip
        float lvl = clamp(val, 0.0, 1.0);
        float edge = hw * 2.0 / len;
        float fill = smoothstep(lvl + edge, lvl - edge, uu);
        float tip  = exp(-abs(uu - lvl) * len / (hw * 3.0)) * step(0.02, lvl);
        b = fill * 0.75 + tip * 1.4;
        col = mix(v_col, v_col2, smoothstep(0.6, 1.0, uu));
    } else if (fx == 3) {               // Comet: a spark crosses the strip on each kick
        float head = since * spd * 1.5 - phase;
        float live = step(0.0, head) * (1.0 - smoothstep(1.0, 1.35, head));
        float behind = uu <= head ? exp(-(head - uu) * 5.0) : exp(-(uu - head) * len / hw * 0.4);
        b = behind * live * 1.6 + 0.04 + val * 0.15;
        col = mix(v_col, v_col2, exp(-abs(head - uu) * 25.0));
    } else if (fx == 4) {               // Strobe on kick (phase delays it → ripple)
        float t = since - phase * 0.25;
        b = step(0.0, t) * exp(-max(t, 0.0) * 12.0) * 1.6;
        col = mix(v_col, v_col2, 0.3);
    } else {                            // Flow: scrolling two-colour gradient
        float x = fract(uu * 1.5 - u_time * spd * 0.3 - phase);
        col = mix(v_col, v_col2, 0.5 + 0.5 * sin(x * TAU));
        b = 0.2 + val * 1.1;
    }

    vec3 c = col * b * inten;
    vec3 outc = c * (core + glow) + vec3(max(b * inten - 1.0, 0.0)) * core * 0.6;
    frag = vec4(outc, clamp(max(outc.r, max(outc.g, outc.b)), 0.0, 1.0));
}
