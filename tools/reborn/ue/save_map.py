import os, sys
import unreal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reborn_common import *  # noqa
require_map()
print("saved", unreal.EditorLoadingAndSavingUtils.save_map(world(), MAP))
