/**
 * Bootstrap.
 *
 * The page says what this client is looking at - a live room, or a recorded
 * session with no backend behind it - and this file builds the matching
 * link and hands it to the renderer. Nothing else in the client knows which
 * it got.
 */

import { SocketLink } from "./connection.js";
import { RecordedLink } from "./fake-server.js";
import { measureFrames } from "./perf.js";
import { DENSE_DRAG_START_MS, demoRecording, denseRecording } from "./recording.js";
import type { ServerLink } from "./protocol.js";
import { TableRenderer } from "./table.js";

declare global {
  interface Window {
    /** The live renderer, for the interaction half and for tests to reach. */
    ethicsSandboxTable?: TableRenderer;
  }
}

function socketUrl(roomCode: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/t/${roomCode}`;
}

function linkFor(root: HTMLElement): ServerLink {
  const roomCode = root.dataset.roomCode ?? "";
  if (root.dataset.source !== "replay") {
    return new SocketLink(socketUrl(roomCode), roomCode);
  }
  const count = Number.parseInt(root.dataset.pieces ?? "", 10);
  const recording = Number.isFinite(count) && count > 0
    ? denseRecording(count)
    : demoRecording();
  return new RecordedLink(recording, { loop: root.dataset.loop === "1" });
}

function boot(): void {
  document.documentElement.dataset.tableClient = "ready";
  const root = document.getElementById("table-root");
  if (!(root instanceof HTMLElement)) return;

  const renderer = new TableRenderer({
    root,
    toolbar: document.getElementById("table-toolbar"),
    link: linkFor(root),
    roomCode: root.dataset.roomCode ?? "",
  });
  window.ethicsSandboxTable = renderer;
  renderer.start();

  if (root.dataset.measure === "1") {
    const readout = document.getElementById("table-measure");
    // Measure the drag, not the mount: the table appearing for the first
    // time is real work, but it is not the work the frame budget is about.
    const measurement = new Promise<void>((resolve) => {
      window.setTimeout(resolve, DENSE_DRAG_START_MS);
    }).then(() => measureFrames(2600));
    void measurement.then((report) => {
      const line =
        `${report.fps.toFixed(1)} fps · ${report.frames} frames · median frame ${report.medianMs.toFixed(1)} ms · ` +
        `95th-percentile frame ${report.worstMs.toFixed(1)} ms`;
      document.documentElement.dataset.tableFps = report.fps.toFixed(1);
      document.documentElement.dataset.tableWorstFrameMs = report.worstMs.toFixed(1);
      document.documentElement.dataset.tableMedianFrameMs = report.medianMs.toFixed(1);
      if (readout instanceof HTMLElement) readout.textContent = line;
    });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
