# Tower of Babel - Archipelago Custom World

Tower of Babel is a unique, text-based "Companion Game" for the Archipelago Multiworld Randomizer. 

Instead of playing a standalone physical game, Tower of Babel runs in the background alongside your main game (e.g., *Ocarina of Time*, *Final Fantasy*, *StarCraft 2*). It intercepts the server's chat and scrambles the text into an unreadable cipher. As players locate "Character" items for the Babel slot hidden throughout the multiworld, letters are dynamically translated in real-time, slowly restoring the server's communication back to readable English.

## Features
* **Companion Architecture:** The client connects to your main game slot for normal gameplay while maintaining a secondary, hidden WebSocket connection to receive Babel translation items.
* **Native Integration:** Bypasses external command-prompt scripts. It runs natively inside the official Archipelago Graphical User Interface (GUI) using customized `PrintJSON` color nodes.
* **Ciphered Hint System:** Includes a built-in spoiler log parser. You can request hints for your main game's items, but the locations will be scrambled using your current Babel dictionary.
* **Dynamic Aesthetics:** Unlocked characters are highlighted in **Magenta**, while scrambled, unknown characters are randomized and highlighted in **Cyan**.

---

## Installation

1. Generate the `.apworld` file by running the builder command in your Archipelago directory:
   `python Launcher.py "Build APWorlds"`
2. Navigate to `build/apworlds/` and locate `manual_towerofbabel_galdan.apworld`.
3. Copy the `.apworld` file into your Archipelago `custom_worlds` folder.
4. Open the Archipelago Launcher. You will now see a button for the **Tower of Babel Multi-Client**.

---

## Quick Start Guide

Because this is a Companion Client, you must log in twice: once as your actual game, and once as the Babel translation slot.

1. **Launch the Client:** Click the `Tower of Babel Multi-Client` button in the Archipelago Launcher.
2. **Connect to the Server:** Type `/connect <server_address>` (e.g., `/connect archipelago.gg:38281`).
3. **Log into your Main Game:** When prompted for your slot name, enter the name of the **primary game** you are playing (e.g., `GaldanFF10`).
4. **Link the Babel Slot:** Once connected, start the background translation engine by typing:
   `/babel "<Your_Babel_Slot_Name>"`
   *(The client will confirm that it has connected in the background and will immediately download your starting characters).*

You are now ready to play! All incoming chat messages will be intercepted and scrambled based on your current inventory.

---

## Commands

The Tower of Babel client adds several custom commands to your Archipelago terminal:

### `/babel "<slot_name>" [password]`
Initializes the background WebSocket connection to the Tower of Babel slot. This must be run after connecting to your main game slot. 
* *Example:* `/babel "Babel_Player_1"`

### `/unlocked`
Displays a sorted list of all the translated characters/symbols you currently have in your Babel inventory.

### `/babelspoiler "<path_to_spoiler>"`
Configures the local path to the Multiworld's Spoiler Log. This is required to use the hint system. 
* *Example:* `/babelspoiler "C:\Archipelago\AP_Spoiler.txt"`

### `/babelhint <item name>`
Searches the configured spoiler log for an item belonging to your connected main slot. If found, it will print the location of that item into the chat, but the location text will be heavily scrambled by the Babel engine. 
* Supports fuzzy-matching, so you don't have to type the exact item name perfectly.
* *Example:* `/babelhint Master Sword`

---

## Gameplay Mechanics

* **Visual Colors:** If a character is scrambled and unreadable, it will appear as randomized text in Cyan. Once you receive the corresponding letter item from the multiworld, that character will automatically reveal itself in Magenta. 
* **Real-time Updates:** When a party member finds a Babel item for you, the client will immediately flash a yellow/magenta alert on your screen: `[Babel] Data Translated! You can now read the character: X`, and all future chat messages will update instantly.
* **Hints:** Use the `/babelhint` command strategically. Even if you only have a few vowels unlocked, you might be able to decipher enough of the scrambled hint to figure out where your most important items are hidden!

## Planned Future Features
* **Options for Tower:** Enable/Disable the different kinds of characters Letters Only, Letters+Numbers, Letters+Numbers+Symbols
* **Pokemon Crystal Unown Hunt intergration:** Instead of using the Babel manual, a /johto command would allow the use of unown dex to fill in for letters only mode
* **Final Fantasy X integration"** Letters only mode that goes off your found Al Bhed ciphers (and might force a static Al Bhed cipher)
* **Cipher Mode Toggle:** An optional "Codebreaker" mode that replaces the pure-random text scrambling with a persistent substitution cipher. This would allow dedicated players to manually decipher the language using context clues before they find the actual items.
* **Native Hint Integration:** Bypassing the need for a local spoiler log by hooking the scrambling engine directly into Archipelago's native `!hint` system.
* **Visual Tracker GUI:** Adding a dedicated visual grid to the Archipelago launcher window that displays the alphabet and illuminates symbols as they are unlocked, replacing the need to type `/unlocked`.