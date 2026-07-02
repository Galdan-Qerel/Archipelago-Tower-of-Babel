import sys
import os

# Path injection for core modules
archipelago_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
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

def launch_tower_of_babel_client():
    # Launches the client as a clean, independent subprocess
    import sys
    launch_subprocess([sys.executable, "-m", "worlds.TowerOfBabel.client.ap_client"])

class VersionedComponent(Component):
    def __init__(self, display_name: str, script_name: Optional[str] = None, func: Optional[Callable] = None, version: int = 0, file_identifier: Optional[Callable[[str], bool]] = None, icon: Optional[str] = None):
        super().__init__(display_name=display_name, script_name=script_name, func=func, component_type=Type.CLIENT, file_identifier=file_identifier, icon=icon)
        self.version = version

def add_client_to_launcher() -> None:
    version = 2026_07_02 
    components.append(VersionedComponent(
        "Tower of Babel Client", 
        "TowerOfBabelClient", 
        func=launch_tower_of_babel_client, 
        version=version, 
        icon="manual"
    ))

add_client_to_launcher()