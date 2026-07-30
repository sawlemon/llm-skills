import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseReportCard, splitNotes, slugify } from './parseReportCard';
import { CANONICAL_ASPECTS, ReportCardParseError } from './types';
import { fixtureCard, fixtureModel } from './__fixtures__/fixtureCard';

const realSource = readFileSync(resolve(__dirname, '../../../../LLM_REPORT_CARD.md'), 'utf8');

/**
 * Grammar and behaviour are pinned against the fixture, which never changes underneath these
 * assertions, so they can be exact.
 */
describe('parseReportCard on the fixture document', () => {
  const card = fixtureCard;

  it('reads the document title', () => {
    expect(card.title).toBe('Fixture Report Card');
  });

  it('ignores the fenced authoring template', () => {
    expect(card.providers.map((provider) => provider.name)).not.toContain('Provider');
    expect(card.models.map((model) => model.name)).not.toContain('Model name (exact id if known)');
    const everyNote = card.models.flatMap((model) =>
      model.aspects.flatMap((entry) => [...entry.pros, ...entry.cons]),
    );
    expect(everyNote.join(' ')).not.toContain('must never be parsed');
  });

  it('extracts every provider in source order', () => {
    expect(card.providers.map((provider) => provider.name)).toEqual([
      'Acme Labs',
      'Globex (Speech-to-Text / ASR)',
    ]);
  });

  it('groups models under the provider heading above them', () => {
    expect(card.providers.map((provider) => provider.models.map((model) => model.name))).toEqual([
      ['Acme Prime 2', 'Acme Mini'],
      ['Globex Echo 0.6B'],
    ]);
  });

  it('flattens every model in source order and back-links it to its provider', () => {
    expect(card.models.map((model) => model.name)).toEqual(['Acme Prime 2', 'Acme Mini', 'Globex Echo 0.6B']);
    for (const model of card.models) {
      const provider = card.providers.find((entry) => entry.id === model.providerId);
      expect(provider?.name).toBe(model.provider);
      expect(provider?.models).toContain(model);
    }
  });

  it('generates unique, url-safe, provider-scoped model ids', () => {
    expect(card.models.map((model) => model.id)).toEqual([
      'acme-labs--acme-prime-2',
      'acme-labs--acme-mini',
      'globex-speech-to-text-asr--globex-echo-0-6b',
    ]);
  });

  it('collects the union of aspects used, in canonical order', () => {
    expect(card.aspects).toEqual([...CANONICAL_ASPECTS]);
  });

  it('keeps a model rows in source order, even when it lists only some aspects', () => {
    expect(fixtureModel('Globex Echo 0.6B').aspects.map((entry) => entry.aspect)).toEqual([
      'Context handling',
      'Speed / latency',
      'Formatting / output quality',
      'Other',
    ]);
  });

  it('splits a cell into separate notes on semicolons', () => {
    const reasoning = fixtureModel('Acme Prime 2').aspects.find((entry) => entry.aspect === 'Reasoning');
    expect(reasoning?.pros).toEqual(['plans multi-step tasks well', 'states its assumptions up front']);
    expect(reasoning?.cons).toEqual(['loses the thread past ten steps']);
  });

  it('keeps a semicolon nested in parentheses inside one note', () => {
    const tools = fixtureModel('Acme Prime 2').aspects.find((entry) => entry.aspect === 'Tool use / agentic');
    expect(tools?.pros).toEqual(['picks the right tool first try (even when two tools overlap; no retries)']);
  });

  it('unescapes pipes and preserves inline backticks verbatim', () => {
    const rows = fixtureModel('Acme Prime 2').aspects;
    expect(rows.find((entry) => entry.aspect === 'Formatting / output quality')?.pros).toEqual([
      'renders `a | b` inside a table cell correctly',
    ]);
    expect(rows.find((entry) => entry.aspect === 'Coding')?.pros).toEqual([
      'patches `parseReportCard.ts` without breaking callers',
    ]);
  });

  it('leaves empty cells as empty arrays', () => {
    const context = fixtureModel('Acme Prime 2').aspects.find((entry) => entry.aspect === 'Context handling');
    expect(context).toEqual({ aspect: 'Context handling', pros: [], cons: [] });
  });

  it('records covered aspects and pro/con tallies', () => {
    const model = fixtureModel('Acme Prime 2');
    expect(model.coveredAspects).toEqual([
      'Reasoning',
      'Coding',
      'Instruction-following',
      'Tool use / agentic',
      'Speed / latency',
      'Cost / efficiency',
      'Formatting / output quality',
      'Other',
    ]);
    expect(model.prosCount).toBe(7);
    expect(model.consCount).toBe(5);
  });

  it('keeps a model whose every cell is empty, with nothing covered', () => {
    const model = fixtureModel('Acme Mini');
    expect(model.aspects).toHaveLength(CANONICAL_ASPECTS.length);
    expect(model.coveredAspects).toEqual([]);
    expect(model.prosCount).toBe(0);
    expect(model.consCount).toBe(0);
  });
});

/**
 * The real document is content, not code: the owner edits it almost daily. Only invariants that
 * hold for *any* valid card belong here — no counts, no names, no note text — so a content edit
 * can never fail the test suite. Schema violations are caught by the validator
 * (`npm run validate -w report-card`) and by the build, which both parse the real file.
 */
describe('the real report card', () => {
  it('parses and satisfies the invariants every valid card must hold', () => {
    expect(() => parseReportCard(realSource)).not.toThrow();
    const card = parseReportCard(realSource);

    expect(card.providers.length).toBeGreaterThan(0);
    expect(card.models.length).toBeGreaterThan(0);

    const ids = card.models.map((model) => model.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z0-9-]+$/);

    for (const model of card.models) {
      const provider = card.providers.find((entry) => entry.id === model.providerId);
      expect(provider?.name).toBe(model.provider);
      expect(provider?.models).toContain(model);
    }

    const grouped = card.providers.reduce((total, provider) => total + provider.models.length, 0);
    expect(card.models).toHaveLength(grouped);

    for (const aspect of card.aspects) expect(CANONICAL_ASPECTS).toContain(aspect);
  });
});

describe('parseReportCard validation', () => {
  const table = ['| Aspect | Pros | Cons |', '|---|---|---|', '| Reasoning | fast | |'].join('\n');

  it('accepts a minimal well-formed document', () => {
    const card = parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${table}\n`);
    expect(card.models[0]).toMatchObject({
      name: 'Model X',
      provider: 'Acme',
      prosCount: 1,
      consCount: 0,
    });
  });

  it('rejects a model heading without a provider', () => {
    expect(() => parseReportCard(`# Card\n\n### Model X\n\n${table}\n`)).toThrow(
      /LLM_REPORT_CARD\.md:3:.*before any provider heading/,
    );
  });

  it('rejects a model without a table', () => {
    expect(() => parseReportCard('# Card\n\n## Acme\n\n### Model X\n\nsome prose\n')).toThrow(
      /model "Model X" has no aspect table/,
    );
  });

  it('rejects unexpected table columns', () => {
    const wrong = ['| Aspect | Notes |', '|---|---|', '| Reasoning | fast |'].join('\n');
    expect(() => parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${wrong}\n`)).toThrow(
      /expected \[Aspect, Pros, Cons\]/,
    );
  });

  it('rejects a row with the wrong number of columns', () => {
    const ragged = ['| Aspect | Pros | Cons |', '|---|---|---|', '| Reasoning | fast |'].join('\n');
    expect(() => parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${ragged}\n`)).toThrow(
      /has a row with 2 column\(s\)/,
    );
  });

  it('rejects a row with an empty aspect', () => {
    const blank = ['| Aspect | Pros | Cons |', '|---|---|---|', '|  | fast | |'].join('\n');
    expect(() => parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${blank}\n`)).toThrow(/empty Aspect/);
  });

  it('rejects an aspect that is not canonical, suggesting the near miss', () => {
    const typo = ['| Aspect | Pros | Cons |', '|---|---|---|', '| Tool use/agentic | fast | |'].join('\n');
    try {
      parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${typo}\n`);
      expect.unreachable('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(ReportCardParseError);
      const parseError = error as ReportCardParseError;
      expect(parseError.message).toContain('unknown aspect "Tool use/agentic"');
      expect(parseError.message).toContain('did you mean "Tool use / agentic"?');
      // The offending row, not the model heading two lines above it.
      expect(parseError.line).toBe(9);
      expect(parseError.message).toContain('LLM_REPORT_CARD.md:9:');
    }
  });

  it('rejects an aspect resembling nothing canonical, listing the allowed names', () => {
    const invented = ['| Aspect | Pros | Cons |', '|---|---|---|', '| Vibes | good | |'].join('\n');
    expect(() => parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${invented}\n`)).toThrow(
      `model "Model X" has unknown aspect "Vibes"; expected one of [${CANONICAL_ASPECTS.join(', ')}]`,
    );
  });

  it('returns card aspects in canonical order while model rows keep source order', () => {
    const scrambled = [
      '| Aspect | Pros | Cons |',
      '|---|---|---|',
      '| Other | last in canon | |',
      '| Coding | middle in canon | |',
      '| Reasoning | first in canon | |',
    ].join('\n');
    const card = parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${scrambled}\n`);

    expect(card.aspects).toEqual(['Reasoning', 'Coding', 'Other']);
    expect(card.models[0].aspects.map((entry) => entry.aspect)).toEqual(['Other', 'Coding', 'Reasoning']);
  });

  it('rejects a table before any model heading', () => {
    expect(() => parseReportCard(`# Card\n\n## Acme\n\n${table}\n`)).toThrow(/outside of a model section/);
  });

  it('rejects duplicate models under one provider', () => {
    const doc = `# Card\n\n## Acme\n\n### Model X\n\n${table}\n\n### Model X\n\n${table}\n`;
    expect(() => parseReportCard(doc)).toThrow(/duplicate model "Model X"/);
  });

  it('rejects a document with no models', () => {
    expect(() => parseReportCard('# Card\n\nJust prose.\n')).toThrow(/no models found/);
  });

  it('reports errors as ReportCardParseError with a line number', () => {
    try {
      parseReportCard(`# Card\n\n### Model X\n\n${table}\n`);
      expect.unreachable('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(ReportCardParseError);
      expect((error as ReportCardParseError).line).toBe(3);
    }
  });
});

describe('splitNotes', () => {
  it('splits on top-level semicolons', () => {
    expect(splitNotes('one; two;three')).toEqual(['one', 'two', 'three']);
  });

  it('keeps semicolons inside parentheses together', () => {
    expect(splitNotes('a (x; y); b')).toEqual(['a (x; y)', 'b']);
  });

  it('returns an empty list for a blank cell', () => {
    expect(splitNotes('   ')).toEqual([]);
  });
});

describe('slugify', () => {
  it('produces url-safe ids', () => {
    expect(slugify('NVIDIA (Speech-to-Text / ASR)')).toBe('nvidia-speech-to-text-asr');
    expect(slugify('!!!')).toBe('section');
  });
});
