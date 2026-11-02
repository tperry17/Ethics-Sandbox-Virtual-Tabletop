/**
 * Reveals and close looks, drawn where nobody can miss them.
 *
 * In these exercises showing a card is a speech act, so a reveal is not a
 * quiet change of face on a small card at the edge of the table. While one
 * is in progress, everyone sees who is showing what to whom; the people
 * being shown it see the card itself, large. All of it is read from the
 * pieces' own state - `revealed_by`, `revealed_to`, and whether this viewer
 * was sent a face - so a reconnect, or a late arrival, sees exactly what is
 * happening now.
 */

import type { TableModel } from "./model.js";
import { appendFace } from "./piece-node.js";
import type { ComponentView } from "./protocol.js";

export interface RevealCallbacks {
  /** Put away a card this viewer is showing. */
  putAway: (pieceId: string) => void;
  /** A person's name, for a seat. */
  nameOf: (seatId: string) => string;
}

export class RevealLayer {
  readonly element: HTMLElement;
  readonly peek: HTMLElement;
  private signature = "";
  private readonly dismissed = new Set<string>();
  private peeking: string | null = null;

  constructor(private readonly callbacks: RevealCallbacks) {
    this.element = document.createElement("div");
    this.element.className = "reveals";

    this.peek = document.createElement("div");
    this.peek.className = "peek";
    this.peek.hidden = true;
  }

  /** Redraw from the model, if anything about the reveals in progress changed. */
  sync(model: TableModel): void {
    const me = model.seatId;
    const shown = [...model.pieces.values()]
      .filter((piece) => piece.revealed_by !== null && piece.revealed_to.length > 0)
      .sort((a, b) => a.id.localeCompare(b.id));
    // The names are part of it: a seat that arrives, leaves or is renamed
    // after a reveal began must not leave a stale name on the notice.
    const signature = shown
      .map((piece) => {
        const by = piece.revealed_by!;
        return [
          piece.id,
          by,
          piece.revealed_to.join(","),
          piece.component_id,
          by === me ? "" : this.callbacks.nameOf(by),
          this.audience(model, piece.revealed_to, by, me),
        ].join(":");
      })
      .join("|");
    for (const id of [...this.dismissed]) {
      if (!shown.some((piece) => piece.id === id)) this.dismissed.delete(id);
    }
    if (signature === this.signature) return;
    this.signature = signature;
    this.element.replaceChildren();

    for (const piece of shown) {
      const by = piece.revealed_by!;
      const shower = by === me ? "You" : this.callbacks.nameOf(by);
      const audience = this.audience(model, piece.revealed_to, by, me);
      const component =
        piece.component_id === null ? undefined : model.components.get(piece.component_id);
      const title = component?.title ?? null;

      if (by === me) {
        const bar = panel("reveal reveal--mine");
        bar.dataset.revealOf = piece.id;
        bar.append(
          line(`You are showing ${title ?? "a card"} to ${audience}.`),
          action("Put it away", () => this.callbacks.putAway(piece.id)),
        );
        this.element.append(bar);
        continue;
      }

      const toMe = me !== null && piece.revealed_to.includes(me);
      if (toMe && component !== undefined && !this.dismissed.has(piece.id)) {
        const card = panel("reveal reveal--to-me");
        card.dataset.revealOf = piece.id;
        card.setAttribute("role", "group");
        card.setAttribute("aria-label", `${shower} is showing you ${title ?? "a card"}`);
        card.append(line(`${shower} is showing ${audience === "you" ? "you" : audience}:`));
        card.append(enlarged(piece.kind, component));
        card.append(
          action("Hide", () => {
            this.dismissed.add(piece.id);
            this.signature = "";
            this.sync(model);
          }),
        );
        this.element.append(card);
        continue;
      }

      const notice = panel("reveal reveal--elsewhere");
      notice.dataset.revealOf = piece.id;
      notice.append(line(`${shower} is showing a card to ${audience}.`));
      this.element.append(notice);
    }
  }

  /** Who a reveal is addressed to, in words. */
  audience(
    model: TableModel,
    seats: string[],
    by: string,
    me: string | null,
  ): string {
    // "The table" only when it is more than one other person; at a table of
    // two, naming the one person being shown is plainer.
    const others = [...model.seats.keys()].filter((seat) => seat !== by);
    if (others.length > 1 && others.every((seat) => seats.includes(seat))) {
      return "the table";
    }
    const names = seats
      .filter((seat) => seat !== by)
      .map((seat) => (seat === me ? "you" : this.callbacks.nameOf(seat)));
    if (names.length === 0) return "nobody";
    if (names.length === 1) return names[0]!;
    return `${names.slice(0, -1).join(", ")} and ${names.at(-1)!}`;
  }

  // -- a close look, visible to nobody else ----------------------------------

  get peekingAt(): string | null {
    return this.peeking;
  }

  openPeek(pieceId: string, kind: string, component: ComponentView, onClose: () => void): void {
    this.peeking = pieceId;
    this.peek.replaceChildren();
    this.peek.dataset.peekOf = pieceId;
    this.peek.setAttribute("role", "dialog");
    this.peek.setAttribute("aria-label", `A closer look at ${component.title ?? "this card"}`);
    const hint = line("Only you can see this.");
    hint.classList.add("peek__hint");
    const close = action("Close", onClose);
    this.peek.append(enlarged(kind, component), hint, close);
    this.peek.hidden = false;
  }

  /** Focus the close control, for a look opened from the keyboard. */
  focusPeek(): void {
    this.peek.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  }

  closePeek(): void {
    this.peeking = null;
    this.peek.hidden = true;
    this.peek.replaceChildren();
    delete this.peek.dataset.peekOf;
  }
}

function panel(className: string): HTMLElement {
  const element = document.createElement("aside");
  element.className = className;
  return element;
}

function line(text: string): HTMLElement {
  const paragraph = document.createElement("p");
  paragraph.className = "reveal__line";
  paragraph.textContent = text;
  return paragraph;
}

function action(label: string, onClick: () => void): HTMLElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button button--secondary button--sm";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function enlarged(kind: string, component: ComponentView): HTMLElement {
  const card = document.createElement("article");
  card.className = `piece piece--${kind} piece--enlarged`;
  appendFace(card, component);
  return card;
}
