import { useCallback, useEffect, useState } from 'react';

function readHash(): string | null {
  const raw = window.location.hash.replace(/^#/, '');
  return raw ? decodeURIComponent(raw) : null;
}

/**
 * Keeps the selected model id in sync with the URL fragment so links are shareable.
 *
 * Both directions go through the History API: opening a model pushes an entry
 * (so Back returns to where the user was), while closing replaces the current
 * entry (so dismissing a sheet never leaves a trailing entry that would reopen
 * it). Neither `pushState` nor `replaceState` fires `hashchange`, so state is
 * updated directly here; the listener only handles real hash navigation.
 */
export function useHashModel(): [string | null, (id: string | null) => void] {
  const [modelId, setModelId] = useState<string | null>(readHash);

  useEffect(() => {
    const onHashChange = () => setModelId(readHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const select = useCallback((id: string | null) => {
    const { pathname, search } = window.location;
    const base = `${pathname}${search}`;
    if (id) {
      window.history.pushState(null, '', `${base}#${encodeURIComponent(id)}`);
    } else {
      window.history.replaceState(null, '', base);
    }
    setModelId(id);
  }, []);

  return [modelId, select];
}
