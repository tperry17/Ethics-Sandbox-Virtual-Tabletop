/**
 * The one canvas layer: ink, pointers, and other people's cursors.
 *
 * Everything else on the table is a DOM element, because text has to stay
 * text. These three are not text and there can be a great many of them, so
 * they are drawn, in world coordinates, and redrawn whenever the viewport
 * moves.
 */

import type { CursorView, SeatView, StrokeView } from "./protocol.js";
import { initialsFor, seatTintClass } from "./piece-node.js";
import type { Viewport } from "./viewport.js";

/** How long a pointer marker stays on the table after someone points. */
export const PING_MS = 3000;

interface Ping {
  x: number;
  y: number;
  seatId: string;
  at: number;
}

export class InkLayer {
  private readonly context: CanvasRenderingContext2D | null;
  private pings: Ping[] = [];
  private width = 0;
  private height = 0;
  private ratio = 1;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.context = canvas.getContext("2d");
  }

  resize(width: number, height: number, ratio: number): void {
    this.width = width;
    this.height = height;
    this.ratio = ratio;
    this.canvas.width = Math.max(1, Math.round(width * ratio));
    this.canvas.height = Math.max(1, Math.round(height * ratio));
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
  }

  ping(x: number, y: number, seatId: string, now: number): void {
    this.pings.push({ x, y, seatId, at: now });
  }

  /** True while something on this layer is still animating. */
  draw(
    viewport: Viewport,
    strokes: Iterable<StrokeView>,
    cursors: CursorView[],
    seats: Map<string, SeatView>,
    now: number,
  ): boolean {
    const context = this.context;
    if (context === null) return false;

    this.pings = this.pings.filter((ping) => now - ping.at < PING_MS);

    context.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    context.clearRect(0, 0, this.width, this.height);
    context.save();
    context.setTransform(
      viewport.scale * this.ratio,
      0,
      0,
      viewport.scale * this.ratio,
      viewport.offsetX * this.ratio,
      viewport.offsetY * this.ratio,
    );

    context.lineCap = "round";
    context.lineJoin = "round";
    for (const stroke of strokes) {
      if (stroke.points.length < 2) continue;
      context.strokeStyle = stroke.colour || this.seatColour(seats.get(stroke.seat_id));
      context.lineWidth = stroke.width;
      context.beginPath();
      const [first, ...rest] = stroke.points;
      context.moveTo(first![0], first![1]);
      for (const [x, y] of rest) context.lineTo(x, y);
      context.stroke();
    }

    for (const ping of this.pings) {
      const age = (now - ping.at) / PING_MS;
      const radius = (10 + age * 34) / viewport.scale;
      context.strokeStyle = this.seatColour(seats.get(ping.seatId));
      context.globalAlpha = Math.max(0, 1 - age);
      context.lineWidth = 3 / viewport.scale;
      context.beginPath();
      context.arc(ping.x, ping.y, radius, 0, Math.PI * 2);
      context.stroke();
    }
    context.globalAlpha = 1;
    context.restore();

    // Cursors and names are drawn in screen space so a name stays the same
    // size, and readable, however far out the table is zoomed.
    context.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
    context.font = "500 12px system-ui, sans-serif";
    context.textBaseline = "top";

    // Who pointed, beside the marker, fading with it.
    for (const ping of this.pings) {
      const seat = seats.get(ping.seatId);
      if (seat === undefined) continue;
      const age = (now - ping.at) / PING_MS;
      const x = ping.x * viewport.scale + viewport.offsetX;
      const y = ping.y * viewport.scale + viewport.offsetY;
      const name = seat.display_name ?? seat.label;
      const width = context.measureText(name).width;
      context.globalAlpha = Math.max(0, 1 - age * age);
      context.fillStyle = this.seatColour(seat);
      context.fillRect(x + 14, y - 26, width + 10, 18);
      context.fillStyle = "#0e1417";
      context.fillText(name, x + 19, y - 23);
    }
    context.globalAlpha = 1;

    for (const cursor of cursors) {
      const seat = seats.get(cursor.seat_id);
      const x = cursor.x * viewport.scale + viewport.offsetX;
      const y = cursor.y * viewport.scale + viewport.offsetY;
      if (x < -40 || y < -40 || x > this.width + 40 || y > this.height + 40) continue;
      const colour = this.seatColour(seat);
      context.fillStyle = colour;
      context.beginPath();
      context.moveTo(x, y);
      context.lineTo(x + 11, y + 4);
      context.lineTo(x + 4, y + 11);
      context.closePath();
      context.fill();
      if (seat !== undefined) {
        const label = initialsFor(seat);
        const width = context.measureText(label).width;
        context.fillRect(x + 10, y + 10, width + 8, 16);
        context.fillStyle = "#0e1417";
        context.fillText(label, x + 14, y + 12);
      }
    }
    return this.pings.length > 0;
  }

  private seatColour(seat: SeatView | undefined): string {
    if (seat === undefined) return "#9db0b2";
    const token = seatTintClass(seat.tint_index).replace("seat-", "--seat-");
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue(token)
      .trim();
    return value || "#9db0b2";
  }
}
