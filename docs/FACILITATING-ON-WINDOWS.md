# Facilitating from a Windows desktop

The server runs directly on Windows and reaches the internet through a
Cloudflare tunnel, which gives it an `https://` address anyone can open.
The usual set-up is a named tunnel on your own domain, set up once (step 5
below): the address is the same every session, invite links keep working,
and people who come back reclaim their seat. Until it is set up, or with
`-Quick`, the script falls back to a quick tunnel, whose address is new
every time and which needs no Cloudflare account or domain. Neither needs
any change to the router, and either runs beside any other Cloudflare
tunnel the computer already has.

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

5. Set up the permanent address: a named tunnel. It needs a Cloudflare
   account (the free plan is enough) and a domain whose DNS Cloudflare
   manages.

   1. In the Cloudflare dashboard, under Networking, Tunnels, choose
      "Create a tunnel" and give it a name of its own (for example
      `ethics-sandbox`). Don't reuse the tunnel this computer already
      runs. Choose Windows as the operating system; Cloudflare shows an
      install command ending in a long token. Copy it, but don't run it,
      since the script starts the tunnel itself.
   2. On the tunnel's Routes tab, choose "Add route", then "Published
      application": a subdomain (for example `sandbox`), your domain, and
      Service URL `http://localhost:8000`. Cloudflare makes the DNS
      record.
   3. In PowerShell, in the project folder:

      ```
      .\scripts\serve-tunnel.cmd -SetUpNamedTunnel
      ```

      Paste the address (`https://sandbox.example.org`) and then the token
      (pasting the whole install command works too). They are saved in
      `.sandbox-tunnel-url` and `.sandbox-tunnel-token` in the project
      folder, which git ignores. Anyone holding the token can serve on
      that address, so keep the folder off shared drives; if the token
      leaks, refresh it in Cloudflare and run this step again.

   From then on every start uses that address. Add `-Quick` for a quick
   tunnel instead, for one start; delete the two files to stop using the
   named tunnel. The dashboard renames these screens from time to time;
   the steps are the same under the new names.

## Each session

1. Start the server and the tunnel, in either of two ways.

   - **From VS Code:** open the project folder itself (File, Open Folder,
     the folder that holds `scripts`), then Terminal, Run Task, "Serve the
     Ethics Sandbox". "Serve the Ethics Sandbox (skip checks)" starts
     faster. The task runs in its own terminal panel.
   - **From PowerShell:**

     ```
     cd $HOME\Ethics-Sandbox-Virtual-Tabletop
     .\scripts\serve-tunnel.cmd
     ```

     Add `-SkipChecks` to start faster
     (`.\scripts\serve-tunnel.cmd -SkipChecks`).

   The first run takes several minutes. When it is ready it prints
   `Share this address: https://…`, your named tunnel's address. If step 5
   has not been done, it is a new `….trycloudflare.com` address instead.

2. Open `<address>/health` on a phone using mobile data (not the home
   Wi-Fi). If it says "You can reach the server", the address works from
   outside. It can take a minute after the tunnel opens.

3. Open a room from an exercise page and share its invite link. The link
   carries the tunnel address.

4. Leave the window (or VS Code) open for the whole session. Click in its
   terminal and press Ctrl-C to stop the server and the tunnel. A quick
   tunnel's address then stops working for good; a named tunnel's answers
   again at the next start.

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
- **Starting it stops an earlier run.** If the script (or the VS Code
  task) is still serving from another window, starting it again stops that
  run first, without asking. With a quick tunnel it serves at a new
  address and the old invite links stop working. Don't start it during a session unless you mean to
  restart.
- **"Port 8000 is already in use … which is not an earlier run".** Some
  other program holds the port. Close it, or serve on another port with
  `-Port 8001`.
- **The tunnel or the computer restarted mid-session.** Run the script
  again. With a named tunnel nothing else is needed. With a quick tunnel,
  send the new address. Rooms and tables are kept, so people can
  reach theirs by entering its code under "Join a room" at the new address,
  but they join as new participants: their old seat and hand stay with the
  old address.
- **"cloudflared stopped before connecting" with a named tunnel.** The
  token is wrong or was refreshed in Cloudflare. Run
  `.\scripts\serve-tunnel.cmd -SetUpNamedTunnel` again, or add `-Quick`
  to serve on a quick tunnel for now.
- **The named address shows a Cloudflare error page (502 or 1033).** The
  script is not running, or the published application route in Cloudflare points to a
  port other than the one served (8000 unless `-Port` was given).
- **cloudflared complains about a configuration file.** The other tunnel's
  settings may be getting in the way of the quick tunnel. Send the message
  to whoever maintains the project.
- **Windows Update.** Set active hours, or pause updates, around a
  session; a forced restart stops the server.
- **Too many people.** A quick tunnel answers at most 200 requests at once.
  Whether each open table counts towards that has not been measured.

On Linux, a Mac, or WSL, use `scripts/serve-tunnel.sh` instead; see the
README.
