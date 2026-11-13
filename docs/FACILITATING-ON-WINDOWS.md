# Facilitating from a Windows desktop

The server runs in WSL2 (Ubuntu inside Windows) and reaches the internet
through a Cloudflare quick tunnel, which gives it an `https://` address
anyone can open. The address is new every time the tunnel starts, so each
session gets fresh links. Nothing here needs a Cloudflare account, a domain
or any change to the router.

`cloudflared` is installed inside Ubuntu, not on Windows, so it is separate
from any tunnel already set up on the Windows side.

## Once: set up the desktop

1. In PowerShell, run as administrator, install WSL2 with Ubuntu, then
   restart when asked and choose a Linux user name and password:

   ```
   wsl --install -d Ubuntu
   ```

2. In the Ubuntu terminal, install git, curl and the GitHub CLI:

   ```
   sudo apt update && sudo apt install -y git curl gh
   ```

   If apt cannot find `gh`, install it from cli.github.com instead.

3. Install Node.js 22 (the version CI uses) with nvm; the commands are on
   nodejs.org's download page under Linux. Ubuntu's own `nodejs` package is
   too old for the client build.

4. Install uv, then close and reopen the terminal:

   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

5. Install `cloudflared` from Cloudflare's release page:

   ```
   curl -LO https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared-linux-amd64.deb
   ```

6. The repository is private, so sign git in to GitHub. Choose GitHub.com,
   HTTPS, "Yes" to authenticating git with your GitHub credentials, and
   logging in with a web browser; it shows a code to enter in the browser.
   `deploy.sh` fetches `main` at every start and uses this login.

   ```
   gh auth login
   ```

7. Clone the project into the Linux home folder, not under `/mnt/c/`.
   Files on the Windows drive are slow from WSL, and the live SQLite
   database should not sit on a drive Windows also syncs or scans.

   ```
   cd ~ && gh repo clone HolyTispoon/Ethics-Sandbox-Virtual-Tabletop
   ```

8. In Windows Settings, under Power, set the screen and sleep to "Never"
   while plugged in. A sleeping desktop drops every table.

## Each session

1. Open Ubuntu and run:

   ```
   cd ~/Ethics-Sandbox-Virtual-Tabletop && scripts/serve-tunnel.sh
   ```

   It opens the tunnel, prints `Tunnel address: https://….trycloudflare.com`,
   then updates to the latest `main`, runs the checks, builds and serves.
   Add `--skip-checks` to start faster.

2. Open `<tunnel address>/health` on a phone using mobile data (not the
   home Wi-Fi). If it says "You can reach the server", the address works
   from outside. It can take a minute after the tunnel opens.

3. Open a room from an exercise page and share its invite link. The link
   carries the tunnel address. Ignore the `localhost` and local-network
   addresses `deploy.sh` also prints: they work only in the house.

4. Leave the Ubuntu window open for the whole session. Ctrl-C stops the
   server and the tunnel; the address then stops working.

## If something goes wrong

- **The tunnel or the desktop restarted mid-session.** Run
  `scripts/serve-tunnel.sh` again and send the new address. Rooms and tables
  are kept, so people can reach theirs by entering its code under "Join a
  room" at the new address, but they join as new participants: their old
  seat and hand stay with the old address.
- **Windows Update.** Set active hours, or pause updates, around a session;
  a forced restart stops the server.
- **Too many people.** A quick tunnel answers at most 200 requests at once.
  Whether each open table counts towards that has not been measured.
