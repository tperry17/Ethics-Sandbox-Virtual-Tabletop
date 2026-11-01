# Facilitating from a Mac on the local network

Run `scripts/deploy.sh` on the Mac. It prints the address other devices use
and sets `SANDBOX_PUBLIC_URL` from it, so every invite link carries that
address, not `localhost`.

- **Keep the lid open and the charger in.** `caffeinate -i` (which the
  script runs) stops idle sleep, not sleep when the lid is closed.
- **Test the network beforehand.** Campus and guest Wi-Fi often stop devices
  from reaching one another. If tablets cannot reach the Mac, use a phone
  hotspot or a router of your own.
- **If the Mac's address changes** (a new network, or a router restart),
  press Ctrl-C and run `scripts/deploy.sh` again, then share the new
  address. Tables are restored from their snapshots and open browsers
  reconnect on their own.
- **Check `/health` from one tablet before the class arrives**:
  `http://<the Mac's address>:8000/health`. If it opens, that device can
  reach the table.
- **Copying the invite link.** The link is shown as text beside the button.
  Over plain `http` browsers have no clipboard access, so the button selects
  the text and says "Press Ctrl-C or Cmd-C".
