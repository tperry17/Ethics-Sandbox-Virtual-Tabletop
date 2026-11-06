/**
 * The context menu on a piece, filled by the server.
 *
 * What may be done to a piece depends on rules this client does not know,
 * so the menu is a question: open it and the server is asked; its answer
 * is drawn as it arrives. Choosing an entry sends the intent the server
 * attached to it, unchanged. Nothing here decides what belongs on the menu.
 */

import { newClientId } from "./intents.js";
import type { MenuItemView, MenuMessage, ServerLink } from "./protocol.js";

export class ContextMenu {
  readonly element: HTMLElement;
  private readonly list: HTMLElement;
  private requestId: string | null = null;
  private pieceId: string | null = null;
  private returnFocus: HTMLElement | null = null;
  /** Questions asked without opening the menu, by request id: a keyboard shortcut's. */
  private readonly asked = new Map<string, (items: MenuItemView[]) => void>();

  constructor(
    private readonly host: HTMLElement,
    private readonly link: ServerLink,
    private readonly choose: (item: MenuItemView, pieceId: string) => void,
  ) {
    this.element = document.createElement("div");
    this.element.className = "table-menu";
    this.element.hidden = true;
    this.list = document.createElement("div");
    this.list.className = "table-menu__list";
    this.list.setAttribute("role", "menu");
    this.element.append(this.list);
    this.element.addEventListener("keydown", this.onKeyDown);
    host.append(this.element);
  }

  get isOpen(): boolean {
    return !this.element.hidden;
  }

  /** The piece whose menu is open, or null. */
  get openFor(): string | null {
    return this.isOpen ? this.pieceId : null;
  }

  /** Ask the server what may be done to `pieceId`, and show the answer at a point. */
  open(
    pieceId: string,
    clientX: number,
    clientY: number,
    label: string,
    returnFocus: HTMLElement | null,
  ): void {
    this.requestId = newClientId();
    this.pieceId = pieceId;
    this.returnFocus = returnFocus;
    this.list.setAttribute("aria-label", `Actions for ${label}`);
    this.list.replaceChildren(note("Asking the table…"));
    this.element.hidden = false;
    this.place(clientX, clientY);
    this.list.tabIndex = -1;
    this.list.focus({ preventScroll: true });
    this.link.send({ type: "menu_request", client_id: this.requestId, piece_id: pieceId });
  }

  /**
   * Ask what may be done to `pieceId` without showing a menu, for a shortcut
   * that stands for one of its entries. The answer is the server's, as ever.
   */
  ask(pieceId: string, answer: (items: MenuItemView[]) => void): void {
    const requestId = newClientId();
    this.asked.set(requestId, answer);
    this.link.send({ type: "menu_request", client_id: requestId, piece_id: pieceId });
  }

  receive(message: MenuMessage): void {
    const answer = this.asked.get(message.client_id);
    if (answer !== undefined) {
      this.asked.delete(message.client_id);
      answer(message.items);
      return;
    }
    if (!this.isOpen || message.client_id !== this.requestId) return;
    this.list.replaceChildren();
    if (message.items.length === 0) {
      this.list.append(note("There is nothing you can do with this piece right now."));
      return;
    }
    let group: string | null = null;
    for (const item of message.items) {
      if (item.group !== group) {
        group = item.group;
        if (group !== null) {
          const heading = document.createElement("p");
          heading.className = "table-menu__group";
          heading.setAttribute("role", "presentation");
          heading.textContent = group;
          this.list.append(heading);
        }
      }
      this.list.append(this.entry(item, message.piece_id));
    }
    const rect = this.element.getBoundingClientRect();
    this.place(rect.left, rect.top);
    this.items()[0]?.focus({ preventScroll: true });
  }

  close(restoreFocus = true): void {
    if (!this.isOpen) return;
    this.element.hidden = true;
    this.requestId = null;
    this.pieceId = null;
    if (restoreFocus) this.returnFocus?.focus({ preventScroll: true });
    this.returnFocus = null;
  }

  private entry(item: MenuItemView, pieceId: string): HTMLElement {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-menu__item";
    button.setAttribute("role", "menuitem");
    button.dataset.menuItem = item.id;
    button.tabIndex = -1;
    button.textContent = item.label;
    if (item.group !== null) button.classList.add("table-menu__item--grouped");
    button.addEventListener("click", () => {
      this.close();
      this.choose(item, pieceId);
    });
    return button;
  }

  private items(): HTMLElement[] {
    return [...this.list.querySelectorAll<HTMLElement>("[role=menuitem]")];
  }

  /** Put the menu at a screen point, kept inside the table. */
  private place(clientX: number, clientY: number): void {
    const box = this.host.getBoundingClientRect();
    const width = this.element.offsetWidth || 240;
    const height = this.element.offsetHeight || 120;
    const left = Math.min(Math.max(clientX - box.left, 8), Math.max(box.width - width - 8, 8));
    const top = Math.min(Math.max(clientY - box.top, 8), Math.max(box.height - height - 8, 8));
    this.element.style.left = `${left}px`;
    this.element.style.top = `${top}px`;
  }

  private onKeyDown = (event: KeyboardEvent): void => {
    const items = this.items();
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape" || event.key === "Tab") {
      event.preventDefault();
      event.stopPropagation();
      this.close();
      return;
    }
    if (items.length === 0) return;
    let next: number | null = null;
    if (event.key === "ArrowDown") next = index < 0 ? 0 : (index + 1) % items.length;
    if (event.key === "ArrowUp") next = index <= 0 ? items.length - 1 : index - 1;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = items.length - 1;
    if (next === null) return;
    event.preventDefault();
    event.stopPropagation();
    items[next]!.focus({ preventScroll: true });
  };
}

function note(text: string): HTMLElement {
  const paragraph = document.createElement("p");
  paragraph.className = "table-menu__note";
  paragraph.textContent = text;
  return paragraph;
}
