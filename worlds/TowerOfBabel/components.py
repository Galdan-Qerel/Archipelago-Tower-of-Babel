from worlds.LauncherComponents import Component, components, Type, launch
from .Game import game_name

def run_client(*args: str) -> None:
    from .client.launch import launch_tower_of_babel_client
    launch(launch_tower_of_babel_client, name="Tower of Babel Client", args=args)

components.append(Component(
    "Tower of Babel Client", 
    "TowerOfBabelClient", 
    func=run_client, 
    game_name=game_name 
))