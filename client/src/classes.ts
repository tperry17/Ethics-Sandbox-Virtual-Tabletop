/**
 * Classes, drawn in the toolbar: one activity at several tables, run by the
 * facilitator. This file sends what the person pressed. Who may, what is
 * legal, how people are sorted and what a pair's choices lead to are the
 * server's; the client shows the proposal it was sent and the sentences it
 * was given.
 */

import type { TableModel } from "./model.js";
import type { ClassView } from "./protocol.js";

export type SendClass = (payload: Record<string, unknown>) => void;

function button(label: string, onClick: () => void): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.className = "button button--sm";
  node.textContent = label;
  node.addEventListener("click", onClick);
  return node;
}

function seatName(model: TableModel, seatId: string): string {
  const seat = model.seats.get(seatId);
  return seat?.display_name ?? seat?.label ?? seatId;
}

function tableName(group: ClassView, tableId: string): string {
  return `Table ${group.tables.indexOf(tableId) + 1}`;
}

/** Whole seconds as m:ss, never negative. */
export function clock(seconds: number): string {
  const whole = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** The control that starts a class, shown to anyone who could run one. */
function renderStart(model: TableModel, send: SendClass): HTMLElement | null {
  if (model.activityChoices.length === 0) return null;
  const root = document.createElement("div");
  root.className = "toolbar__class-start";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Start a class");

  const select = document.createElement("select");
  select.setAttribute("aria-label", "Activity for the class");
  for (const choice of model.activityChoices) {
    const option = document.createElement("option");
    option.value = choice.slug;
    option.textContent = choice.title;
    select.append(option);
  }
  const boxes = new Map<string, HTMLElement>();
  const picks = new Map<string, HTMLSelectElement>();
  for (const choice of model.activityChoices) {
    const box = document.createElement("span");
    for (const option of choice.options ?? []) {
      const label = document.createElement("label");
      label.textContent = `${option.label} `;
      const pick = document.createElement("select");
      for (const entry of option.choices) {
        const item = document.createElement("option");
        item.value = entry.id;
        item.textContent = entry.label;
        pick.append(item);
      }
      picks.set(`${choice.slug}/${option.id}`, pick);
      label.append(pick);
      box.append(label);
    }
    boxes.set(choice.slug, box);
  }
  const showOptions = (): void => {
    for (const [slug, box] of boxes) box.hidden = slug !== select.value;
  };
  select.addEventListener("change", showOptions);
  showOptions();

  const tables = document.createElement("input");
  tables.type = "number";
  tables.min = "1";
  tables.max = "15";
  tables.value = "2";
  tables.setAttribute("aria-label", "Number of tables");
  const tablesLabel = document.createElement("label");
  tablesLabel.append("Tables ", tables);

  root.append(
    select,
    ...boxes.values(),
    tablesLabel,
    button("Start a class", () => {
      const options: Record<string, string> = {};
      for (const [key, pick] of picks) {
        const [slug, id] = key.split("/");
        if (slug === select.value && id !== undefined) options[id] = pick.value;
      }
      send({
        action: "start",
        slug: select.value,
        options,
        tables: Number.parseInt(tables.value, 10),
      });
    }),
  );
  return root;
}

/** The facilitator's sorting: the proposal, a way to move people, and confirm. */
function renderSort(
  model: TableModel,
  group: ClassView,
  send: SendClass,
  redraw: () => void,
): HTMLElement | null {
  const proposal = model.classSort;
  if (proposal === null || proposal.class_id !== group.id) return null;
  const root = document.createElement("div");
  root.className = "toolbar__sort";
  root.setAttribute("aria-label", "Proposed tables");
  root.setAttribute("role", "group");
  const where = new Map<string, number>();
  proposal.tables.forEach((people, index) => {
    for (const seat of people) where.set(seat, index);
  });
  for (const [seat, index] of where) {
    const row = document.createElement("label");
    row.className = "toolbar__sort-person";
    row.append(`${seatName(model, seat)} `);
    const pick = document.createElement("select");
    group.tables.forEach((id, i) => {
      const option = document.createElement("option");
      option.value = String(i);
      option.textContent = tableName(group, id);
      option.selected = i === index;
      pick.append(option);
    });
    pick.addEventListener("change", () => {
      const moved = proposal.tables.map((people) => people.filter((p) => p !== seat));
      moved[Number.parseInt(pick.value, 10)]?.push(seat);
      model.classSort = { ...proposal, tables: moved };
      redraw();
    });
    row.append(pick);
    root.append(row);
  }
  root.append(
    button("Sort again", () => send({ action: "sort_preview", class_id: group.id })),
    button("Seat them like this", () => {
      send({ action: "assign", class_id: group.id, tables: proposal.tables });
      model.classSort = null;
    }),
    button("Drop it", () => {
      model.classSort = null;
      redraw();
    }),
  );
  return root;
}

function renderPairing(model: TableModel, group: ClassView, send: SendClass): HTMLElement {
  const root = document.createElement("div");
  root.className = "toolbar__pairing";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Paired tables");
  const choices = group.pair_choices ?? [];
  for (const pair of group.pairs ?? []) {
    const row = document.createElement("div");
    row.className = "toolbar__pair";
    row.dataset.first = pair.first;
    const heading = document.createElement("span");
    heading.textContent = `${tableName(group, pair.first)} with ${tableName(group, pair.second)}: `;
    row.append(heading);
    for (const [table, decision, proposed] of [
      [pair.first, pair.first_decision, pair.first_proposed],
      [pair.second, pair.second_decision, pair.second_proposed],
    ] as const) {
      const label = document.createElement("label");
      label.append(`${tableName(group, table)} decided `);
      const pick = document.createElement("select");
      pick.dataset.table = table;
      const none = document.createElement("option");
      none.value = "";
      none.textContent = "not yet";
      pick.append(none);
      for (const choice of choices) {
        const option = document.createElement("option");
        option.value = choice;
        option.textContent = choice;
        option.selected = choice === decision;
        pick.append(option);
      }
      pick.addEventListener("change", () =>
        send({ action: "decision", class_id: group.id, first: table, decision: pick.value }),
      );
      label.append(pick);
      row.append(label);
      if (proposed !== null && proposed !== undefined) {
        row.append(
          button(`Confirm ${tableName(group, table)}: ${proposed}`, () =>
            send({ action: "decision", class_id: group.id, first: table, decision: proposed }),
          ),
        );
      }
    }
    row.append(
      button("Unpair", () => send({ action: "unpair", class_id: group.id, first: pair.first })),
    );
    if (pair.outcome !== null) {
      const outcome = document.createElement("p");
      outcome.className = "toolbar__outcome";
      outcome.textContent = pair.outcome;
      row.append(outcome);
    }
    root.append(row);
  }
  const free = group.tables.filter(
    (id) => !(group.pairs ?? []).some((pair) => pair.first === id || pair.second === id),
  );
  if (free.length >= 2) {
    const first = document.createElement("select");
    const second = document.createElement("select");
    first.setAttribute("aria-label", "First table to pair");
    second.setAttribute("aria-label", "Second table to pair");
    for (const id of free) {
      for (const pick of [first, second]) {
        const option = document.createElement("option");
        option.value = id;
        option.textContent = tableName(group, id);
        pick.append(option);
      }
    }
    if (second.options[1] !== undefined) second.selectedIndex = 1;
    root.append(
      first,
      second,
      button("Pair these tables", () =>
        send({ action: "pair", class_id: group.id, first: first.value, second: second.value }),
      ),
    );
  }
  return root;
}

/** Someone's table, and a way for the facilitator to put them at another. */
function moveControl(
  model: TableModel,
  group: ClassView,
  seatId: string,
  current: string | null,
  send: SendClass,
): HTMLElement {
  const label = document.createElement("label");
  label.className = "toolbar__move";
  label.append(`${seatName(model, seatId)} → `);
  const pick = document.createElement("select");
  pick.dataset.seat = seatId;
  pick.setAttribute("aria-label", `Table for ${seatName(model, seatId)}`);
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "no table";
  none.selected = current === null;
  pick.append(none);
  for (const id of group.tables) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = tableName(group, id);
    option.selected = id === current;
    pick.append(option);
  }
  pick.addEventListener("change", () =>
    send({
      action: "move",
      class_id: group.id,
      seat_id: seatId,
      to: pick.value === "" ? null : pick.value,
    }),
  );
  label.append(pick);
  return label;
}

/** What their own table decided, for someone at a paired table. */
function renderOwnChoice(group: ClassView, send: SendClass): HTMLElement | null {
  const choices = group.pair_choices ?? [];
  if (!group.your_table || choices.length === 0) return null;
  const label = document.createElement("label");
  label.className = "toolbar__own-choice";
  label.append("Your table chose ");
  const pick = document.createElement("select");
  pick.setAttribute("aria-label", "What your table chose");
  const shown = group.your_proposal ?? group.your_decision ?? null;
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "not yet";
  pick.append(none);
  for (const choice of choices) {
    const option = document.createElement("option");
    option.value = choice;
    option.textContent = choice;
    option.selected = choice === shown;
    pick.append(option);
  }
  pick.addEventListener("change", () =>
    send({
      action: "decision",
      class_id: group.id,
      first: group.your_table,
      decision: pick.value,
    }),
  );
  label.append(pick);
  const status = document.createElement("span");
  status.className = "toolbar__hint";
  status.setAttribute("role", "status");
  status.textContent =
    group.your_proposal
      ? "Waiting for the facilitator to confirm."
      : group.your_decision
        ? `The facilitator confirmed: ${group.your_decision}.`
        : "";
  label.append(" ", status);
  return label;
}

function renderClass(
  model: TableModel,
  group: ClassView,
  send: SendClass,
  sendActivity: SendClass,
  redraw: () => void,
): HTMLElement {
  const root = document.createElement("div");
  root.className = "toolbar__class";
  root.dataset.classId = group.id;
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", `Class: ${group.title}`);

  const heading = document.createElement("strong");
  heading.textContent = `Class: ${group.title}, ${group.tables.length} tables`;
  root.append(heading);

  const facilitator = model.you?.is_facilitator === true;
  const tables = document.createElement("ul");
  tables.className = "toolbar__class-tables";
  for (const id of group.tables) {
    const activity = model.activities.get(id);
    if (activity === undefined) continue;
    const item = document.createElement("li");
    item.dataset.activityId = id;
    const who = activity.seats.map((seat) => seatName(model, seat)).join(", ");
    const range =
      activity.min_players === activity.max_players
        ? `${activity.min_players}`
        : `${activity.min_players}–${activity.max_players}`;
    item.append(
      `${tableName(group, id)}: ${activity.status === "signup" ? "signing up" : "running"}, ${activity.seats.length} of ${range}${who ? ` (${who})` : ""} `,
    );
    const mine = model.seatId !== null && activity.seats.includes(model.seatId);
    if (!facilitator && activity.status === "signup") {
      if (mine) item.append(button("Leave", () => sendActivity({ action: "leave", activity_id: id })));
      else item.append(button("Join this table", () => sendActivity({ action: "join", activity_id: id })));
    }
    if (facilitator) {
      for (const seat of activity.seats) item.append(moveControl(model, group, seat, id, send));
    }
    tables.append(item);
  }
  root.append(tables);

  if (facilitator) {
    // People in the room who have no table in this class yet.
    const seated = new Set(
      group.tables.flatMap((id) => model.activities.get(id)?.seats ?? []),
    );
    const waiting = [...model.seats.values()].filter(
      (seat) => seat.participant_id !== null && !seat.is_facilitator && !seated.has(seat.id),
    );
    if (waiting.length > 0) {
      const line = document.createElement("div");
      line.className = "toolbar__waiting";
      line.append("Not at a table: ");
      for (const seat of waiting) line.append(moveControl(model, group, seat.id, null, send));
      root.append(line);
    }
  }

  if (!facilitator) {
    const choice = renderOwnChoice(group, send);
    if (choice !== null) root.append(choice);
    return root;
  }

  const sort = renderSort(model, group, send, redraw);
  root.append(
    button("Sort people into tables", () => send({ action: "sort_preview", class_id: group.id })),
    button("Begin the tables", () => send({ action: "begin", class_id: group.id })),
  );
  if (sort !== null) root.append(sort);

  const minutes = document.createElement("input");
  minutes.type = "number";
  minutes.min = "1";
  minutes.max = "180";
  minutes.value = String(Math.max(1, Math.round((group.timer_seconds || 1800) / 60)));
  minutes.setAttribute("aria-label", "Minutes on the timer");
  const timer = document.createElement("label");
  timer.append("Timer, minutes ", minutes);
  root.append(
    timer,
    button("Start timer for every table", () =>
      send({
        action: "timer",
        class_id: group.id,
        seconds: Math.round(Number.parseFloat(minutes.value) * 60),
      }),
    ),
    button("Clear timer", () => send({ action: "timer_clear", class_id: group.id })),
  );

  const prompts = group.prompt_choices ?? [];
  if (prompts.length > 0) {
    const pick = document.createElement("select");
    pick.setAttribute("aria-label", "Prompt to show everyone");
    for (const prompt of prompts) {
      const option = document.createElement("option");
      option.value = prompt.id;
      option.textContent = prompt.text.length > 70 ? `${prompt.text.slice(0, 70)}…` : prompt.text;
      pick.append(option);
    }
    root.append(
      pick,
      button("Show to every table", () =>
        send({ action: "prompt", class_id: group.id, prompt_id: pick.value }),
      ),
      button("Take it down", () => send({ action: "prompt", class_id: group.id, prompt_id: "" })),
    );
  }

  if (group.can_pair === true) root.append(renderPairing(model, group, send));

  root.append(
    button("End the class", () => {
      if (window.confirm("End the class? Every table and what is on it is removed.")) {
        send({ action: "end", class_id: group.id });
      }
    }),
  );
  return root;
}

/**
 * The classes section of the toolbar: the control to start one, and each
 * running class. `send` carries class actions; `sendActivity` the ordinary
 * activity actions (join, leave) a table of a class shares with any activity.
 */
export function renderClasses(
  model: TableModel,
  send: SendClass,
  sendActivity: SendClass,
  redraw: () => void,
): HTMLElement | null {
  if (model.seatId === null) return null;
  const root = document.createElement("div");
  root.className = "toolbar__classes";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "Classes");
  const start = renderStart(model, send);
  if (start !== null) root.append(start);
  for (const group of model.classes) {
    root.append(renderClass(model, group, send, sendActivity, redraw));
  }
  return root.childElementCount === 0 ? null : root;
}
