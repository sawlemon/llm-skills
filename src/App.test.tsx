import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import App from './App';

function setHash(hash: string) {
  window.history.replaceState(null, '', hash ? `/#${hash}` : '/');
}

beforeEach(() => setHash(''));
afterEach(() => setHash(''));

describe('gallery', () => {
  it('renders every model grouped by provider', () => {
    render(<App />);
    expect(screen.getByRole('button', { name: /Claude Opus 5 by Anthropic/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'DeepSeek' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('15 models');
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

    await user.click(screen.getByRole('button', { name: 'DeepSeek' }));

    expect(screen.getByRole('status')).toHaveTextContent('1 model');
    expect(screen.queryByRole('button', { name: /Claude Opus 5 by/ })).not.toBeInTheDocument();
  });

  it('toggles a provider chip off when clicked twice', async () => {
    const user = userEvent.setup();
    render(<App />);
    const chip = screen.getByRole('button', { name: 'xAI' });

    await user.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await user.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('status')).toHaveTextContent('15 models');
  });

  it('searches observation text, not just names', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByRole('searchbox'), 'tamil');

    expect(screen.getByRole('status')).toHaveTextContent('1 model');
    expect(screen.getByRole('button', { name: /Parakeet Unified ENG 0\.6B by/ })).toBeInTheDocument();
  });

  it('filters by aspect using recorded observations', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.selectOptions(screen.getByRole('combobox'), 'Cost / efficiency');

    expect(screen.queryByRole('button', { name: /Grok 4\.5 by/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /GLM 5\.2 by/ })).toBeInTheDocument();
  });

  it('shows an empty state and resets filters', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByRole('searchbox'), 'zzzznothing');
    expect(screen.getByText('No models match those filters.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));
    expect(screen.getByRole('status')).toHaveTextContent('15 models');
  });
});

describe('model detail', () => {
  it('opens an accessible dialog with the full pros/cons table', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: /GLM 5\.2 by/ }));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByRole('heading', { name: 'GLM 5.2' })).toBeInTheDocument();
    expect(within(dialog).getByText('does research very well')).toBeInTheDocument();
    expect(within(dialog).getByText(/high-thinking mode expensive/)).toBeInTheDocument();
    // Every aspect row is present, including the ones with no observations.
    expect(within(dialog).getAllByRole('rowheader')).toHaveLength(10);
  });

  it('moves focus into the dialog and closes on Escape', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: /Grok 4\.5 by/ }));
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('can be opened with the keyboard', async () => {
    const user = userEvent.setup();
    render(<App />);

    screen.getByRole('button', { name: /Claude Sonnet 5 by/ }).focus();
    await user.keyboard('{Enter}');

    expect(screen.getByRole('heading', { name: 'Claude Sonnet 5' })).toBeInTheDocument();
  });

  it('writes a shareable fragment and clears it on close', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: /DeepSeek V4 Flash by/ }));
    expect(window.location.hash).toBe('#deepseek--deepseek-v4-flash');

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(window.location.hash).toBe('');
  });

  it('opens the model named in the URL fragment on load', () => {
    setHash('anthropic--claude-opus-5');
    render(<App />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Claude Opus 5' })).toBeInTheDocument();
  });

  it('ignores a fragment that names no known model', () => {
    setHash('nope--gone');
    render(<App />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
