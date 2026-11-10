"""Who is around the hero in the play world: combat enemies (with their state)
and any other actors with a skeletal mesh (layout previews, crowd, props)."""
import unreal

w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
hero = unreal.GameplayStatics.get_player_pawn(w, 0)
radius = float(globals().get("GS_RADIUS", 6000.0))
enemies = unreal.GameplayStatics.get_all_actors_of_class(w, unreal.CoHCombatEnemy)
print("combat enemies within %.0f m:" % (radius / 100))
for e in enemies:
    d = e.get_distance_to(hero)
    if d > radius:
        continue
    p = e.get_editor_property("powers")
    print("  %-28s %-34s hp %4.0f side %s dead %s state %s mesh %s" % (
        e.get_name(), e.get_editor_property("villain"), p.get_editor_property("health"),
        "hero" if p.get_editor_property("b_player_side") else "foe", e.is_dead(),
        e.get_editor_property("state"), e.get_editor_property("kit_model") or "old catalog"), round(d / 100), "m")
others = {}
for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Actor):
    if isinstance(a, unreal.CoHCombatEnemy) or a == hero:
        continue
    if a.get_distance_to(hero) > radius:
        continue
    if a.get_components_by_class(unreal.SkeletalMeshComponent):
        cls = a.get_class().get_name()
        others.setdefault(cls, []).append(a.get_name())
print("other actors with skeletal meshes:")
for cls, names in sorted(others.items(), key=lambda kv: -len(kv[1])):
    print("  %4d %s  e.g. %s" % (len(names), cls, names[:3]))
