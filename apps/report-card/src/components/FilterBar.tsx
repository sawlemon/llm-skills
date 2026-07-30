import { Search, X } from 'lucide-react';
import type { ProviderEntry } from '../data/types';
import type { Filters } from '../lib/filterModels';

interface FilterBarProps {
  providers: ProviderEntry[];
  aspects: string[];
  filters: Filters;
  resultCount: number;
  onChange: (next: Filters) => void;
}

export function FilterBar({ providers, aspects, filters, resultCount, onChange }: FilterBarProps) {
  const isFiltered = Boolean(filters.query || filters.providerId || filters.aspect);

  return (
    <div className="filter-bar">
      <div className="search">
        <Search aria-hidden="true" size={16} className="search__icon" />
        <input
          type="search"
          className="search__input"
          value={filters.query}
          placeholder="Search models and observations"
          aria-label="Search models and observations"
          onChange={(event) => onChange({ ...filters, query: event.target.value })}
        />
        {filters.query ? (
          <button
            type="button"
            className="search__clear"
            aria-label="Clear search"
            onClick={() => onChange({ ...filters, query: '' })}
          >
            <X aria-hidden="true" size={14} />
          </button>
        ) : null}
      </div>

      <div className="chips" role="group" aria-label="Filter by provider">
        <button
          type="button"
          className="chip"
          aria-pressed={filters.providerId === null}
          onClick={() => onChange({ ...filters, providerId: null })}
        >
          All providers
        </button>
        {providers.map((provider) => (
          <button
            key={provider.id}
            type="button"
            className="chip"
            aria-pressed={filters.providerId === provider.id}
            onClick={() =>
              onChange({ ...filters, providerId: filters.providerId === provider.id ? null : provider.id })
            }
          >
            {provider.name}
          </button>
        ))}
      </div>

      <div className="filter-bar__row">
        <label className="select">
          <span className="visually-hidden">Filter by aspect</span>
          <select
            value={filters.aspect ?? ''}
            onChange={(event) => onChange({ ...filters, aspect: event.target.value || null })}
          >
            <option value="">All aspects</option>
            {aspects.map((aspect) => (
              <option key={aspect} value={aspect}>
                {aspect}
              </option>
            ))}
          </select>
        </label>

        <p className="filter-bar__count" role="status" aria-live="polite">
          {resultCount} {resultCount === 1 ? 'model' : 'models'}
        </p>

        {isFiltered ? (
          <button
            type="button"
            className="text-button"
            onClick={() => onChange({ query: '', providerId: null, aspect: null })}
          >
            Reset
          </button>
        ) : null}
      </div>
    </div>
  );
}
