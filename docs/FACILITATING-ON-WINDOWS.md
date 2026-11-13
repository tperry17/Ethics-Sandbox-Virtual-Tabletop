# Facilitating from a Windows desktop

The server runs directly on Windows and reaches the internet through a
Cloudflare quick tunnel, which gives it an `https://` address anyone can
open. The address is new every time the tunnel starts, so each session gets
fresh links. Nothing here needs a Cloudflare account, a domain or any change
to the router, and it runs beside any other Cloudflare tunnel the computer
already has.

`scripts\serve-tunnel.cmd` does everything: it updates to the latest
`main`, installs dependencies, runs the checks, builds the table client,
migrates its own database (`ethics-sandbox-live.db`), opens the tunnel and
serves. Rooms and the cookie secret (`.sandbox-secret`) are kept between
runs.

## Once: set up the computer

Open PowerShell (not as administrator) for all of these.

1. Install git, uv, Node.js and the GitHub CLI. Skip any you already have;
   `cloudflared` is already installed if another tunnel runs here.

   ```
   winget install --id Git.Git
   winget install --id astral-sh.uv
   winget install --id OpenJS.NodeJS.LTS
   winget install --id GitHub.cli
   winget install --id Cloudflare.cloudflared
   ```

   Close PowerShell and open it again so it finds them. uv fetches Python
   3.12 itself the first time it runs; nothing else needs Python.

2. The repository is private, so sign git in to GitHub. Choose GitHub.com,
   HTTPS, "Yes" to authenticating git with your GitHub credentials, and
   logging in with a web browser; it shows a code to enter in the browser.
   The script fetches `main` at every start and uses this login.

   ```
   gh auth login
   ```

3. Clone the project into your user folder. Keep it out of OneDrive,
   Dropbox and Google Drive: syncing the live database can corrupt it.

   ```
   cd $HOME
   gh repo clone tperry17/Ethics-Sandbox-Virtual-Tabletop
   ```

4. In Settings, System, Power, set sleep to "Never" while plugged in. The
   script keeps Windows awake while it runs, but a setting is the surer
   guard.

## Each session

1. Open PowerShell and run:

   ```
   cd $HOME\Ethics-Sandbox-Virtual-Tabletop
   .\scripts\serve-tunnel.cmd
   ```

   The first run takes several minutes. When it is ready it prints
   `Share this address: https://….trycloudflare.com`. Add `-SkipChecks`
   to start faster (`.\scripts\serve-tunnel.cmd -SkipChecks`).

2. Open `<address>/health` on a phone using mobile data (not the home
   Wi-Fi). If it says "You can reach the server", the address works from
   outside. It can take a minute after the tunnel opens.

3. Open a room from an exercise page and share its invite link. The link
   carries the tunnel address.

4. Leave the PowerShell window open for the whole session. Ctrl-C stops
   the server and the tunnel; the address then stops working.

## If something goes wrong

- **The checks fail.** Nobody had run them on Windows before this guide.
  Send the output to whoever maintains the project, and run with
  `-SkipChecks` meanwhile; the same checks pass on every pull request.
- **`test_the_card_files_are_up_to_date` fails, saying a card file is out
  of date.** The copy was cloned before the repository fixed its line
  endings (13 November 2026), so its files have Windows line endings. In
  the project folder, with no edits of your own to keep, run
  `git rm -r --cached -q .` and then `git reset --hard`; this rewrites the
  files with the repository's line endings.
- **"Port 8000 is already in use".** An earlier run is still open in
  another window: press Ctrl-C there or close it. Or serve on another port
  with `-Port 8001`.
- **The tunnel or the computer restarted mid-session.** Run the script
  again and send the new address. Rooms and tables are kept, so people can
  reach theirs by entering its code under "Join a room" at the new address,
  but they join as new participants: their old seat and hand stay with the
  old address.
- **cloudflared complains about a configuration file.** The other tunnel's
  settings may be getting in the way of the quick tunnel. Send the message
  to whoever maintains the project.
- **Windows Update.** Set active hours, or pause updates, around a
  session; a forced restart stops the server.
- **Too many people.** A quick tunnel answers at most 200 requests at once.
  Whether each open table counts towards that has not been measured.

On Linux, a Mac, or WSL, use `scripts/serve-tunnel.sh` instead; see the
README.
