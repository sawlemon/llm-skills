import { useCallback, useEffect, useState } from 'react';

function readHash(): string | null {
  const raw = window.location.hash.replace(/^#/, '');
  return raw ? decodeURIComponent(raw) : null;
}

/** Keeps the selected model id in sync with the URL fragment so links are shareable. */
export function useHashModel(): [string | null, (id: string | null) => void] {
  const [modelId, setModelId] = useState<string | null>(readHash);

  useEffect(() => {
    const onHashChange = () => setModelId(readHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const select = useCallback((id: string | null) => {
    if (id) {
      window.location.hash = encodeURIComponent(id);
    } else {
      const { pathname, search } = window.location;
      window.history.pushState(null, '', `${pathname}${search}`);
    }
    setModelId(id);
  }, []);

  return [modelId, select];
}
