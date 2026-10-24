"""PIE check for the game systems (run step by step with ue_exec.py):

  GS_STEP 'info'    level actors that matter (spawner, player start)
  GS_STEP 'start'   start Play In Editor
  GS_STEP 'spawn'   clear random groups, spawn a level 2 Hellions spray-paint encounter
  GS_STEP 'fight'   target the nearest Hellion and use tray slot GS_SLOT (default 0)
  GS_STEP 'state'   hero level / XP / influence / debt, villains alive, last CoH log lines
  GS_STEP 'stop'    end PIE
"""
import unreal

step = globals().get("GS_STEP", "info")
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def pie_world():
    for w in unreal.EditorLevelLibrary.get_pie_worlds(False) if hasattr(unreal.EditorLevelLibrary, "get_pie_worlds") else []:
        return w
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()


def actors(world, cls):
    return unreal.GameplayStatics.get_all_actors_of_class(world, cls)


if step == "info":
    acts = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    print([a.get_name() for a in acts if "Spawner" in a.get_class().get_name() or "PlayerStart" in a.get_class().get_name()][:10], len(acts))
elif step == "start":
    les.editor_play_simulate() if globals().get("GS_SIM") else les.editor_request_begin_play()
    print("requested PIE")
elif step == "spawn":
    w = pie_world()
    hero = unreal.GameplayStatics.get_player_pawn(w, 0)
    sp = actors(w, unreal.CoHEnemySpawner)
    if not sp:
        # no spawner placed in the loaded cells: summon one in the play world
        pc = unreal.GameplayStatics.get_player_controller(w, 0)
        unreal.SystemLibrary.execute_console_command(w, "summon CoHEnemySpawner", pc)
        sp = actors(w, unreal.CoHEnemySpawner)
    if not sp:
        raise RuntimeError("no CoHEnemySpawner in the play world")
    s = sp[0]
    s.set_spawning(False)
    ok = s.spawn_test_group(hero, "Hellions", int(globals().get("GS_LEVEL", 2)), float(globals().get("GS_DIST", 1500.0)), globals().get("GS_KIND", "spraypaint"))
    print("hero", hero.get_name(), hero.get_actor_location(), "spawned", ok)
    for e in actors(w, unreal.CoHCombatEnemy):
        p = e.get_editor_property("powers")
        print(" ", e.get_editor_property("villain"), "lvl", p.get_editor_property("level"), e.get_editor_property("kit_model"),
              e.get_editor_property("encounter_idle"), e.get_editor_property("thought"), round(e.get_distance_to(hero)))
elif step == "fight":
    w = pie_world()
    hero = unreal.GameplayStatics.get_player_pawn(w, 0)
    hp = hero.get_editor_property("powers")
    foes = sorted([e for e in actors(w, unreal.CoHCombatEnemy) if not e.is_dead()], key=lambda e: e.get_distance_to(hero))
    if foes:
        hp.set_target_actor(foes[0])
        hp.activate_slot(int(globals().get("GS_SLOT", 0)))
        print("target", foes[0].get_editor_property("villain"), round(foes[0].get_distance_to(hero)), "tray", [str(t) for t in hp.get_editor_property("tray")])
    else:
        print("no foes")
elif step == "state":
    w = pie_world()
    hero = unreal.GameplayStatics.get_player_pawn(w, 0)
    pr = hero.get_editor_property("progress")
    h = pr.get_editor_property("hero")
    hp = hero.get_editor_property("powers")
    print("hero", h.get_editor_property("name"), h.get_editor_property("class_"), "lvl", h.get_editor_property("level"), "xp", h.get_editor_property("xp"),
          "inf", h.get_editor_property("influence"), "debt", h.get_editor_property("debt"), "insp", [str(i) for i in h.get_editor_property("inspirations")],
          "hp", round(hp.get_editor_property("health")), "/", round(hp.get_editor_property("max_health")), "body", hero.get_editor_property("co_h_body_type"))
    for e in actors(w, unreal.CoHCombatEnemy):
        p = e.get_editor_property("powers")
        print(" ", e.get_editor_property("villain"), "hp", round(p.get_editor_property("health")), "dead", e.is_dead(), e.get_editor_property("thought"), round(e.get_distance_to(hero)))
elif step == "stop":
    les.editor_request_end_play()
    print("stop")
