from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import TowerOfBabelWorld

def set_all_rules(world: "TowerOfBabelWorld") -> None:
    # Tell Archipelago that the player beats the game when they receive the Victory item
    world.multiworld.completion_condition[world.player] = lambda state: state.has("Victory", world.player)