presidents-and-assholes
=======================

Server, client, and client GUI to play the Presidents and Assholes card game over a network.

Todo
---

Features:
- 6 Out of turn play handling in GUI
- 5 Make server crash proof
- 4 Validate messages (Regular expressions)
- 2 Implement chand
- 2 Name mangling
- 3 First hand starts with 3 of clubs
- 1 Start players in lobby instead of at table
- 1 Lobby limit

Bugs:
- Server crashing when unitialized clients disconnect
+ Email to prevent having to wait for os to free socket
+ server 230: len(hands) != len(players_at_table)
- Cleanup code
