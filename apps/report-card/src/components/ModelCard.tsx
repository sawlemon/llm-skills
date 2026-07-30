import { ThumbsDown, ThumbsUp } from 'lucide-react';
import type { ModelEntry } from '../data/types';
import { renderNote } from '../lib/renderNote';

interface ModelCardProps {
  model: ModelEntry;
  highlightAspect: string | null;
  onSelect: (id: string) => void;
}

export function ModelCard({ model, highlightAspect, onSelect }: ModelCardProps) {
  const preview = highlightAspect
    ? model.aspects.find((entry) => entry.aspect === highlightAspect)
    : (model.aspects.find((entry) => entry.aspect === 'Other' && (entry.pros.length || entry.cons.length)) ??
      model.aspects.find((entry) => entry.pros.length || entry.cons.length));

  const previewNote = preview?.pros[0] ?? preview?.cons[0] ?? null;
  const previewTone = preview?.pros.length ? 'pro' : 'con';

  return (
    <button
      type="button"
      className="model-card"
      onClick={() => onSelect(model.id)}
      aria-label={`${model.name} by ${model.provider}, ${model.prosCount} strengths and ${model.consCount} weaknesses noted`}
    >
      <span className="model-card__provider">{model.provider}</span>
      <span className="model-card__name">{model.name}</span>
      {previewNote ? (
        <span className={`model-card__note model-card__note--${previewTone}`}>
          <span className="model-card__note-aspect">{preview?.aspect}</span>
          {renderNote(previewNote)}
        </span>
      ) : (
        <span className="model-card__note model-card__note--empty">No observations recorded yet.</span>
      )}
      <span className="model-card__tally">
        <span className="tally tally--pro">
          <ThumbsUp aria-hidden="true" size={14} strokeWidth={2} />
          {model.prosCount}
          <span className="visually-hidden"> strengths</span>
        </span>
        <span className="tally tally--con">
          <ThumbsDown aria-hidden="true" size={14} strokeWidth={2} />
          {model.consCount}
          <span className="visually-hidden"> weaknesses</span>
        </span>
      </span>
    </button>
  );
}
