// Custom node body for M_CoH_WindowGlass "PaneMaskRecess" (pasted in by build_glass_material.py).
// Pane mask from a colour key of the original window texture (W/Thr/Soft/Inv) or, when UseTex > 0.5,
// from a hand-painted mask texture (R). Evaluated three times to fake a recessed window:
//   x = pane mask here
//   y = reveal: we are on glass, but the view ray, pushed RecessDepth (UV units) into the wall,
//       lands on frame -> show the dark side wall of the window opening instead of glass
//   z = sill shadow: the frame above (ShadowLen up the texture) shades the top of the pane
// Samples with SampleLevel and a distance-based mip so it also works in Nanite compute shading.
float mip = clamp(log2(max(PixelDepth, 1.0) / max(MipDist, 1.0)) + MipBias, 0.0, 6.0);
SamplerState ss = View.MaterialTextureBilinearWrapedSampler;
float3 v = normalize(V);
float2 off = -v.xy * float2(1, FlipY) / max(v.z, 0.25) * RecessDepth;
float2 uvs[3] = { UV, UV + off, UV - float2(0, ShadowLen) };
float m[3];
for (int i = 0; i < 3; i++) {
    float k;
    if (UseTex > 0.5) {
        k = MaskTex.SampleLevel(ss, uvs[i], mip).r;
    } else {
        float l = dot(WinTex.SampleLevel(ss, uvs[i], mip).rgb, W.rgb);
        k = saturate((l - Thr) / max(Soft, 1e-4));
        k = lerp(k, 1 - k, Inv);
    }
    m[i] = k;
}
float reveal = m[0] * (1 - m[1]) * step(1e-4, RecessDepth);
float shadow = m[0] * (1 - m[2]) * step(1e-4, ShadowLen);
return float4(m[0], reveal, shadow, 0);
