import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fixtureModel } from '../data/__fixtures__/fixtureCard';
import { ModelCard } from './ModelCard';

describe('ModelCard', () => {
  const prime = fixtureModel('Acme Prime 2');
  const mini = fixtureModel('Acme Mini');

  it('announces the model, its provider and its tallies', () => {
    render(<ModelCard model={prime} highlightAspect={null} onSelect={() => {}} />);

    expect(
      screen.getByRole('button', {
        name: 'Acme Prime 2 by Acme Labs, 7 strengths and 5 weaknesses noted',
      }),
    ).toBeInTheDocument();
  });

  it('previews the "Other" note when no aspect is highlighted', () => {
    render(<ModelCard model={prime} highlightAspect={null} onSelect={() => {}} />);

    expect(screen.getByText('Other')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveTextContent('favourite for refactors');
  });

  it('previews the highlighted aspect instead, rendering inline code', () => {
    render(<ModelCard model={prime} highlightAspect="Coding" onSelect={() => {}} />);

    expect(screen.getByText('Coding')).toBeInTheDocument();
    const card = screen.getByRole('button');
    expect(card).toHaveTextContent('patches parseReportCard.ts without breaking callers');
    expect(card.querySelector('code')).toHaveTextContent('parseReportCard.ts');
  });

  it('falls back to the first con when the highlighted aspect has only cons', () => {
    render(<ModelCard model={prime} highlightAspect="Cost / efficiency" onSelect={() => {}} />);

    expect(screen.getByRole('button')).toHaveTextContent('token-hungry on long agent runs');
  });

  it('says nothing is recorded when the highlighted aspect is empty', () => {
    render(<ModelCard model={prime} highlightAspect="Context handling" onSelect={() => {}} />);

    expect(screen.getByText('No observations recorded yet.')).toBeInTheDocument();
  });

  it('says nothing is recorded for a model with no observations', () => {
    render(<ModelCard model={mini} highlightAspect={null} onSelect={() => {}} />);

    expect(screen.getByText('No observations recorded yet.')).toBeInTheDocument();
  });

  it('reports its model id when activated', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ModelCard model={prime} highlightAspect={null} onSelect={onSelect} />);

    await user.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledWith('acme-labs--acme-prime-2');
  });
});
