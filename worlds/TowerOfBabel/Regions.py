from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Entrance, Region

if TYPE_CHECKING:
    from .world import APQuestWorld


def create_and_connect_regions(world: TowerOfBabelWorld) -> None:
    create_all_regions(world)


def create_all_regions(world: TowerOfBabelWorld) -> None:
    overworld = Region("Overworld", world.player, world.multiworld)
    regions = [overworld]
    world.multiworld.regions += regions