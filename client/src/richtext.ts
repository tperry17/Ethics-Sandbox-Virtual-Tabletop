/**
 * A card or sheet's text, drawn as real text. The server sends a small
 * subset of Markdown and nothing else: `**bold**`, `*italic*`, a `# `
 * heading line, a blank line between paragraphs, `- ` and `1. ` list items,
 * and `\*` for a literal asterisk. Text with none of those is one plain
 * paragraph. Everything is built with `textContent`, never as markup.
 */

const TOKEN = /\\\*|\*\*(.+?)\*\*|\*(.+?)\*/g;

function inline(parent: HTMLElement, text: string): void {
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const at = match.index ?? 0;
    if (at > last) parent.append(text.slice(last, at));
    if (match[0] === "\\*") {
      parent.append("*");
    } else {
      const node = document.createElement(match[1] !== undefined ? "strong" : "em");
      inline(node, match[1] ?? match[2] ?? "");
      parent.append(node);
    }
    last = at + match[0].length;
  }
  if (last < text.length) parent.append(text.slice(last));
}

export function renderRichText(container: HTMLElement, text: string): void {
  let list: HTMLElement | null = null;
  const blocks = text.split(/\n{2,}/);
  for (const block of blocks) {
    for (const line of block.split("\n")) {
      const item = /^(?:- |\d+\. )(.*)$/.exec(line);
      if (item !== null) {
        const ordered = /^\d/.test(line);
        const wanted = ordered ? "OL" : "UL";
        if (list === null || list.tagName !== wanted) {
          list = document.createElement(wanted.toLowerCase());
          list.className = "piece__list";
          container.append(list);
        }
        const li = document.createElement("li");
        inline(li, item[1] ?? "");
        list.append(li);
        continue;
      }
      list = null;
      const heading = /^# (.*)$/.exec(line);
      const node = document.createElement(heading !== null ? "strong" : "span");
      node.className = heading !== null ? "piece__heading" : "piece__paragraph";
      inline(node, heading !== null ? (heading[1] ?? "") : line);
      container.append(node);
    }
    list = null;
  }
}
