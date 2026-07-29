import type { ModelEntry } from '../data/types';

export interface Filters {
  query: string;
  providerId: string | null;
  aspect: string | null;
}

export const EMPTY_FILTERS: Filters = { query: '', providerId: null, aspect: null };

function matchesQuery(model: ModelEntry, needle: string): boolean {
  if (model.name.toLowerCase().includes(needle)) return true;
  if (model.provider.toLowerCase().includes(needle)) return true;
  return model.aspects.some(
    (entry) =>
      entry.aspect.toLowerCase().includes(needle) ||
      entry.pros.some((note) => note.toLowerCase().includes(needle)) ||
      entry.cons.some((note) => note.toLowerCase().includes(needle)),
  );
}

export function filterModels(models: ModelEntry[], filters: Filters): ModelEntry[] {
  const needle = filters.query.trim().toLowerCase();

  return models.filter((model) => {
    if (filters.providerId && model.providerId !== filters.providerId) return false;
    if (filters.aspect && !model.coveredAspects.includes(filters.aspect)) return false;
    if (needle && !matchesQuery(model, needle)) return false;
    return true;
  });
}
