import json
ENEMY_IMPORT_COSTUMES=set(json.load(open(r'C:\Users\rtcru\ClaudeProjects\COHReborn\atlas_enemy_remaining.json')))
ENEMY_IMPORT_LIMIT=5
exec(compile(open(r'C:\Users\rtcru\ClaudeProjects\COHReborn\atlas_enemy_import.py').read(),'atlas_enemy_import.py','exec'))
