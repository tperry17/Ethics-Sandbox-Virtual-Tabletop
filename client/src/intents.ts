/**
 * Proposing things to the server, and hearing back.
 *
 * Every gesture becomes an intent with its own `client_id`. The server
 * answers each one exactly once: an `ack` once it has applied it (its
 * patches already sent), or a `reject` with a sentence a person can read.
 * This file matches those answers to whoever asked, and nothing more. It
 * does not know whether any intent ought to succeed - that is the server's
 * to say, and the reason the local result of a gesture is only ever a
 * guess that may be taken back.
 */

import type { ClientMessage, ServerLink } from "./protocol.js";

export interface IntentCallbacks {
  onAck?: () => void;
  onReject?: (reason: string) => void;
}

/**
 * How long to wait for an answer before treating silence as "the server
 * did not hear it" - a socket that dropped mid-gesture. Long enough that a
 * slow connection is not mistaken for a lost one.
 */
const ANSWER_TIMEOUT_MS = 8000;

let counter = 0;

export function newClientId(): string {
  counter += 1;
  const random = Math.random().toString(36).slice(2, 10);
  return `c${Date.now().toString(36)}-${counter}-${random}`;
}

interface Pending {
  callbacks: IntentCallbacks;
  timer: number;
}

export class IntentTracker {
  private readonly pending = new Map<string, Pending>();

  /**
   * `onLost` hears about an intent that was never answered, so the person
   * is told; the server never sent a sentence for it, so this file must.
   */
  constructor(
    private readonly link: ServerLink,
    private readonly onLost: (reason: string) => void = () => {},
  ) {}

  /**
   * Propose one operation. Returns its `client_id`.
   *
   * The id doubles as the operation's `op_id`, so if the same intent ever
   * reaches the server twice it is applied once.
   */
  send(
    opType: string,
    payload: Record<string, unknown>,
    callbacks: IntentCallbacks = {},
  ): string {
    const clientId = newClientId();
    const timer = window.setTimeout(() => {
      const reason = "That did not reach the table. Please try again.";
      if (this.settle(clientId, reason)) this.onLost(reason);
    }, ANSWER_TIMEOUT_MS);
    this.pending.set(clientId, { callbacks, timer });
    const message: ClientMessage = {
      type: "intent",
      client_id: clientId,
      op_type: opType,
      payload: { ...payload, op_id: clientId },
    };
    this.link.send(message);
    return clientId;
  }

  /** The server accepted `clientId`. */
  ack(clientId: string): boolean {
    return this.settle(clientId, null);
  }

  /** The server refused `clientId`, for `reason`. True if anyone was waiting. */
  reject(clientId: string, reason: string): boolean {
    return this.settle(clientId, reason);
  }

  /** Whether `clientId` is still waiting on an answer. */
  isPending(clientId: string): boolean {
    return this.pending.has(clientId);
  }

  private settle(clientId: string, reason: string | null): boolean {
    const entry = this.pending.get(clientId);
    if (entry === undefined) return false;
    this.pending.delete(clientId);
    window.clearTimeout(entry.timer);
    if (reason === null) entry.callbacks.onAck?.();
    else entry.callbacks.onReject?.(reason);
    return true;
  }
}
