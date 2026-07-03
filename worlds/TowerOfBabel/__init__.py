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

# Mandatory Archipelago Imports
import Utils
from typing import Callable, Optional, Any
from worlds.LauncherComponents import Component, components, Type, launch as launch_component
from worlds.AutoWorld import World

# Tower of Babel Game Imports
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
# Integrated GUI Client Launch Logic (APQuest Native Style)
###

def launch_tower_of_babel_client(*args: str):
    from .Client import launch 
    launch_component(launch, name="Tower of Babel Client", args=args)

# Append the component to the Launcher's GUI
components.append(Component(
    "Tower of Babel Client", 
    "TowerOfBabelClient", 
    func=launch_tower_of_babel_client, 
    game_name=game_name 
))