import unreal,json,math
sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
w=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert 'AtlasPark_CitySampleStudy' in w.get_path_name()
buildings=[a for a in sub.get_all_level_actors() if str(a.get_folder_path())=='Atlas25/Buildings']
results=[]
for a in buildings:
    o,e=a.get_actor_bounds(False)
    # Packed Blueprint bounds may include editor-only visualization; report component geometry too.
    row={'label':a.get_actor_label(),'location':[a.get_actor_location().x,a.get_actor_location().y,a.get_actor_location().z],'center':[o.x,o.y,o.z],'extent':[e.x,e.y,e.z]}
    results.append(row);print(row)
traces=[]
for z in range(1000,1641,40):
    x=1088*30.48;y=-z*30.48
    hit=unreal.SystemLibrary.line_trace_single(w,unreal.Vector(x,y,4000),unreal.Vector(x,y,-1000),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
    if hit:
        vals=hit.to_tuple();p=vals[4]; actor=vals[9] if len(vals)>9 else None
        traces.append({'feet':z,'hit':True,'height_cm':p.z,'actor':actor.get_actor_label() if isinstance(actor,unreal.Actor) else str(actor)})
    else:traces.append({'feet':z,'hit':False})
print('STREET_SURVEY',traces)
json.dump({'map':w.get_path_name(),'buildings':results,'street':traces},open('C:/Users/rtcru/ClaudeProjects/COHReborn/city_study_verification.json','w'),indent=2)
print('SAVE',unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True))
