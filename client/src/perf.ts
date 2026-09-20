/**
 * Measuring the frame budget, in the browser, on a real table.
 *
 * The number this produces is the one CLAUDE.md records: how many frames a
 * second a crowded table holds while a piece is being dragged across it.
 * It samples actual frame intervals rather than timing a synthetic loop,
 * because what matters is what the person sees.
 */

export interface FrameReport {
  frames: number;
  durationMs: number;
  fps: number;
  /** The 95th-percentile frame interval: how bad the bad frames were. */
  worstMs: number;
  /** The median frame interval: what the frame usually costs. */
  medianMs: number;
}

export function measureFrames(durationMs: number): Promise<FrameReport> {
  return new Promise((resolve) => {
    const intervals: number[] = [];
    let previous = performance.now();
    const startedAt = previous;

    const tick = (now: number): void => {
      intervals.push(now - previous);
      previous = now;
      if (now - startedAt >= durationMs) {
        const elapsed = now - startedAt;
        const sorted = [...intervals].sort((a, b) => a - b);
        const index = Math.min(
          sorted.length - 1,
          Math.floor(sorted.length * 0.95),
        );
        resolve({
          frames: intervals.length,
          durationMs: elapsed,
          fps: (intervals.length / elapsed) * 1000,
          worstMs: sorted[index] ?? 0,
          medianMs: sorted[Math.floor(sorted.length / 2)] ?? 0,
        });
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}
