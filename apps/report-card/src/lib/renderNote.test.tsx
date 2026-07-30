import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderNote } from './renderNote';

/** Renders a note in isolation and reports its text plus the runs that became `<code>`. */
function renderedNote(note: string) {
  const { container } = render(<p>{renderNote(note)}</p>);
  const paragraph = container.querySelector('p') as HTMLParagraphElement;
  return {
    text: paragraph.textContent,
    code: Array.from(paragraph.querySelectorAll('code'), (element) => element.textContent),
    html: paragraph.innerHTML,
  };
}

describe('renderNote', () => {
  it('passes a note with no backticks through as plain text', () => {
    const { text, code } = renderedNote('sticks to the system prompt');
    expect(text).toBe('sticks to the system prompt');
    expect(code).toEqual([]);
  });

  it('wraps a backticked run in <code> and drops the delimiters', () => {
    const { text, code } = renderedNote('patches `parseReportCard.ts` cleanly');
    expect(text).toBe('patches parseReportCard.ts cleanly');
    expect(code).toEqual(['parseReportCard.ts']);
  });

  it('handles several runs and keeps the surrounding text in order', () => {
    const { text, code } = renderedNote('`a` then `b` then done');
    expect(text).toBe('a then b then done');
    expect(code).toEqual(['a', 'b']);
  });

  it('renders a note that begins and ends with code without empty text nodes', () => {
    expect(renderNote('`only`')).toHaveLength(1);
    const { text, code } = renderedNote('`only`');
    expect(text).toBe('only');
    expect(code).toEqual(['only']);
  });

  it('leaves an unmatched backtick as a literal character', () => {
    const { text, code } = renderedNote('costs about $3 ` per query');
    expect(text).toBe('costs about $3 ` per query');
    expect(code).toEqual([]);
  });

  it('never produces an empty <code> from an empty pair', () => {
    const { text, code } = renderedNote('an empty pair `` stays text');
    expect(text).toBe('an empty pair `` stays text');
    expect(code).toEqual([]);
  });

  it('escapes markup instead of interpreting it', () => {
    const { text, html } = renderedNote('warns about <b>bold</b> & co');
    expect(text).toBe('warns about <b>bold</b> & co');
    expect(html).not.toContain('<b>');
    expect(html).toContain('&lt;b&gt;');
  });

  it('returns an empty list for an empty note', () => {
    expect(renderNote('')).toEqual([]);
  });
});
