import { describe, expect, it } from 'vitest';
import { EMPTY_FILTERS, filterModels } from './filterModels';
import type { ModelEntry } from '../data/types';

function model(partial: Partial<ModelEntry> & Pick<ModelEntry, 'id' | 'name'>): ModelEntry {
  const aspects = partial.aspects ?? [];
  return {
    provider: 'Acme',
    providerId: 'acme',
    aspects,
    coveredAspects: aspects.filter((a) => a.pros.length || a.cons.length).map((a) => a.aspect),
    prosCount: aspects.reduce((n, a) => n + a.pros.length, 0),
    consCount: aspects.reduce((n, a) => n + a.cons.length, 0),
    ...partial,
  };
}

const alpha = model({
  id: 'acme--alpha',
  name: 'Alpha',
  aspects: [
    { aspect: 'Coding', pros: ['refactors cleanly'], cons: [] },
    { aspect: 'Speed / latency', pros: [], cons: [] },
  ],
});

const beta = model({
  id: 'globex--beta',
  name: 'Beta',
  provider: 'Globex',
  providerId: 'globex',
  aspects: [
    { aspect: 'Coding', pros: [], cons: [] },
    { aspect: 'Speed / latency', pros: [], cons: ['very slow to respond'] },
  ],
});

const models = [alpha, beta];

describe('filterModels', () => {
  it('returns everything with no filters', () => {
    expect(filterModels(models, EMPTY_FILTERS)).toEqual(models);
  });

  it('filters by provider', () => {
    expect(filterModels(models, { ...EMPTY_FILTERS, providerId: 'globex' })).toEqual([beta]);
  });

  it('filters by aspect coverage, not mere presence of the row', () => {
    expect(filterModels(models, { ...EMPTY_FILTERS, aspect: 'Coding' })).toEqual([alpha]);
    expect(filterModels(models, { ...EMPTY_FILTERS, aspect: 'Speed / latency' })).toEqual([beta]);
  });

  it('searches model names case-insensitively', () => {
    expect(filterModels(models, { ...EMPTY_FILTERS, query: 'ALPHA' })).toEqual([alpha]);
  });

  it('searches provider names', () => {
    expect(filterModels(models, { ...EMPTY_FILTERS, query: 'globex' })).toEqual([beta]);
  });

  it('searches note text', () => {
    expect(filterModels(models, { ...EMPTY_FILTERS, query: 'slow to respond' })).toEqual([beta]);
  });

  it('combines filters conjunctively', () => {
    expect(filterModels(models, { query: 'refactors', providerId: 'globex', aspect: null })).toEqual([]);
  });

  it('ignores surrounding whitespace in the query', () => {
    expect(filterModels(models, { ...EMPTY_FILTERS, query: '  alpha  ' })).toEqual([alpha]);
  });
});
