"""Writes the Atlas Park expansion test block as a CoH map file (game feet).
The avenue (6_strt at x 1024..1152) continues north from the old War Wall
door at z=1024 to a 4-lane T-junction at z 1664..1792, with buildings on
both sides, props, ruins at the old wall line and a temporary War Wall."""
import kit, math, random
from coh2unreal import maplayout as ml
store, lib, ex = kit.load()
random.seed(7)
groups = []          # (def path, pos, pyr)
def add(name, x, y, z, yaw=0.0):
    groups.append((name, (x, y, z), (0.0, yaw, 0.0)))
def world_box(name, yaw):
    lo, hi, _n, miss = kit.bounds(lib, ex, name)
    assert not miss, (name, miss)
    m = ml.mat_from_pyr((0, 0, 0), (0, yaw, 0))
    xs, zs = [], []
    for lx in (lo[0], hi[0]):
        for lz in (lo[2], hi[2]):
            xs.append(lx * m[0][0] + lz * m[2][0]); zs.append(lx * m[0][2] + lz * m[2][2])
    return min(xs), max(xs), min(zs), max(zs), hi[1]
WEST_EDGE, EAST_EDGE = 1022.0, 1154.0
def building(name, yaw, side, zmin):
    x0, x1, z0, z1, h = world_box(name, yaw)
    px = (WEST_EDGE - x1) if side == "w" else (EAST_EDGE - x0)
    pz = zmin - z0
    add(name, px, 0, pz, yaw)
    print("%-24s %s yaw %4d  x %6.0f..%6.0f  z %6.0f..%6.0f  h %4.0f" % (name, side, yaw, px + x0, px + x1, pz + z0, pz + z1, h))
    return pz + z1
# --- road: 3 x 6_strt, 6->4 lanes, T-junction with two 4-lane arms each way
for z in (1152, 1280, 1408):
    add("Streets/road_6lane/6_strt", 1152, 0, z)
add("Streets/road_4lane/4_4to6", 1024, 0, 1664, 180)
add("Streets/road_4lane/4_3way", 1024, 0, 1664, 180)
for x in (768, 896, 1152, 1280):
    add("Streets/road_4lane/4_strt", x, 0, 1664, 90)
road = {(1024, z) for z in range(1024, 1665, 128)} | {(x, 1664) for x in (768, 896, 1152, 1280)}
# --- ground: road filler under every other cell of the pocket
for cx in range(512, 1664, 128):
    for cz in range(1024, 1793, 128):
        if (cx, cz) not in road:
            add("Streets/road_filler/Filler_sidewlk", cx + 128, 0, cz + 128)
# --- buildings. West side faces +x (east), east side faces -x (west).
z = building("FillerShop_A", 180, "w", 1066)                 # Filler_Shops
z = building("ind_ware_08_ware_final", -90, "w", z + 8)        # warehouses
z = building("Deco1", 0, "w", z + 8)                           # deco (new style)
z = building("OT_House_lrg", 90, "w", z + 8)                   # Oldtown (new style)
z = building("ind_ware_07_final", 0, "e", 1066)                # warehouses
z = building("deco_skyscraper_14", 0, "e", z + 8)              # Upgraded_Deco
z = building("FillerShop_C", 0, "e", z + 8)                    # Filler_Shops
z = building("FillerShop_J", 0, "e", z + 8)                    # Filler_Shops
# back row, for a skyline behind the street fronts
add("Buildings/Style/warehouses/ind_ware_12_final", 1520, 0, 1230, 0)
add("FLRN_BUILDING_B", 760, 0, 1500, 0)   # Filler_Buildings, behind the deco tower
# --- parking lots behind the street fronts, with parking lamps and cars
cars = ["parked_compact", "parked_sport2", "parked_lux1", "parked_sport1", "parked_lux2"]
def lot(x0, x1, z0, z1):
    for lx, lz in ((x0 + 20, z0 + 20), (x1 - 20, z1 - 20), (x0 + 20, z1 - 20), (x1 - 20, z0 + 20)):
        add("Streets/Elements/lights/streetlights/Lamp_Parkinglot_01", lx, 0, lz, random.choice((0, 90, 180, 270)))
    for row_x in (x0 + 45, x1 - 45):
        zz = z0 + 40
        while zz < z1 - 40:
            if random.random() < 0.7:
                add(random.choice(cars), row_x, 0.1, zz, 90 if row_x < (x0 + x1) / 2 else -90)
            zz += 12
lot(560, 780, 1090, 1290)
lot(1330, 1440, 1440, 1640)
# --- sidewalk props on both curbs
for zz in range(1170, 1530, 64):
    add("common_decor/Slums_&_Wastes/trash/TrashCan_bag", 1029, 0, zz + 6)
    add("common_decor/Slums_&_Wastes/trash/TrashCan_bag", 1147, 0, zz + 38)
    add("city_zones/Atlas_Park_makeover/AP_Planter_01", 1030, 0, zz + 30)
    add("city_zones/Atlas_Park_makeover/AP_Planter_01", 1146, 0, zz + 2)
# --- ruins along the old wall line (z ~1024) and closed T-junction arms
add("WstRbl_Lg_cnr_chunks_a", 905, 0, 1040, 180)
add("WstRbl_Lg_cnr_chunks_a", 1270, 0, 1040, 90)
add("WstRbl_Xlg_hlf_chunk_a", 700, 0, 1060, 180)
add("WstRbl_Lg_hlf_chunk_b", 1470, 0, 1060, 0)
for x, zz, yaw in ((1036, 1036, 20), (1060, 1044, 75), (1118, 1030, 160), (1140, 1050, 300), (960, 1070, 45), (1215, 1065, 210)):
    add("RUIN_WALL_CHUNKS", x, 0, zz, yaw)
for x, zz, n in ((1060, 1030, "Ruin_Pot_Hole_Decal_07"), (1110, 1050, "Ruin_Pot_Hole_Decal_03"), (1090, 1075, "Ruin_Stain_XLg"), (1045, 1095, "Ruin_Stain_Lg")):
    add(n, x, 0.05, zz, random.uniform(0, 360))
add("Rn_Compact", 990, 0, 1050, 30)
for x in (780, 1396):
    for dz in (-36, -12, 12, 36):
        add("Ruined_Concrete_Barrier_0%d" % random.randint(1, 3), x, 1.5, 1728 + dz, 90)
# --- temporary War Wall closing the pocket: back wall + two sides
for x in (704, 1088, 1472):
    add("Walls/warzone_walls/warwall_base/WarWall_base_straight", x, 0, 1856)
    add("Walls/warzone_walls/warwall_shield/WarWall_shield_straight", x, 512, 1856)
for zz in (1216, 1600, 1664):
    for x, yaw in ((512, 90), (1664, -90)):
        add("Walls/warzone_walls/warwall_base/WarWall_base_straight", x, 0, zz, yaw)
        add("Walls/warzone_walls/warwall_shield/WarWall_shield_straight", x, 512, zz, yaw)
with open("data/maps/expansion/atlas_expansion_block.txt", "w") as f:
    f.write("# Atlas Park expansion test block (generated by gen_block.py)\n\nDef grp_Expansion\n")
    for name, (x, y, z), (p, yw, r) in groups:
        f.write("\tGroup %s\n\t\tPYR %g %g %g\n\t\tPos %g %g %g\n\tEnd\n" % (name, p, yw, r, x, y, z))
    f.write("End\n\nRef grp_Expansion\n\tPos 0 0 0\nEnd\n")
print("groups:", len(groups))
