Presidents-and-Assholes
=======================

Server, client, and curses text-based UI to play the Presidents and
Assholes (aka Warlords and Scumbags) card game over the network.

The client UI runs in your shell window, so in order to see the whole
interface, your shell window must have at least 100 columns and 50 rows before
your start the client. If the client crashes while the UI is running, use the
'reset' command to get your shell back to normal. 

Todo
---

Features:
- Out of turn play handling in UI
- x Make server crash proof
+ x Validate messages (Regular expressions)
+ x Implement chand
+ x Name mangling
+ x First hand starts with 3 of clubs
+ x Start players in lobby instead of at table
+ x Lobby limit
- x Finish command line parameters
- x Make sure server buffer doesn't overflow

Bugs:
+ x Server crashing when unitialized clients disconnect
+ x Email to prevent having to wait for os to free socket
+ x server 230: len(hands) != len(players_at_table)
- x Get ^ lined up properly in gui hand
- Deal with UI hand card overflow
- x One 2 beats anything
- x messages.py line 46 crash - leads to swaps bomb from server

Other:
- Check on swapping no cards
