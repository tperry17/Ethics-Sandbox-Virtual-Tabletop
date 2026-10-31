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
  root.className = "toolbar__activities";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Activities");

  if (model.activityChoices.length > 0) {
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Activity to start");
    for (const choice of model.activityChoices) {
      const option = document.createElement("option");
      option.value = choice.slug;
      option.textContent = `${choice.title} (${choice.min_players === choice.max_players ? choice.min_players : `${choice.min_players}–${choice.max_players}`} people)`;
      select.append(option);
    }
    root.append(
      select,
      button("Start this activity", () => send({ action: "open", slug: select.value })),
    );
  }

  for (const activity of model.activities.values()) {
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
