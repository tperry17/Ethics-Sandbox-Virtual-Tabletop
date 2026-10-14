/**
 * The table, in words, for anyone using a screen reader.
 *
 * Piece movements and reveals are announced in a polite live region. The
 * same sentence twice in a row is still announced: a second card moving to
 * the same place is a second thing that happened.
 */

export class Announcer {
  readonly element: HTMLElement;
  private flip = false;

  constructor() {
    this.element = document.createElement("p");
    this.element.className = "visually-hidden";
    this.element.setAttribute("role", "status");
    this.element.setAttribute("aria-live", "polite");
    this.element.dataset.announcer = "";
  }

  announce(text: string): void {
    // A trailing invisible character that alternates makes every message a
    // change, so assistive technology reads it even when it repeats.
    this.flip = !this.flip;
    this.element.textContent = this.flip ? text : `${text}​`;
  }

  get last(): string {
    return (this.element.textContent ?? "").replace(/​$/, "");
  }
}
