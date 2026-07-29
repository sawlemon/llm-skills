import { useEffect, useRef } from 'react';
import { Check, Link2, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { useState } from 'react';
import type { ModelEntry } from '../data/types';

interface ModelDetailProps {
  model: ModelEntry;
  onClose: () => void;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])';

export function ModelDetail({ model, onClose }: ModelDetailProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    setCopied(false);
  }, [model.id]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const copyLink = async () => {
    const url = `${window.location.origin}${window.location.pathname}#${encodeURIComponent(model.id)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const rows = model.aspects;
  const hasNotes = model.prosCount + model.consCount > 0;

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        ref={dialogRef}
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        onKeyDown={onKeyDown}
      >
        <header className="sheet__header">
          <div>
            <p className="sheet__provider">{model.provider}</p>
            <h2 className="sheet__title" id="sheet-title">
              {model.name}
            </h2>
          </div>
          <div className="sheet__actions">
            <button type="button" className="icon-button" onClick={copyLink} aria-label="Copy link to this model">
              {copied ? <Check aria-hidden="true" size={18} /> : <Link2 aria-hidden="true" size={18} />}
            </button>
            <button ref={closeRef} type="button" className="icon-button" onClick={onClose} aria-label="Close">
              <X aria-hidden="true" size={18} />
            </button>
          </div>
        </header>

        <div className="sheet__body">
          {hasNotes ? (
            <table className="aspect-table">
              <caption className="visually-hidden">
                Observed strengths and weaknesses for {model.name}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Aspect</th>
                  <th scope="col">
                    <ThumbsUp aria-hidden="true" size={14} /> Pros
                  </th>
                  <th scope="col">
                    <ThumbsDown aria-hidden="true" size={14} /> Cons
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((entry) => (
                  <tr key={entry.aspect} className={entry.pros.length || entry.cons.length ? '' : 'is-empty'}>
                    <th scope="row">{entry.aspect}</th>
                    <td>
                      {entry.pros.length ? (
                        <ul className="notes notes--pro">
                          {entry.pros.map((note, index) => (
                            <li key={index}>{note}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="notes__none" aria-label="none recorded">
                          —
                        </span>
                      )}
                    </td>
                    <td>
                      {entry.cons.length ? (
                        <ul className="notes notes--con">
                          {entry.cons.map((note, index) => (
                            <li key={index}>{note}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="notes__none" aria-label="none recorded">
                          —
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="sheet__empty">No observations recorded for this model yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
