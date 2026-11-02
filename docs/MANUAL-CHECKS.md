# Manual checks

Things that cannot be automated; check them by hand before a real session.

- **Network**: open `/health` from a tablet on the same Wi-Fi as the Mac.
- **Invite link**: on a tablet over `http://<LAN IP>`, press "Copy invite
  link"; the link is selected and "Press Ctrl-C or Cmd-C" appears.
- **Restart mid-session**: Ctrl-C the server, run `scripts/deploy.sh`; open
  tables come back as they were and reconnect without a reload.
- **iPad in Safari, portrait and landscape**: open a table, zoom in and pan,
  then rotate the iPad. The same part of the table stays in the middle.
- **Thumb reach**: with an iPad held in both hands, every card in a 12-card
  hand can be reached with a thumb, in both orientations.
- **On-screen keyboard**: tap the name field on the join page, and the
  "tables" and "minutes" fields in the class controls. The field stays visible
  above the keyboard while typing.
- **Phone (under 600 px wide)**: the join page says a tablet or laptop is
  better. At the table, your hand and the buttons work, and the public table
  can be panned and zoomed but its pieces cannot be dragged.
- **Screen reader (VoiceOver or NVDA)**: deals, accepted trades, votes, reveals,
  macros, joins and leaves are spoken. Dragging a piece is not.
- **Text at 200 percent**: zoom the browser to 200 percent on the join page,
  the help page and a table. Nothing is cut off or overlaps.
- **Held pieces on a dropped connection**: grab a card on one laptop and turn
  its Wi-Fi off for 5 seconds; on another laptop the card stays held, and is
  put down after 10 seconds. (Covered in code by tests/test_live.py.)
- **Colour**: with a colour-blindness simulator on, the six seats can still be
  told apart, and every seat also shows its name.
