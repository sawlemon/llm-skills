import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import reportCard from 'virtual:report-card';
import App from './App';
import type { ModelEntry } from './data/types';
import { EMPTY_FILTERS, filterModels, type Filters } from './lib/filterModels';

/**
 * These tests wire up the real `LLM_REPORT_CARD.md` through `virtual:report-card`, and that
 * document is content the owner edits almost daily. So nothing below names a provider, a model,
 * an aspect, a note or a count: every expectation is derived from the imported data, with
 * `filterModels` as the oracle for what the UI should be showing. Exact content assertions live
 * in the fixture-driven tests (`data/parseReportCard.test.ts`, `components/*.test.tsx`).
 */
const { models, providers } = reportCard;

const allModels = `${models.length} models`;

/** How the filter bar words a result count. */
function count(n: number): string {
  return `${n} ${n === 1 ? 'model' : 'models'}`;
}

/** The accessible name `ModelCard` gives a model — unique across the card. */
function label(model: ModelEntry): string {
  return `${model.name} by ${model.provider}, ${model.prosCount} strengths and ${model.consCount} weaknesses noted`;
}

function cardFor(model: ModelEntry) {
  return screen.getByRole('button', { name: label(model) });
}

function queryCardFor(model: ModelEntry) {
  return screen.queryByRole('button', { name: label(model) });
}

function matching(filters: Partial<Filters>): ModelEntry[] {
  return filterModels(models, { ...EMPTY_FILTERS, ...filters });
}

/** Notes render backticked runs as `<code>`, which drops the delimiters from the text. */
function plain(note: string): string {
  return note.replaceAll('`', '');
}

/** The provider with the fewest models: filtering by it hides the most. */
const narrowestProvider = providers.reduce((a, b) => (b.models.length < a.models.length ? b : a));

/** A word only ever seen in note text, so searching for it must reach observations. */
const noteWord = (() => {
  const names = models.flatMap((model) => [model.name.toLowerCase(), model.provider.toLowerCase()]);
  const words = new Set(
    models
      .flatMap((model) => model.aspects.flatMap((entry) => [...entry.pros, ...entry.cons]))
      .flatMap((note) => note.toLowerCase().match(/[a-z]{6,}/g) ?? []),
  );
  for (const word of words) {
    if (!names.some((name) => name.includes(word))) return word;
  }
  return null;
})();

/** An aspect some models cover and others do not, so filtering by it is observable. */
const partialAspect =
  reportCard.aspects.find((aspect) => {
    const covering = matching({ aspect });
    return covering.length > 0 && covering.length < models.length;
  }) ?? reportCard.aspects[0];

/** The model with the most recorded observations — its dialog has the most to show. */
const richestModel = models.reduce((a, b) => (b.prosCount + b.consCount > a.prosCount + a.consCount ? b : a));

function setHash(hash: string) {
  window.history.replaceState(null, '', hash ? `/#${hash}` : '/');
}

beforeEach(() => setHash(''));
afterEach(() => setHash(''));

describe('gallery', () => {
  it('renders every model, grouped under its provider', () => {
    render(<App />);

    for (const provider of providers) {
      expect(screen.getByRole('heading', { name: provider.name })).toBeInTheDocument();
      for (const model of provider.models) expect(cardFor(model)).toBeInTheDocument();
    }
    expect(screen.getByRole('status')).toHaveTextContent(allModels);
  });

  it('states that this is personal, non-benchmark data', () => {
    render(<App />);
    expect(screen.getByText(/not benchmark results/i)).toBeInTheDocument();
  });
});

describe('filtering and search', () => {
  it('filters by provider chip', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: narrowestProvider.name }));

    expect(screen.getByRole('status')).toHaveTextContent(count(narrowestProvider.models.length));
    for (const model of narrowestProvider.models) expect(cardFor(model)).toBeInTheDocument();
    for (const model of models) {
      if (model.providerId !== narrowestProvider.id) {
        expect(queryCardFor(model)).not.toBeInTheDocument();
      }
    }
  });

  it('toggles a provider chip off when clicked twice', async () => {
    const user = userEvent.setup();
    render(<App />);
    const chip = screen.getByRole('button', { name: narrowestProvider.name });

    await user.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await user.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('status')).toHaveTextContent(allModels);
  });

  it('searches observation text, not just names', async () => {
    const user = userEvent.setup();
    // Every card has notes; if this ever fails, the document lost all of them.
    expect(noteWord).not.toBeNull();
    const query = noteWord as string;
    const expected = matching({ query });
    render(<App />);

    await user.type(screen.getByRole('searchbox'), query);

    expect(expected.length).toBeGreaterThan(0);
    expect(expected.length).toBeLessThan(models.length);
    expect(screen.getByRole('status')).toHaveTextContent(count(expected.length));
    for (const model of expected) expect(cardFor(model)).toBeInTheDocument();
    for (const model of models) {
      if (!expected.includes(model)) expect(queryCardFor(model)).not.toBeInTheDocument();
    }
  });

  it('filters by aspect using recorded observations', async () => {
    const user = userEvent.setup();
    const expected = matching({ aspect: partialAspect });
    render(<App />);

    await user.selectOptions(screen.getByRole('combobox'), partialAspect);

    expect(screen.getByRole('status')).toHaveTextContent(count(expected.length));
    for (const model of expected) expect(cardFor(model)).toBeInTheDocument();
    // Models that merely have the row, with both cells empty, must be filtered out.
    for (const model of models) {
      if (!expected.includes(model)) expect(queryCardFor(model)).not.toBeInTheDocument();
    }
  });

  it('shows an empty state and resets filters', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByRole('searchbox'), 'zzzznothing');
    expect(screen.getByText('No models match those filters.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));
    expect(screen.getByRole('status')).toHaveTextContent(allModels);
  });
});

describe('model detail', () => {
  it('opens an accessible dialog with the full pros/cons table', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(cardFor(richestModel));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByRole('heading', { name: richestModel.name })).toBeInTheDocument();
    // Every aspect row is present, including the ones with no observations.
    expect(within(dialog).getAllByRole('rowheader')).toHaveLength(richestModel.aspects.length);

    const covered = richestModel.aspects.find((entry) => entry.pros.length && entry.cons.length);
    if (covered) {
      expect(dialog).toHaveTextContent(plain(covered.pros[0]));
      expect(dialog).toHaveTextContent(plain(covered.cons[0]));
    }
  });

  it('moves focus into the dialog and closes on Escape', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(cardFor(models[0]));
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('can be opened with the keyboard', async () => {
    const user = userEvent.setup();
    render(<App />);

    cardFor(models[0]).focus();
    await user.keyboard('{Enter}');

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: models[0].name })).toBeInTheDocument();
  });

  it('writes a shareable fragment and clears it on close', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(cardFor(models[0]));
    expect(window.location.hash).toBe(`#${encodeURIComponent(models[0].id)}`);

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(window.location.hash).toBe('');
  });

  it('opens the model named in the URL fragment on load', () => {
    const target = models[models.length - 1];
    setHash(target.id);
    render(<App />);

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: target.name })).toBeInTheDocument();
  });

  it('ignores a fragment that names no known model', () => {
    setHash('nope--gone');
    render(<App />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
