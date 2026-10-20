// Custom node body for M_CoH_WindowGlass "InteriorRoom" (pasted in by build_glass_material.py).
// Furnished fake interiors from City Sample's own room captures:
//   Rooms1/FG1C/FG1D = TCA_1x1x1_Rooms + T2A_1x1x1_CaptureFG/DepthFG (15 slices, one-pane rooms)
//   Rooms2/FG2C/FG2D = TCA_2x2x1_Rooms + T2A_2x2x1_CaptureFG/DepthFG (11 slices, wide rooms)
// One room spans RoomWidth panes x RoomHeight panes (one floor); width is re-rolled per floor.
// Returns rgb = room colour (tonemapped for base colour), a = 1 when this room's lights are on at night.

float2 g = UV * Panes;                              // pane grid: x across, y down the facade
float rh = max(RoomH, 1.0);
float row = floor(g.y / rh);
float2 hr = frac(sin(float2(row * 12.9898 + Seed * 7.131, row * 78.233 + Seed * 3.719)) * 43758.5453);
float w = clamp(floor(lerp(WMin, WMax + 0.999, hr.x)), 1.0, 4.0);
float gx = g.x + floor(hr.y * w);                   // stagger room walls between floors
float col = floor(gx / w);
float2 lp = frac(float2(gx / w, g.y / rh));         // position on this room's window wall, 0..1, y down
float4 h = frac(sin(float4(col * 12.9898 + row * 78.233, col * 39.346 + row * 11.135,
                           col * 73.156 + row * 52.235, col * 94.673 + row * 17.497) + Seed * 1.618 + Theme * 3.3) * 43758.5453);
float emptyRow = step(frac(hr.x * 91.7 + hr.y * 13.1), EmptyFrac);
bool wide = w >= 2.0;
int t = (int)round(Theme);                          // 0 office, 1 residential, 2 retail

float idx;
if (!wide) {
    if (t == 1)      { const float L[5] = {0, 1, 2, 3, 4};       idx = L[min((int)(h.x * 5), 4)]; }  // bedrooms, living rooms
    else if (t == 2) { const float L[4] = {9, 10, 11, 12};       idx = L[min((int)(h.x * 4), 3)]; }  // shops, restaurant
    else             { const float L[6] = {5, 6, 7, 8, 5, 7};    idx = L[min((int)(h.x * 6), 5)]; }  // offices
    if (emptyRow > 0.5) idx = (t == 1) ? 0 : 13;    // bare floor: lobby / sparse bedroom, no clutter
} else {
    if (t == 1)      { const float L[3] = {0, 1, 2};             idx = L[min((int)(h.x * 3), 2)]; }
    else if (t == 2) { const float L[2] = {7, 8};                idx = L[min((int)(h.x * 2), 1)]; }
    else             { const float L[5] = {3, 4, 5, 6, 3};       idx = L[min((int)(h.x * 5), 4)]; }  // open plan, meeting rooms
    if (emptyRow > 0.5) idx = (t == 1) ? 2 : 9;
}

float3 v = normalize(V);                            // tangent space, z towards the camera
if (h.z < 0.5) { lp.x = 1.0 - lp.x; v.x = -v.x; }   // random mirror

// ---- room box (City Sample captures: 1x1x1, or 2 wide x 1 tall x 2 deep) ----
float3 B = wide ? float3(1.0, 0.5, Depth) : float3(1.0, 1.0, Depth);
float3 o = float3((lp.x * 2 - 1) * B.x, (1 - lp.y * 2) * B.y, B.z);
float3 d = -v;
d.y = -d.y;
d.z = min(d.z, -1e-3);
float3 sd = float3(d.x >= 0 ? 1 : -1, d.y >= 0 ? 1 : -1, -1);
float3 tt = (sd * B - o) / d;
float3 hit = o + min(min(tt.x, tt.y), tt.z) * d;
float3 dir = float3(-hit.z, hit.x, hit.y);          // tangent (right, up, out) -> capture space
for (int r = 0; r < (int)Yaw; r++) dir = float3(-dir.y, dir.x, dir.z);
float mip = clamp(log2(max(PixelDepth, 1.0) / max(MipDist, 1.0)), 0.0, 7.0);
SamplerState cs = View.MaterialTextureBilinearClampedSampler;
float3 room = wide ? Rooms2.SampleLevel(cs, float4(dir, idx), mip).rgb
                   : Rooms1.SampleLevel(cs, float4(dir, idx), mip).rgb;

// ---- foreground furniture/curtain layer: depth-slab raymarch like City Sample's M_Window ----
if (emptyRow < 0.5) {
    float2 uvOut = lp;
    float a = 0;
    float2 par = v.xy * float2(1, 1) / max(v.z, 0.05) * Depth;
    for (int i = 0; i < (int)Steps; i++) {
        float hh = (i + 0.5) / Steps;
        float2 uc = lp + par * (-1 + hh);
        float2 slab = wide ? FG2D.SampleLevel(cs, float3(uc, idx), mip).xy : FG1D.SampleLevel(cs, float3(uc, idx), mip).xy;
        if (hh > 1 - slab.y && hh < slab.x && all(uc > 0) && all(uc < 1)) { uvOut = uc; a = 1; }
    }
    float3 fg = wide ? FG2C.SampleLevel(cs, float3(uvOut, idx), mip).rgb : FG1C.SampleLevel(cs, float3(uvOut, idx), mip).rgb;
    room = lerp(room, fg, a);
}

float lit = (emptyRow < 0.5 && h.y < LitFrac) ? 1.0 : 0.0;
float3 c = room * Bright;
c = c / (1 + c);                                    // HDR capture -> base colour range
c *= lerp(0.55, 1.0, lit);                          // unlit rooms read darker by day too

// ---- blinds / curtains just behind the glass ----
if (frac(h.w * 7.31) < BlindsFrac) {
    float drop = lerp(0.15, 0.95, frac(h.w * 17.3));
    if (lp.y < drop) {
        float slat = 0.78 + 0.22 * sin(lp.y * rh * 6.2832 * 18);
        c = BlindsColor * slat;
        lit *= 0.35;
    }
}
return float4(c, lit);
