"""Material production uses bounded batches to release compilation memory.
Run atlas_overhaul_material_inventory.py in Unreal, then
atlas_overhaul_material_driver.py with workstation Python, then
atlas_overhaul_prefabs.py in Unreal for persistent packed-prefab materials.
The material_apply script is for temporary instance previews only.
"""
raise RuntimeError('Use the inventory / batch driver / prefab sequence.')
