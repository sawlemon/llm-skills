import { useEffect, useMemo, useState } from 'react';
import reportCard from 'virtual:report-card';
import type { ModelEntry } from './data/types';
import { FilterBar } from './components/FilterBar';
import { ModelCard } from './components/ModelCard';
import { ModelDetail } from './components/ModelDetail';
import { EMPTY_FILTERS, filterModels, type Filters } from './lib/filterModels';
import { useHashModel } from './lib/useHashModel';

export default function App() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [selectedId, setSelectedId] = useHashModel();

  const results = useMemo(() => filterModels(reportCard.models, filters), [filters]);
  const selected =
    reportCard.models.find((model) => model.id === selectedId) ??
    reportCard.harnesses.find((harness) => harness.id === selectedId) ??
    null;

  // A hash pointing at a model that no longer exists should not leave a dead URL.
  useEffect(() => {
    if (selectedId && !selected) setSelectedId(null);
  }, [selectedId, selected, setSelectedId]);

  const groups = useMemo(() => {
    const byProvider = new Map<string, ModelEntry[]>();
    for (const model of results) {
      const bucket = byProvider.get(model.provider);
      if (bucket) bucket.push(model);
      else byProvider.set(model.provider, [model]);
    }
    return Array.from(byProvider, ([provider, models]) => ({ provider, models }));
  }, [results]);

  return (
    <>
      <a className="skip-link" href="#gallery">
        Skip to models
      </a>

      <header className="nav">
        <div className="nav__inner">
          <span className="nav__title">{reportCard.title}</span>
          <span className="nav__meta">
            {reportCard.models.length} models · {reportCard.providers.length} providers
            {reportCard.harnesses.length > 0 ? ` · ${reportCard.harnesses.length} harnesses` : ''}
          </span>
        </div>
      </header>

      <main>
        <section className="hero">
          <h1 className="hero__headline">Notes on how these models actually behave.</h1>
          <p className="hero__body">
            A personal, continuously updated record of what I&apos;ve observed while using these models day to
            day. These are subjective impressions from my own workflows — not benchmark results, not
            measurements, and not universal advice.
          </p>
        </section>

        <FilterBar
          providers={reportCard.providers}
          aspects={reportCard.aspects}
          filters={filters}
          resultCount={results.length}
          onChange={setFilters}
        />

        <section className="gallery" id="gallery" aria-label="Model gallery">
          {groups.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state__title">No models match those filters.</p>
              <button type="button" className="text-button" onClick={() => setFilters(EMPTY_FILTERS)}>
                Reset filters
              </button>
            </div>
          ) : (
            groups.map((group) => (
              <div className="gallery__group" key={group.provider}>
                <h2 className="gallery__heading">{group.provider}</h2>
                <div className="gallery__grid">
                  {group.models.map((model) => (
                    <ModelCard
                      key={model.id}
                      model={model}
                      highlightAspect={filters.aspect}
                      onSelect={setSelectedId}
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </section>

        {reportCard.harnesses.length > 0 ? (
          <section className="gallery gallery--harness" aria-label="LLM harness gallery">
            <div className="gallery__group">
              <div className="gallery__section-head">
                <h2 className="gallery__heading">LLM Harnesses</h2>
                <p className="gallery__section-note">
                  The apps and CLIs models run inside — judged on the harness itself, not the model.
                </p>
              </div>
              <div className="gallery__grid">
                {reportCard.harnesses.map((harness) => (
                  <ModelCard key={harness.id} model={harness} highlightAspect={null} onSelect={setSelectedId} />
                ))}
              </div>
            </div>
          </section>
        ) : null}
      </main>

      <footer className="footer">
        <p>
          Generated from <code>LLM_REPORT_CARD.md</code>, the single source of truth. Every deployment
          rebuilds this page from that file.
        </p>
      </footer>

      {selected ? <ModelDetail model={selected} onClose={() => setSelectedId(null)} /> : null}
    </>
  );
}
