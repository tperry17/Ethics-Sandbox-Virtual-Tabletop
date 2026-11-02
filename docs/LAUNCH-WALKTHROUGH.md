# Launch walkthrough: friction points

Prompt 16 asks for two walks, reported and not fixed. **What was actually
done:** both walks were made from a server run on a development machine,
driving every page and the join flow over HTTP, plus a read of the join,
start and table pages' text. **No tablet was held and no browser was driven
by a person**, so everything about touch, the on-screen keyboard and real
Wi-Fi is unchecked; `docs/MANUAL-CHECKS.md` covers it. Treat this list as a
first pass to be extended after a real tablet session.

Ordered by how likely each is to spoil a real session.

## Facilitator, five minutes before

1. **Wi-Fi that isolates devices.** Campus and guest networks often block
   tablets from reaching the Mac. `/health` finds this, but only if the
   facilitator thinks to check. Proposed fix: print the `/health` address
   and a "check from a tablet now" line last in `deploy.sh`'s output (it
   currently prints it, among other lines), and show a QR code of it.
2. **The address changes.** A new network or router restart changes the
   Mac's address and every shared link goes dead. Proposed fix: have
   `deploy.sh` also accept a hostname (Bonjour `name.local`) for
   `SANDBOX_PUBLIC_URL`, so links survive a change of address.
3. **Running `uvicorn` by hand uses an insecure default secret** and the
   development database. Proposed fix: refuse to start without
   `SANDBOX_SECRET_KEY` unless a development flag is set.
4. **Every room is titled "Open table".** With several tabs open, a
   facilitator cannot tell a class from a sandbox. Proposed fix: put the
   running activity's name in the tab title.
5. **No way to rehearse alone.** `seed-demo` fills every seat with fake
   people, so the facilitator can look at the table but not play it.
   Proposed fix: let the command leave one seat free.

## Participant on a tablet who has never seen it

6. **Copying the invite over `http`** needs a manual copy, as the
   rough-edges list says. Proposed fix: a QR code beside the link.
7. **A mistyped room code** gives "We couldn't find that", which is correct
   but does not offer the join form again. Proposed fix: show the code field
   on that page.
8. **Everyone joins as an observer once seats are full**, with nothing on
   the join page saying how many seats are left. Proposed fix: say "3 of 3
   seats taken" before joining.
9. **Nothing in the sandbox says what the table's pieces do** until the
   person tries them. Proposed fix: a one-line "Drag a card; double-tap to
   turn it over" hint for the first visit, dismissed once used.
10. **No social-preview image** when a link is pasted into a chat. Waiting
    on the Center's approval for the seal.
