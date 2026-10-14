import type {} from "../src/main.js";

import { type Locator, type Page, expect, test } from "@playwright/test";

import type { ServerMessage } from "../src/protocol.js";

/**
 * The interaction half, driven through the recorded session.
 *
 * There is no server behind `/table-preview`, so these tests play its part:
 * they read the intents the client proposed and answer them - an ack, a
 * reject, a menu, a patch - exactly as the server would. What they check
 * is the client's side of that conversation: that a gesture shows at once,
 * proposes the right intent, and goes back visibly when refused.
 */

const PREVIEW = "/table-preview";

interface SentIntent {
  type: "intent";
  client_id: string;
  op_type: string;
  payload: Record<string, unknown>;
}

async function sent(page: Page): Promise<Array<Record<string, unknown>>> {
  return page.evaluate(
    () => (window.ethicsSandboxLink?.sent ?? []) as unknown as Array<Record<string, unknown>>,
  );
}

async function intents(page: Page): Promise<SentIntent[]> {
  const all = await sent(page);
  return all.filter((message) => message["type"] === "intent") as unknown as SentIntent[];
}

async function inject(page: Page, message: ServerMessage): Promise<void> {
  await page.evaluate((m) => window.ethicsSandboxLink!.inject(m), message);
}

async function centre(locator: Locator): Promise<{ x: number; y: number }> {
  const box = (await locator.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Where a world point is on screen right now. */
async function onScreen(page: Page, x: number, y: number): Promise<{ x: number; y: number }> {
  return page.evaluate(
    ([wx, wy]) => {
      const table = window.ethicsSandboxTable!;
      const viewport = table.currentViewport;
      const box = table.surfaceElement.getBoundingClientRect();
      return {
        x: box.left + wx! * viewport.scale + viewport.offsetX,
        y: box.top + wy! * viewport.scale + viewport.offsetY,
      };
    },
    [x, y],
  );
}

async function drag(
  page: Page,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 8 });
  await page.mouse.up();
}

function piece(page: Page, id: string): Locator {
  return page.locator(`[data-piece-id="${id}"]`);
}

async function visual(page: Page, id: string): Promise<[number, number]> {
  return page.evaluate((pieceId) => window.ethicsSandboxTable!.visualPositionOf(pieceId)!, id);
}

/** The recording deals a card into this viewer's hand at 1.5 s; let it land first. */
async function settledTray(page: Page): Promise<void> {
  await expect(page.locator(".hand-tray__fan .piece")).toHaveCount(4, { timeout: 5000 });
}

test.describe("dragging", () => {
  test("lifts a piece at once, proposes each step, and keeps it where it was let go", async ({
    page,
  }) => {
    await page.goto(PREVIEW);
    const token = piece(page, "token-1");
    const start = await centre(token);
    const target = await onScreen(page, 300, 260);

    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(target.x, target.y, { steps: 8 });
    await expect(token).toHaveClass(/is-dragging/);
    await expect(token).toHaveClass(/is-held/);
    const [midX, midY] = await visual(page, "token-1");
    expect(midX).toBeCloseTo(300, 0);
    expect(midY).toBeCloseTo(260, 0);
    await page.mouse.up();

    const proposed = await intents(page);
    const ops = proposed.map((intent) => intent.op_type);
    expect(ops[0]).toBe("grab");
    expect(ops).toContain("move");
    expect(ops.at(-1)).toBe("release");
    const lastMove = proposed.filter((intent) => intent.op_type === "move").at(-1)!;
    expect(lastMove.payload["x"]).toBeCloseTo(300, 0);
    expect(lastMove.payload["y"]).toBeCloseTo(260, 0);

    // Waiting on the server, the piece stays where the hand let it go.
    expect((await visual(page, "token-1"))[0]).toBeCloseTo(300, 0);

    // The server agrees: patches first, then the ack for the release.
    await inject(page, {
      type: "patches",
      seq: 50,
      patches: [
        {
          kind: "piece",
          op: "upsert",
          entity_id: "token-1",
          fields: { x: 300, y: 260, held_by: null },
        },
      ],
    });
    await inject(page, { type: "ack", client_id: proposed.at(-1)!.client_id });
    await expect(token).not.toHaveClass(/is-dragging/);
    expect((await visual(page, "token-1"))[0]).toBeCloseTo(300, 0);
  });

  test("goes back visibly, with the server's sentence, when the server refuses", async ({
    page,
  }) => {
    await page.goto(PREVIEW);
    const token = piece(page, "token-1");
    const start = await centre(token);
    const target = await onScreen(page, 320, 280);
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(target.x, target.y, { steps: 6 });

    const grab = (await intents(page)).find((intent) => intent.op_type === "grab")!;
    await inject(page, {
      type: "reject",
      client_id: grab.client_id,
      reason: "Someone else is already holding that piece.",
    });

    await expect(token).toHaveClass(/is-rolling-back/);
    await expect(page.locator(".tabletop__notices")).toContainText(
      "Someone else is already holding that piece.",
    );
    // It glides back rather than vanishing to its old spot.
    await expect
      .poll(async () => (await visual(page, "token-1"))[0], { timeout: 2000 })
      .toBeCloseTo(180, 0);
    await page.mouse.up();
    const after = (await intents(page)).map((intent) => intent.op_type);
    expect(after).not.toContain("release");
  });

  test("drops onto a zone as a move into that zone, at the spot it was let go", async ({
    page,
  }) => {
    await page.goto(PREVIEW);
    await drag(page, await centre(piece(page, "token-1")), await onScreen(page, 410, 600));

    const move = (await intents(page)).find((intent) => intent.op_type === "move_to_zone")!;
    expect(move.payload["piece_id"]).toBe("token-1");
    expect(move.payload["zone_id"]).toBe("claims");
    expect(move.payload["x"]).toBeCloseTo(410, 0);
    expect(move.payload["y"]).toBeCloseTo(600, 0);
  });

  test("lights the zone it would land in while it is held", async ({ page }) => {
    await page.goto(PREVIEW);
    const start = await centre(piece(page, "token-1"));
    const over = await onScreen(page, 410, 600);
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(over.x, over.y, { steps: 6 });

    await expect(page.locator('.zone[data-zone-id="claims"]')).toHaveClass(/is-drop-target/);
    await page.mouse.up();
    await expect(page.locator('.zone[data-zone-id="claims"]')).not.toHaveClass(/is-drop-target/);
  });

  test("stacks a piece dropped on another", async ({ page }) => {
    await page.goto(PREVIEW);
    const start = await centre(piece(page, "token-1"));
    const onto = await centre(piece(page, "cube-1"));
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(onto.x, onto.y, { steps: 8 });
    await expect(piece(page, "cube-1")).toHaveClass(/is-stack-target/);
    await page.mouse.up();

    const stack = (await intents(page)).find((intent) => intent.op_type === "stack_onto")!;
    expect(stack.payload).toMatchObject({ piece_id: "token-1", onto_id: "cube-1" });
  });

  test("takes a piece into the hand when it is dropped on the tray", async ({ page }) => {
    await page.goto(PREVIEW);
    await settledTray(page);
    const tray = await centre(page.locator(".hand-tray"));
    await drag(page, await centre(piece(page, "token-1")), tray);

    const take = (await intents(page)).find((intent) => intent.op_type === "move_to_zone")!;
    expect(take.payload).toMatchObject({ piece_id: "token-1", zone_id: "hand-1" });
  });

  test("plays a card from the hand onto the table", async ({ page }) => {
    await page.goto(PREVIEW);
    await settledTray(page);
    await drag(page, await centre(piece(page, "hand-1-a")), await onScreen(page, 200, 300));

    const proposed = await intents(page);
    expect(proposed.map((intent) => intent.op_type)).toEqual([
      "grab",
      "move_to_zone",
      "release",
    ]);
    expect(proposed[1]!.payload).toMatchObject({ piece_id: "hand-1-a", zone_id: "table" });
  });
});

test.describe("selecting", () => {
  test("marquee-selects pieces, which then rotate and move together", async ({ page }) => {
    await page.goto(PREVIEW);
    await drag(page, await onScreen(page, 120, 120), await onScreen(page, 300, 220));

    await expect(piece(page, "token-1")).toHaveClass(/is-selected/);
    await expect(piece(page, "cube-1")).toHaveClass(/is-selected/);
    await expect(piece(page, "die-1")).not.toHaveClass(/is-selected/);

    await page.keyboard.press("r");
    const rotated = (await intents(page)).filter((intent) => intent.op_type === "rotate");
    expect(rotated.map((intent) => intent.payload["piece_id"]).sort()).toEqual([
      "cube-1",
      "token-1",
    ]);
    expect(rotated.every((intent) => intent.payload["degrees"] === 90)).toBe(true);

    await drag(page, await centre(piece(page, "token-1")), await onScreen(page, 240, 300));
    const moved = new Set(
      (await intents(page))
        .filter((intent) => intent.op_type === "move")
        .map((intent) => intent.payload["piece_id"]),
    );
    expect(moved).toEqual(new Set(["token-1", "cube-1"]));
  });

  test("a click on empty table clears the selection", async ({ page }) => {
    await page.goto(PREVIEW);
    await page.mouse.click(...Object.values(await centre(piece(page, "token-1"))) as [number, number]);
    await expect(piece(page, "token-1")).toHaveClass(/is-selected/);
    const empty = await onScreen(page, 120, 300);
    await page.mouse.click(empty.x, empty.y);
    await expect(piece(page, "token-1")).not.toHaveClass(/is-selected/);
  });
});

test.describe("flipping and rotating", () => {
  test("a double-click turns a card over, hiding its face at once", async ({ page }) => {
    await page.goto(PREVIEW);
    const card = piece(page, "claim-1");
    await card.dblclick();

    await expect(card).toHaveClass(/is-face-down/);
    await expect(card.locator(".piece__title")).toHaveCount(0);
    const flip = (await intents(page)).find((intent) => intent.op_type === "flip")!;
    expect(flip.payload["piece_id"]).toBe("claim-1");

    // Refused: the face comes back.
    await inject(page, { type: "reject", client_id: flip.client_id, reason: "That piece is locked." });
    await expect(card.locator(".piece__title")).toHaveText("Equal standing");
  });
});

test.describe("the context menu", () => {
  const menu = (pieceId: string, clientId: string): ServerMessage => ({
    type: "menu",
    client_id: clientId,
    piece_id: pieceId,
    items: [
      { id: "flip", label: "Turn over", group: null, op_type: "flip", payload: { piece_id: pieceId } },
      {
        id: "show_to:seat-2",
        label: "Rowan Bell",
        group: "Show to…",
        op_type: "show_to",
        payload: { piece_id: pieceId, seat_ids: ["seat-2"] },
      },
    ],
  });

  async function lastMenuRequest(page: Page): Promise<Record<string, unknown>> {
    return (await sent(page)).filter((message) => message["type"] === "menu_request").at(-1)!;
  }

  test("asks the server what may be done, and sends what was chosen", async ({ page }) => {
    await page.goto(PREVIEW);
    await piece(page, "claim-1").click({ button: "right" });

    const request = await lastMenuRequest(page);
    expect(request["piece_id"]).toBe("claim-1");
    await expect(page.locator(".table-menu")).toBeVisible();
    await expect(page.locator(".table-menu")).toContainText("Asking the table");

    await inject(page, menu("claim-1", request["client_id"] as string));
    await expect(page.getByRole("menuitem", { name: "Turn over" })).toBeVisible();
    await expect(page.locator(".table-menu__group")).toHaveText("Show to…");
    await page.getByRole("menuitem", { name: "Rowan Bell" }).click();

    await expect(page.locator(".table-menu")).toBeHidden();
    const show = (await intents(page)).at(-1)!;
    expect(show.op_type).toBe("show_to");
    expect(show.payload).toMatchObject({ piece_id: "claim-1", seat_ids: ["seat-2"] });
  });

  test("is reachable and usable from the keyboard", async ({ page }) => {
    await page.goto(PREVIEW);
    const card = piece(page, "claim-1");
    await card.focus();
    await page.keyboard.press("m");
    await inject(page, menu("claim-1", (await lastMenuRequest(page))["client_id"] as string));

    await expect(page.getByRole("menuitem", { name: "Turn over" })).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("menuitem", { name: "Rowan Bell" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.locator(".table-menu")).toBeHidden();
    await expect(card).toBeFocused();

    await page.keyboard.press("m");
    await inject(page, menu("claim-1", (await lastMenuRequest(page))["client_id"] as string));
    await page.keyboard.press("Enter");
    expect((await intents(page)).at(-1)!.op_type).toBe("flip");
  });
});

test.describe("the hand and revealing", () => {
  test("holding a card in the hand lifts it up close, privately, and logs a look", async ({
    page,
  }) => {
    await page.goto(PREVIEW);
    await settledTray(page);
    const card = await centre(piece(page, "hand-1-b"));
    await page.mouse.move(card.x, card.y);
    await page.mouse.down();

    const look = page.locator(".peek");
    await expect(look).toBeVisible({ timeout: 2000 });
    await expect(look.locator(".piece__title")).toHaveText("Kept promises");
    await expect(look).toContainText("Only you can see this");
    expect((await intents(page)).map((intent) => intent.op_type)).toEqual(["peek"]);

    await page.mouse.up();
    await expect(look).toBeHidden();
  });

  test("a card shown to this viewer appears large, with who is showing it", async ({ page }) => {
    await page.goto(PREVIEW);
    await inject(page, {
      type: "patches",
      seq: 60,
      components: [
        {
          id: "fair-shares",
          title: "Fair shares",
          body: "Divide so that the one who cuts would accept any piece.",
          folio: "vii",
          image: null,
          tint_index: null,
          width: null,
          height: null,
        },
      ],
      patches: [
        {
          kind: "piece",
          op: "upsert",
          entity_id: "hand-2-a",
          fields: {
            component_id: "fair-shares",
            face_up: true,
            revealed_to: ["seat-1"],
            revealed_by: "seat-2",
          },
        },
        {
          kind: "table",
          op: "event",
          entity_id: null,
          fields: { type: "show", piece_id: "hand-2-a", by_seat: "seat-2", to_seats: ["seat-1"] },
        },
      ],
    });

    const reveal = page.locator(".reveal--to-me");
    await expect(reveal).toContainText("Rowan Bell is showing you:");
    await expect(reveal.locator(".piece__title")).toHaveText("Fair shares");
    // The face arrived with the patch, so the piece on the table shows it too.
    await expect(piece(page, "hand-2-a").locator(".piece__title")).toHaveText("Fair shares");
    await expect(page.locator("[data-announcer]")).toHaveText(
      /Rowan Bell is showing Fair shares to you\./,
    );

    await inject(page, {
      type: "patches",
      seq: 61,
      patches: [
        {
          kind: "piece",
          op: "upsert",
          entity_id: "hand-2-a",
          fields: { component_id: null, face_up: false, revealed_to: [], revealed_by: null },
        },
        {
          kind: "table",
          op: "event",
          entity_id: null,
          fields: { type: "show_end", piece_id: "hand-2-a", by_seat: "seat-2" },
        },
      ],
    });
    await expect(reveal).toHaveCount(0);
    await expect(piece(page, "hand-2-a")).toHaveClass(/is-face-down/);
  });

  test("everyone else sees that a card is being shown, and to whom, but not what", async ({
    page,
  }) => {
    await page.goto(PREVIEW);
    await inject(page, {
      type: "presence",
      cursors: [],
      seats: [
        {
          id: "seat-1",
          label: "Seat 1",
          tint_index: 0,
          participant_id: "p-1",
          display_name: "Ines Okafor",
          is_facilitator: true,
          connected: true,
        },
        {
          id: "seat-2",
          label: "Seat 2",
          tint_index: 1,
          participant_id: "p-2",
          display_name: "Rowan Bell",
          is_facilitator: false,
          connected: true,
        },
        {
          id: "seat-3",
          label: "Seat 3",
          tint_index: 2,
          participant_id: "p-3",
          display_name: "Sam Ortiz",
          is_facilitator: false,
          connected: true,
        },
      ],
    });
    await inject(page, {
      type: "patches",
      seq: 70,
      patches: [
        {
          kind: "piece",
          op: "upsert",
          entity_id: "hand-2-b",
          fields: { revealed_to: ["seat-3"], revealed_by: "seat-2" },
        },
      ],
    });

    const notice = page.locator(".reveal--elsewhere");
    await expect(notice).toHaveText("Rowan Bell is showing a card to Sam Ortiz.");
    await expect(notice.locator(".piece")).toHaveCount(0);
    await expect(piece(page, "hand-2-b")).toHaveClass(/is-shown/);
    await expect(piece(page, "hand-2-b")).toHaveClass(/is-face-down/);
  });

  test("a card this viewer is showing can be put away", async ({ page }) => {
    await page.goto(PREVIEW);
    await inject(page, {
      type: "patches",
      seq: 80,
      patches: [
        {
          kind: "piece",
          op: "upsert",
          entity_id: "hand-1-b",
          fields: { revealed_to: ["seat-2"], revealed_by: "seat-1" },
        },
      ],
    });

    const mine = page.locator(".reveal--mine");
    await expect(mine).toContainText("You are showing Kept promises to Rowan Bell.");
    await mine.getByRole("button", { name: "Put it away" }).click();
    const putAway = (await intents(page)).at(-1)!;
    expect(putAway.op_type).toBe("end_show");
    expect(putAway.payload["piece_id"]).toBe("hand-1-b");
  });
});

test.describe("the keyboard", () => {
  test("moves, flips and rotates a focused piece, and says so", async ({ page }) => {
    await page.goto(PREVIEW);
    const token = piece(page, "token-1");
    await token.focus();

    await page.keyboard.press("ArrowRight");
    let proposed = await intents(page);
    expect(proposed.map((intent) => intent.op_type)).toEqual(["move", "release"]);
    expect(proposed[0]!.payload).toMatchObject({ piece_id: "token-1", x: 200, y: 160 });
    expect((await visual(page, "token-1"))[0]).toBeCloseTo(200, 0);
    await expect(page.locator("[data-announcer]")).toHaveText(/3 moved right\./);

    await page.keyboard.press("Shift+ArrowDown");
    proposed = await intents(page);
    expect(proposed.at(-2)!.payload).toMatchObject({ x: 200, y: 260 });

    await page.keyboard.press("Enter");
    await page.keyboard.press("r");
    await page.keyboard.press("Shift+R");
    proposed = await intents(page);
    expect(proposed.slice(-3).map((intent) => [intent.op_type, intent.payload["degrees"]])).toEqual([
      ["flip", undefined],
      ["rotate", 90],
      ["rotate", -90],
    ]);
    await expect(token).toBeFocused();
  });

  test("every piece can be reached with Tab", async ({ page }) => {
    await page.goto(PREVIEW);
    const reachable = await page.locator("[data-piece-id]").evaluateAll((nodes) =>
      nodes.every((node) => (node as HTMLElement).tabIndex === 0),
    );
    expect(reachable).toBe(true);
  });
});

test.describe("pointing and ink", () => {
  test("alt-click and the Point button each place a marker", async ({ page }) => {
    await page.goto(PREVIEW);
    const spot = await onScreen(page, 700, 250);
    await page.keyboard.down("Alt");
    await page.mouse.click(spot.x, spot.y);
    await page.keyboard.up("Alt");

    let point = (await intents(page)).at(-1)!;
    expect(point.op_type).toBe("point");
    expect(point.payload["x"]).toBeCloseTo(700, 0);
    expect(point.payload["y"]).toBeCloseTo(250, 0);

    const button = page.getByRole("button", { name: "Point" });
    await button.click();
    await expect(button).toHaveAttribute("aria-pressed", "true");
    const other = await onScreen(page, 600, 300);
    await page.mouse.click(other.x, other.y);
    point = (await intents(page)).at(-1)!;
    expect(point.op_type).toBe("point");
    expect(point.payload["x"]).toBeCloseTo(600, 0);
    await expect(button).toHaveAttribute("aria-pressed", "false");
  });

  test("the pen draws one stroke, and ink can be cleared", async ({ page }) => {
    await page.goto(PREVIEW);
    await page.getByRole("button", { name: "Pen" }).click();
    await drag(page, await onScreen(page, 100, 850), await onScreen(page, 300, 900));

    const ink = (await intents(page)).filter((intent) => intent.op_type.startsWith("ink_"));
    expect(ink[0]!.op_type).toBe("ink_begin");
    expect(ink.at(-1)!.op_type).toBe("ink_end");
    expect(ink.some((intent) => intent.op_type === "ink_append")).toBe(true);
    expect(new Set(ink.map((intent) => intent.payload["stroke_id"])).size).toBe(1);
    expect(ink[0]!.payload["colour"]).toMatch(/\S/);

    await page.getByRole("button", { name: "Clear my ink" }).click();
    expect((await intents(page)).at(-1)!.payload).toMatchObject({ everyone: false });
    // This viewer is the facilitator in the recording, so may clear everyone's.
    await page.getByRole("button", { name: "Clear all ink" }).click();
    expect((await intents(page)).at(-1)!.payload).toMatchObject({ everyone: true });
  });
});

test("announces a piece arriving somewhere new", async ({ page }) => {
  await page.goto(PREVIEW);
  await inject(page, {
    type: "patches",
    seq: 90,
    patches: [
      { kind: "piece", op: "upsert", entity_id: "deck-0", fields: { zone_id: "discard" } },
    ],
  });
  await expect(page.locator("[data-announcer]")).toHaveText(
    /Face-down card moved to Set aside\./,
  );
});
