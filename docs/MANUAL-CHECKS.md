# Manual checks

Things that cannot be automated; check them by hand before a real session.

- **Network**: open `/health` from a tablet on the same Wi-Fi as the Mac.
- **Invite link**: on a tablet over `http://<LAN IP>`, press "Copy invite
  link"; the link is selected and "Press Ctrl-C or Cmd-C" appears.
- **Restart mid-session**: Ctrl-C the server, run `scripts/deploy.sh`; open
  tables come back as they were and reconnect without a reload.
