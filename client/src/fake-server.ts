/**
 * A server that is only a recording.
 *
 * It satisfies the same `ServerLink` the real socket does, so the renderer
 * cannot tell the difference and never needs to know. Rendering can be
 * built, looked at, and tested with nothing running behind it.
 *
 * It replays; it does not decide. An intent sent to it is remembered so a
 * test can assert what the client proposed, and answered with nothing -
 * judging an intent is the server's job, and this is not a server.
 */

import type {
  ClientMessage,
  LinkStatus,
  ServerLink,
  ServerMessage,
} from "./protocol.js";
import type { Recording } from "./recording.js";

export interface RecordedLinkOptions {
  /** Replay on a timer. False leaves the caller to drive `advanceTo`. */
  autoplay?: boolean;
  loop?: boolean;
}

export class RecordedLink implements ServerLink {
  /** Every intent the client proposed, in order. For tests to read. */
  readonly sent: ClientMessage[] = [];

  private messageHandler: ((message: ServerMessage) => void) | null = null;
  private statusHandler: ((status: LinkStatus) => void) | null = null;
  private timers: number[] = [];
  private cursor = 0;
  private started = false;

  constructor(
    private readonly recording: Recording,
    private readonly options: RecordedLinkOptions = {},
  ) {}

  onMessage(handler: (message: ServerMessage) => void): void {
    this.messageHandler = handler;
  }

  onStatus(handler: (status: LinkStatus) => void): void {
    this.statusHandler = handler;
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.statusHandler?.("connected");
    this.messageHandler?.(this.recording.snapshot);
    if (this.options.autoplay === false) return;
    for (const frame of this.recording.frames) {
      this.timers.push(
        window.setTimeout(() => {
          this.messageHandler?.(frame.message);
        }, frame.at),
      );
    }
    if (this.options.loop === true) {
      const last = this.recording.frames.at(-1)?.at ?? 0;
      this.timers.push(
        window.setTimeout(() => {
          this.restart();
        }, last + 1500),
      );
    }
  }

  stop(): void {
    for (const timer of this.timers) window.clearTimeout(timer);
    this.timers = [];
    this.started = false;
    this.statusHandler?.("offline");
  }

  send(message: ClientMessage): void {
    this.sent.push(message);
  }

  /** Deliver every frame up to `at` milliseconds. Deterministic; for tests. */
  advanceTo(at: number): void {
    while (this.cursor < this.recording.frames.length) {
      const frame = this.recording.frames[this.cursor]!;
      if (frame.at > at) return;
      this.cursor += 1;
      this.messageHandler?.(frame.message);
    }
  }

  private restart(): void {
    this.stop();
    this.cursor = 0;
    this.start();
  }
}
