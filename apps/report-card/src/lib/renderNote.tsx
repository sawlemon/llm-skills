import type { ReactNode } from 'react';

/**
 * Matches a backtick-delimited span with at least one non-backtick character,
 * so an empty pair (``) and a lone trailing backtick both fall through as text.
 */
const INLINE_CODE = /`([^`]+)`/g;

/**
 * Renders a note string as React nodes, turning `backtick-delimited` runs into
 * `<code>` elements. Everything else stays plain text, so nothing is ever
 * interpreted as markup — no `dangerouslySetInnerHTML`, no markdown dependency.
 *
 * Unmatched backticks are left as literal characters rather than swallowing the
 * rest of the note, and an empty pair never produces an empty `<code>`.
 */
export function renderNote(note: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  for (const match of note.matchAll(INLINE_CODE)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(note.slice(cursor, start));
    nodes.push(<code key={`code-${start}`}>{match[1]}</code>);
    cursor = start + match[0].length;
  }

  if (cursor < note.length) nodes.push(note.slice(cursor));
  return nodes;
}
