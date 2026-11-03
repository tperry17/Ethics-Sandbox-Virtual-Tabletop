/**
 * The room's activities, drawn in the toolbar: what can be started, who has
 * signed up, and the buttons that act on one. It sends what the person
 * pressed; whether it may happen, and who may press what, is the server's.
 */

import type { ActivityView } from "./protocol.js";
import type { TableModel } from "./model.js";

export type SendActivity = (payload: Record<string, unknown>) => void;

function button(label: string, onClick: () => void): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.className = "button button--sm";
  node.textContent = label;
  node.addEventListener("click", onClick);
  return node;
}

function names(model: TableModel, activity: ActivityView): string {
  return activity.seats
    .map((id) => model.seats.get(id)?.display_name ?? model.seats.get(id)?.label ?? id)
    .join(", ");
}

/** The activities section of the toolbar, or null when there is nothing to show. */
export function renderActivities(model: TableModel, send: SendActivity): HTMLElement | null {
  const mine = model.seatId;
  if (mine === null) return null;
  const root = document.createElement("div");
  root.className = "toolbar__activities room-panel__section";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Activities");

  // Each activity the room offers, as a card with its own choices and a
  // Start button. One offered only as a class is started from the class
  // controls, so its card says so instead. The server judges what is sent.
  if (model.activityChoices.length > 0) {
    const heading = document.createElement("h2");
    heading.className = "room-panel__heading";
    heading.textContent = "Start an activity";
    const intro = document.createElement("p");
    intro.className = "room-panel__intro";
    intro.textContent =
      "An activity opens a sign-up for its players. Everyone else keeps using the table.";
    const list = document.createElement("ul");
    list.className = "activity-cards";
    for (const choice of model.activityChoices) {
      const card = document.createElement("li");
      card.className = "activity-card";
      card.dataset.activity = choice.slug;
      const title = document.createElement("span");
      title.className = "activity-card__title";
      title.textContent = choice.title;
      const meta = document.createElement("span");
      meta.className = "activity-card__meta";
      const people =
        choice.min_players === choice.max_players
          ? `${choice.min_players}`
          : `${choice.min_players}–${choice.max_players}`;
      meta.textContent = `${people} people · about ${choice.duration_minutes} minutes`;
      card.append(title, meta);
      const picks = new Map<string, HTMLSelectElement>();
      for (const option of choice.options ?? []) {
        const label = document.createElement("label");
        label.className = "activity-card__option";
        label.textContent = `${option.label} `;
        const pick = document.createElement("select");
        pick.dataset.option = option.id;
        pick.setAttribute("aria-label", `${choice.title}: ${option.label}`);
        for (const entry of option.choices) {
          const item = document.createElement("option");
          item.value = entry.id;
          item.textContent = entry.label;
          pick.append(item);
        }
        picks.set(option.id, pick);
        label.append(pick);
        card.append(label);
      }
      if (choice.class_only === true) {
        const note = document.createElement("span");
        note.className = "activity-card__note";
        note.textContent = "Runs as a class: start it under “Run a class”.";
        card.append(note);
      } else {
        const start = button("Start", () => {
          const options: Record<string, string> = {};
          for (const [id, pick] of picks) options[id] = pick.value;
          send({ action: "open", slug: choice.slug, options });
        });
        start.classList.add("button--primary");
        start.setAttribute("aria-label", `Start ${choice.title}`);
        card.append(start);
      }
      list.append(card);
    }
    root.append(heading, intro, list);
  }

  for (const activity of model.activities.values()) {
    // A table of a class is listed with its class.
    if (activity.class_id) continue;
    const row = document.createElement("div");
    row.className = "toolbar__activity";
    row.dataset.activityId = activity.id;
    const signedUp = activity.seats.includes(mine);
    const label = document.createElement("span");
    label.textContent =
      activity.status === "signup"
        ? `${activity.title}: signing up, ${activity.seats.length} of ${activity.min_players === activity.max_players ? activity.min_players : `${activity.min_players}–${activity.max_players}`} (${names(model, activity)})`
        : `${activity.title}: running (${names(model, activity)})`;
    row.append(label);
    if (activity.status === "signup") {
      if (!signedUp) row.append(button("Join", () => send({ action: "join", activity_id: activity.id })));
      if (signedUp) row.append(button("Leave", () => send({ action: "leave", activity_id: activity.id })));
      if (activity.seats.length >= activity.min_players) {
        row.append(button("Begin now", () => send({ action: "begin", activity_id: activity.id })));
      }
    }
    if (signedUp || model.you?.is_facilitator === true) {
      row.append(button("End", () => send({ action: "end", activity_id: activity.id })));
    }
    root.append(row);
  }
  return root.childElementCount === 0 ? null : root;
}

export type SendOp = (opType: string, payload: Record<string, unknown>) => void;

function seatName(model: TableModel, seatId: string): string {
  const seat = model.seats.get(seatId);
  return seat?.display_name ?? seat?.label ?? seatId;
}

function cardName(model: TableModel, pieceId: string): string {
  const piece = model.pieces.get(pieceId);
  const component = piece?.component_id ? model.components.get(piece.component_id) : undefined;
  return component?.title ?? "a card";
}

function list(model: TableModel, ids: string[]): string {
  return ids.map((id) => cardName(model, id)).join(", ");
}

/**
 * Swap offers, the pairs who have swapped, and the control to make an offer
 * from the cards selected on the table. It gathers what the person chose;
 * the server decides whether it is a legal offer.
 */
export function renderTrades(
  model: TableModel,
  selected: () => ReadonlySet<string>,
  send: SendOp,
): HTMLElement | null {
  const mine = model.seatId;
  if (mine === null) return null;
  const players = new Set<string>();
  for (const activity of model.activities.values()) {
    if (activity.status === "running" && activity.seats.includes(mine)) {
      for (const seat of activity.seats) players.add(seat);
    }
  }
  if (players.size === 0 && model.offers.size === 0) return null;

  const root = document.createElement("div");
  root.className = "toolbar__trades";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Trades");

  const hint = document.createElement("span");
  hint.className = "toolbar__hint";
  hint.setAttribute("role", "status");
  const offer = button("Offer a trade", () => {
    const owner = (id: string): string | null => {
      const zone = model.zones.get(model.pieces.get(id)?.zone_id ?? "");
      return zone?.owner_seat ?? null;
    };
    const chosen = [...selected()];
    const give = chosen.filter((id) => owner(id) === mine);
    const want = chosen.filter((id) => {
      const seat = owner(id);
      return seat !== null && seat !== mine;
    });
    const partners = new Set(want.map((id) => owner(id)));
    if (give.length === 0 || want.length === 0 || partners.size !== 1) {
      hint.textContent =
        "Select cards in your hand and the cards you want from one other hand, then offer.";
      return;
    }
    hint.textContent = "";
    send("offer_swap", { to_seat: [...partners][0], give, want });
  });
  root.append(offer, hint);

  const seats = [...players];
  for (let first = 0; first < seats.length; first += 1) {
    for (let second = first + 1; second < seats.length; second += 1) {
      const key = [seats[first]!, seats[second]!].sort().join("|");
      const line = document.createElement("span");
      line.className = "toolbar__traded";
      line.textContent = `${seatName(model, seats[first]!)} and ${seatName(model, seats[second]!)}: ${
        model.swapped.has(key) ? "have traded" : "not yet"
      }`;
      root.append(line);
    }
  }

  for (const open of model.offers.values()) {
    const row = document.createElement("div");
    row.className = "toolbar__offer";
    row.dataset.offerId = open.id;
    row.textContent = `${seatName(model, open.from_seat)} offers ${list(model, open.give)} to ${seatName(model, open.to_seat)} for ${list(model, open.want)}.`;
    if (open.to_seat === mine) {
      row.append(
        button("Accept", () => send("accept_swap", { offer_id: open.id })),
        button("Decline", () => send("decline_swap", { offer_id: open.id })),
      );
    }
    if (open.from_seat === mine) {
      row.append(button("Withdraw", () => send("withdraw_swap", { offer_id: open.id })));
    }
    root.append(row);
  }
  return root;
}
