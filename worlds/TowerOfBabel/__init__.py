from . import components as components

# The main thing we do in our __init__.py is importing our world class from our world.py to initialize it.
# Obviously, this world class needs to exist first. For this, read world.py.
from .world import TowerOfBabelWorld as TowerOfBabelWorld
