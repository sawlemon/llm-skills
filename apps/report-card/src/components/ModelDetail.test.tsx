import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fixtureModel } from '../data/__fixtures__/fixtureCard';
import { ModelDetail } from './ModelDetail';

/** The cells of the row whose rowheader is `aspect`, as [pros, cons]. */
function cellsFor(aspect: string) {
  const dialog = screen.getByRole('dialog');
  const row = within(dialog).getByRole('rowheader', { name: aspect }).closest('tr');
  return within(row as HTMLTableRowElement).getAllByRole('cell');
}

describe('ModelDetail', () => {
  const prime = fixtureModel('Acme Prime 2');
  const mini = fixtureModel('Acme Mini');

  it('names the model and its provider', () => {
    render(<ModelDetail model={prime} onClose={() => {}} />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByRole('heading', { name: 'Acme Prime 2' })).toBeInTheDocument();
    expect(within(dialog).getByText('Acme Labs')).toBeInTheDocument();
  });

  it('renders one row per aspect in source order, including the empty ones', () => {
    render(<ModelDetail model={prime} onClose={() => {}} />);

    const rows = within(screen.getByRole('dialog')).getAllByRole('rowheader');
    expect(rows.map((row) => row.textContent)).toEqual(prime.aspects.map((entry) => entry.aspect));
  });

  it('lists every pro and con of a row as its own item', () => {
    render(<ModelDetail model={prime} onClose={() => {}} />);

    const [pros, cons] = cellsFor('Reasoning');
    expect(
      within(pros)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['plans multi-step tasks well', 'states its assumptions up front']);
    expect(
      within(cons)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['loses the thread past ten steps']);
  });

  it('renders a backticked run inside a note as code', () => {
    render(<ModelDetail model={prime} onClose={() => {}} />);

    const [pros] = cellsFor('Formatting / output quality');
    const item = within(pros).getByRole('listitem');
    expect(item).toHaveTextContent('renders a | b inside a table cell correctly');
    expect(item.querySelector('code')).toHaveTextContent('a | b');
  });

  it('marks a row with no observations as none recorded on both sides', () => {
    render(<ModelDetail model={prime} onClose={() => {}} />);

    const [pros, cons] = cellsFor('Context handling');
    expect(within(pros).getByLabelText('none recorded')).toBeInTheDocument();
    expect(within(cons).getByLabelText('none recorded')).toBeInTheDocument();
    expect(within(pros).queryAllByRole('listitem')).toHaveLength(0);
  });

  it('replaces the table with a message when nothing is recorded at all', () => {
    render(<ModelDetail model={mini} onClose={() => {}} />);

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('No observations recorded for this model yet.')).toBeInTheDocument();
  });

  it('focuses Close on open and closes on Escape', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<ModelDetail model={prime} onClose={onClose} />);

    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps Tab inside the dialog', async () => {
    const user = userEvent.setup();
    render(<ModelDetail model={prime} onClose={() => {}} />);

    const copy = screen.getByRole('button', { name: 'Copy link to this model' });
    const close = screen.getByRole('button', { name: 'Close' });

    expect(close).toHaveFocus();
    await user.tab();
    expect(copy).toHaveFocus();
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
  });

  it('copies a deep link to the model', async () => {
    const user = userEvent.setup();
    render(<ModelDetail model={prime} onClose={() => {}} />);

    await user.click(screen.getByRole('button', { name: 'Copy link to this model' }));

    const copied = await navigator.clipboard.readText();
    expect(copied).toBe(
      `${window.location.origin}${window.location.pathname}#${encodeURIComponent(prime.id)}`,
    );
  });
});
