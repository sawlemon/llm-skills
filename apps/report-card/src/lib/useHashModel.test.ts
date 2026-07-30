import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useHashModel } from './useHashModel';

/**
 * Puts the browser on a known entry before each case. `pushState` here (rather than
 * `replaceState`) guarantees the entry *behind* the one under test is a plain `/`, so the
 * Back-button cases below cannot be perturbed by fragments left over from earlier cases.
 */
beforeEach(() => window.history.pushState(null, '', '/'));
afterEach(() => window.history.replaceState(null, '', '/'));

/**
 * Presses Back and waits for the traversal to land. `history.back()` is asynchronous, so
 * without waiting for `popstate` (plus a macrotask for the `hashchange` that follows it) a
 * "nothing happened" assertion would pass before anything had a chance to happen.
 */
async function goBack() {
  const popped = new Promise<void>((resolve) => {
    window.addEventListener('popstate', () => resolve(), { once: true });
  });
  await act(async () => {
    window.history.back();
    await popped;
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe('useHashModel', () => {
  it('starts with no model when there is no fragment', () => {
    const { result } = renderHook(() => useHashModel());
    expect(result.current[0]).toBeNull();
  });

  it('reads and decodes the model id already in the fragment', () => {
    window.history.replaceState(null, '', '/#acme%20labs--x');
    const { result } = renderHook(() => useHashModel());
    expect(result.current[0]).toBe('acme labs--x');
  });

  it('opening a model writes an encoded fragment and adds a history entry', () => {
    const { result } = renderHook(() => useHashModel());
    const before = window.history.length;

    act(() => result.current[1]('acme labs--x'));

    expect(window.location.hash).toBe('#acme%20labs--x');
    expect(result.current[0]).toBe('acme labs--x');
    expect(window.history.length).toBe(before + 1);
  });

  it('closing clears the fragment without adding a history entry', () => {
    const { result } = renderHook(() => useHashModel());
    act(() => result.current[1]('acme-labs--x'));
    const afterOpen = window.history.length;

    act(() => result.current[1](null));

    expect(window.location.hash).toBe('');
    expect(result.current[0]).toBeNull();
    expect(window.history.length).toBe(afterOpen);
  });

  it('preserves the path and query when writing the fragment', () => {
    window.history.replaceState(null, '', '/llm-skills/?q=grok');
    const { result } = renderHook(() => useHashModel());

    act(() => result.current[1]('acme-labs--x'));
    expect(window.location.href).toContain('/llm-skills/?q=grok#acme-labs--x');

    act(() => result.current[1](null));
    expect(window.location.href).toContain('/llm-skills/?q=grok');
    expect(window.location.hash).toBe('');
  });

  it('follows real hash navigation', () => {
    const { result } = renderHook(() => useHashModel());

    act(() => {
      window.location.hash = '#acme-labs--y';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });

    expect(result.current[0]).toBe('acme-labs--y');
  });

  it('closes the model when Back is pressed after opening one', async () => {
    const { result } = renderHook(() => useHashModel());
    act(() => result.current[1]('acme-labs--x'));
    expect(result.current[0]).toBe('acme-labs--x');

    await goBack();

    await waitFor(() => expect(result.current[0]).toBeNull());
    expect(window.location.hash).toBe('');
  });

  it('does not reopen the model when Back is pressed after closing it', async () => {
    const { result } = renderHook(() => useHashModel());
    act(() => result.current[1]('acme-labs--x'));
    act(() => result.current[1](null));

    // The closing `replaceState` overwrote the fragment entry, so Back lands on the entry from
    // before the model was ever opened rather than on the model itself.
    await goBack();

    expect(window.location.hash).toBe('');
    expect(result.current[0]).toBeNull();
  });
});
