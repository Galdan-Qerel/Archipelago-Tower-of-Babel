import os
import sys

# Get the directory where ap_client.py is located
client_dir = os.path.dirname(os.path.abspath(__file__))
# Get the world root (TowerOfBabel/)
world_root = os.path.dirname(os.path.dirname(client_dir))
# Get the Archipelago root (where 'worlds/' resides)
archipelago_root = os.path.dirname(os.path.dirname(world_root))

# Add the Archipelago root to sys.path so 'import Utils' works everywhere
if archipelago_root not in sys.path:
    sys.path.insert(0, archipelago_root)

# Corrected Imports
import Utils
from typing import Callable, Optional, Any
from worlds.LauncherComponents import Component, SuffixIdentifier, components, Type, launch_subprocess
from worlds.AutoWorld import World
# ... rest of your imports
from .Data import item_table, location_table, event_table, region_table, category_table
from .Game import game_name
from .Items import item_name_to_id
from .Locations import location_name_to_id
from .Regions import create_regions
from .Rules import set_rules

class ManualWorld(World):
    game = game_name
    topology_present = True
    
    # Add these mandatory class variables
    item_name_to_id = item_name_to_id
    item_id_to_name = {v: k for k, v in item_name_to_id.items()}
    location_name_to_id = location_name_to_id
    location_id_to_name = {v: k for k, v in location_name_to_id.items()}

    def create_regions(self):
        create_regions(self.multiworld, self.player)

    def set_rules(self):
        set_rules(self.multiworld, self.player)

###
# Integrated Client Launch Logic
###


###
# Integrated Client Launch Logic
###

###
# Integrated Client Launch Logic
###

###
# Integrated Client Launch Logic
###

def run_client(*args):
    import sys
    import subprocess
    
    # If the secret flag is present, we are inside the newly popped terminal window!
    # It is safe to run the actual client code now.
    if "--run-now" in args:
        import asyncio
        from worlds.TowerOfBabel.client import ap_client
        try:
            asyncio.run(ap_client.main())
        except Exception:
            import traceback
            traceback.print_exc()
            input("\nPress Enter to close this window...")
            
    # If the flag is NOT present, we were clicked from the GUI.
    # Pop a new black terminal window and call this component again with the secret flag.
    else:
        cmd = [sys.executable, "TowerOfBabelClient", "--run-now"]
        if sys.platform == "win32":
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(cmd)

components.append(Component("Tower of Babel Client", "TowerOfBabelClient", func=run_client))