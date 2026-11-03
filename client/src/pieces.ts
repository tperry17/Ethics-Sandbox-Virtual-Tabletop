/**
 * The room's Pieces menu: dice and a set of player pieces in one colour,
 * added to the table where the person is looking. What the menu offers, and
 * whether a piece may be added, is the server's; this only draws the list
 * it was sent and reports which piece was chosen.
 */

import type { PieceMenuView } from "./protocol.js";

/** The colour last chosen, so the menu remembers it while it redraws. */
let chosenTint = 0;

function button(label: string, onClick: () => void, className = "button button--sm"): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.className = className;
  node.textContent = label;
  node.addEventListener("click", onClick);
  return node;
}

/**
 * The menu as a disclosure: closed, a "Pieces" button; open, the die and
 * the player pieces with a row of colours. Null when the room has none.
 */
export function renderPiecesMenu(
  menu: PieceMenuView[],
  add: (componentId: string) => void,
  wasOpen: boolean,
): HTMLElement | null {
  if (menu.length === 0) return null;
  const root = document.createElement("details");
  root.className = "pieces-menu";
  root.open = wasOpen;
  const summary = document.createElement("summary");
  summary.className = "button button--sm";
  summary.textContent = "Pieces";
  root.append(summary);

  const panel = document.createElement("div");
  panel.className = "pieces-menu__panel";
  panel.setAttribute("role", "group");
  panel.setAttribute("aria-label", "Add a piece");

  // Pieces with no colour of their own: each its own row.
  for (const entry of menu.filter((each) => each.tint_index === null || each.tint_index === undefined)) {
    const row = document.createElement("div");
    row.className = "pieces-menu__row";
    const name = document.createElement("span");
    name.textContent = entry.title;
    row.append(name, button("Add", () => add(entry.component_id)));
    panel.append(row);
  }

  // Player pieces: one set, in whichever colour is chosen.
  const tinted = menu.filter((each) => each.tint_index !== null && each.tint_index !== undefined);
  const tints = [...new Set(tinted.map((each) => each.tint_index as number))].sort((a, b) => a - b);
  if (tints.length > 0) {
    if (!tints.includes(chosenTint)) chosenTint = tints[0]!;
    const heading = document.createElement("p");
    heading.className = "pieces-menu__heading";
    heading.textContent = "Player pieces, in one colour";
    const swatches = document.createElement("div");
    swatches.className = "pieces-menu__swatches";
    swatches.setAttribute("role", "group");
    swatches.setAttribute("aria-label", "Colour");
    for (const tint of tints) {
      const swatch = button("", () => {
        chosenTint = tint;
        for (const other of swatches.children) {
          other.setAttribute("aria-pressed", String(other === swatch));
        }
      }, "pieces-menu__swatch");
      swatch.style.setProperty("--swatch", `var(--seat-${tint + 1})`);
      swatch.setAttribute("aria-label", `Seat colour ${tint + 1}`);
      swatch.setAttribute("aria-pressed", String(tint === chosenTint));
      swatches.append(swatch);
    }
    panel.append(heading, swatches);
    const kinds = [...new Set(tinted.map((each) => each.kind))];
    for (const kind of kinds) {
      const first = tinted.find((each) => each.kind === kind)!;
      const row = document.createElement("div");
      row.className = "pieces-menu__row";
      const name = document.createElement("span");
      name.textContent = first.title;
      row.append(
        name,
        button("Add", () => {
          const chosen =
            tinted.find((each) => each.kind === kind && each.tint_index === chosenTint) ?? first;
          add(chosen.component_id);
        }),
      );
      panel.append(row);
    }
  }
  root.append(panel);
  return root;
}
