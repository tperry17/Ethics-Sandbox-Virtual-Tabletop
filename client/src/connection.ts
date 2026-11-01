/**
 * The live link: one WebSocket, kept open.
 *
 * Losing the connection is ordinary - a laptop lid, a train tunnel, a wifi
 * handover - so it is handled quietly and without ever reloading the page.
 * On coming back, the client says how far it had got and the server decides
 * whether that is a short replay or a whole new snapshot. Sequence numbers
 * are the server's; this file only remembers the last one it was told.
 */

import type {
  ClientMessage,
  LinkStatus,
  ServerLink,
  ServerMessage,
} from "./protocol.js";

const HEARTBEAT_MS = 20_000;
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000];
/** After this many failures in a row, say plainly that the table is offline. */
const OFFLINE_AFTER = 3;
/** The server's close code for "you are not in this room" (live.py). */
const REFUSED_CLOSE_CODE = 4403;

export class SocketLink implements ServerLink {
  private socket: WebSocket | null = null;
  private messageHandler: ((message: ServerMessage) => void) | null = null;
  private statusHandler: ((status: LinkStatus) => void) | null = null;
  private lastSeq = 0;
  private epoch: string | null = null;
  private attempt = 0;
  private heartbeat: number | null = null;
  private retry: number | null = null;
  private stopped = false;

  constructor(
    private readonly url: string,
    private readonly roomCode: string,
  ) {}

  onMessage(handler: (message: ServerMessage) => void): void {
    this.messageHandler = handler;
  }

  onStatus(handler: (status: LinkStatus) => void): void {
    this.statusHandler = handler;
  }

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.socket?.close();
    this.socket = null;
  }

  send(message: ClientMessage): void {
    const socket = this.socket;
    if (socket === null || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify(message));
  }

  private connect(): void {
    if (this.stopped) return;
    this.statusHandler?.(this.attempt >= OFFLINE_AFTER ? "offline" : "reconnecting");
    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.attempt = 0;
      this.statusHandler?.("connected");
      this.send({
        type: "hello",
        room_code: this.roomCode,
        last_seq: this.lastSeq,
        ...(this.epoch === null ? {} : { epoch: this.epoch }),
      });
      this.startHeartbeat();
    });

    socket.addEventListener("message", (event) => {
      if (typeof event.data !== "string") return;
      let message: ServerMessage;
      try {
        message = JSON.parse(event.data) as ServerMessage;
      } catch {
        return;
      }
      if (message.type === "snapshot" && typeof message.epoch === "string") {
        this.epoch = message.epoch;
      }
      if (message.type === "snapshot" || message.type === "patches") {
        this.lastSeq = message.seq;
      }
      this.messageHandler?.(message);
    });

    socket.addEventListener("close", (event) => {
      this.clearTimers();
      this.socket = null;
      if (event.code === REFUSED_CLOSE_CODE) {
        // The server says this person is not in this room, or it is gone.
        // Retrying cannot change that.
        this.stopped = true;
        this.statusHandler?.("refused");
        return;
      }
      this.scheduleRetry();
    });

    socket.addEventListener("error", () => {
      socket.close();
    });
  }

  private scheduleRetry(): void {
    if (this.stopped) return;
    const index = Math.min(this.attempt, BACKOFF_MS.length - 1);
    const base = BACKOFF_MS[index]!;
    this.attempt += 1;
    this.statusHandler?.(this.attempt > OFFLINE_AFTER ? "offline" : "reconnecting");
    const jitter = Math.random() * base * 0.25;
    this.retry = window.setTimeout(() => this.connect(), base + jitter);
  }

  private startHeartbeat(): void {
    this.clearHeartbeat();
    this.heartbeat = window.setInterval(() => {
      this.send({ type: "heartbeat" });
    }, HEARTBEAT_MS);
  }

  private clearHeartbeat(): void {
    if (this.heartbeat !== null) window.clearInterval(this.heartbeat);
    this.heartbeat = null;
  }

  private clearTimers(): void {
    this.clearHeartbeat();
    if (this.retry !== null) window.clearTimeout(this.retry);
    this.retry = null;
  }
}
