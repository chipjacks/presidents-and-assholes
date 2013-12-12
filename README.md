presidents-and-assholes
=======================

Server, client, and curses text-based GUI to play the Presidents and
Assholes (aka Warlords and Scumbags) card game over the network.

Todo
---

Features:
- 3 Out of turn play handling in GUI
- x Make server crash proof
+ x Validate messages (Regular expressions)
+ x Implement chand
+ x Name mangling
+ x First hand starts with 3 of clubs
+ x Start players in lobby instead of at table
+ x Lobby limit
- Finish command line parameters

Bugs:
+ x Server crashing when unitialized clients disconnect
+ x Email to prevent having to wait for os to free socket
+ x server 230: len(hands) != len(players_at_table)

Other:
- Cleanup code
- Check on swapping no cards
