import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseReportCard, splitNotes, slugify } from './parseReportCard';
import { ReportCardParseError } from './types';

const source = readFileSync(resolve(__dirname, '../../LLM_REPORT_CARD.md'), 'utf8');

describe('parseReportCard on the real report card', () => {
  const card = parseReportCard(source);

  it('reads the document title', () => {
    expect(card.title).toBe('LLM Report Card');
  });

  it('ignores the fenced authoring template', () => {
    expect(card.providers.map((p) => p.name)).not.toContain('Provider');
    expect(card.models.map((m) => m.name)).not.toContain('Model name (exact id if known)');
  });

  it('extracts every provider in source order', () => {
    expect(card.providers.map((p) => p.name)).toEqual([
      'Anthropic',
      'OpenAI',
      'Google',
      'DeepSeek',
      'Zhipu AI',
      'xAI',
      'NVIDIA (Speech-to-Text / ASR)',
      'Unknown Provider',
    ]);
  });

  it('assigns every model to its provider', () => {
    expect(card.models).toHaveLength(15);
    for (const model of card.models) {
      const provider = card.providers.find((p) => p.id === model.providerId);
      expect(provider?.name).toBe(model.provider);
      expect(provider?.models).toContain(model);
    }
  });

  it('collects the ten standard aspects', () => {
    expect(card.aspects).toEqual([
      'Reasoning',
      'Coding',
      'Instruction-following',
      'Tool use / agentic',
      'Context handling',
      'Speed / latency',
      'Cost / efficiency',
      'Refusals / safety behavior',
      'Formatting / output quality',
      'Other',
    ]);
  });

  it('splits pros and cons into separate note lists', () => {
    const glm = card.models.find((m) => m.name === 'GLM 5.2');
    const reasoning = glm?.aspects.find((a) => a.aspect === 'Reasoning');
    expect(reasoning?.pros).toEqual([
      'does research very well',
      'admits when it does not know rather than making information up',
    ]);
    expect(reasoning?.cons).toEqual([
      'missed that CrowdStrike Falcon repo `xdr_indicators` is a Falcon LogScale repo where XDR indicators are stored',
    ]);
  });

  it('leaves empty cells as empty arrays', () => {
    const grok = card.models.find((m) => m.name === 'Grok 4.5');
    const speed = grok?.aspects.find((a) => a.aspect === 'Speed / latency');
    expect(speed).toEqual({ aspect: 'Speed / latency', pros: [], cons: [] });
  });

  it('records covered aspects and tallies', () => {
    const parakeet = card.models.find((m) => m.name === 'Parakeet V3');
    expect(parakeet?.coveredAspects).toEqual([
      'Context handling',
      'Speed / latency',
      'Formatting / output quality',
      'Other',
    ]);
    expect(parakeet?.prosCount).toBe(3);
    expect(parakeet?.consCount).toBe(2);
  });

  it('generates unique, url-safe model ids', () => {
    const ids = card.models.map((m) => m.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z0-9-]+$/);
    expect(ids).toContain('anthropic--claude-opus-5');
  });
});

describe('parseReportCard validation', () => {
  const table = ['| Aspect | Pros | Cons |', '|---|---|---|', '| Reasoning | fast | |'].join('\n');

  it('accepts a minimal well-formed document', () => {
    const card = parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${table}\n`);
    expect(card.models[0]).toMatchObject({ name: 'Model X', provider: 'Acme', prosCount: 1, consCount: 0 });
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
    expect(() => parseReportCard(`# Card\n\n## Acme\n\n### Model X\n\n${blank}\n`)).toThrow(
      /empty Aspect/,
    );
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
