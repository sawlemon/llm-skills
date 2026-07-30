/**
 * The only aspect names a model table may use, in the order the site presents them.
 *
 * The parser rejects anything else, so a typo cannot silently mint a new aspect (and a new
 * filter facet). Adding a genuinely new aspect means adding it here first, in its intended
 * display position.
 */
export const CANONICAL_ASPECTS = [
  'Reasoning',
  'Coding',
  'Instruction-following',
  'Tool use / agentic',
  'Context handling',
  'Speed / latency',
  'Cost / efficiency',
  'Refusals / safety behavior',
  'Formatting / output quality',
  'Other',
] as const;

/** One of the {@link CANONICAL_ASPECTS} names. */
export type CanonicalAspect = (typeof CANONICAL_ASPECTS)[number];

export interface AspectEntry {
  /** Aspect name, always one of {@link CANONICAL_ASPECTS}, e.g. "Tool use / agentic". */
  aspect: string;
  /** Individual strengths noted for this aspect. Empty when nothing was recorded. */
  pros: string[];
  /** Individual weaknesses noted for this aspect. Empty when nothing was recorded. */
  cons: string[];
}

export interface ModelEntry {
  /** URL-safe identifier, unique across the report card. */
  id: string;
  /** Model heading text, e.g. "Claude Opus 5". */
  name: string;
  /** Provider heading text, e.g. "Anthropic". */
  provider: string;
  /** URL-safe provider identifier. */
  providerId: string;
  /** Every aspect row of the model's table, in source order. */
  aspects: AspectEntry[];
  /** Aspect names that recorded at least one pro or con. */
  coveredAspects: string[];
  prosCount: number;
  consCount: number;
}

export interface ProviderEntry {
  id: string;
  name: string;
  models: ModelEntry[];
}

export interface ReportCard {
  /** Report card document title (the level-1 heading). */
  title: string;
  providers: ProviderEntry[];
  /** All models, flattened in source order. */
  models: ModelEntry[];
  /** Every distinct aspect name seen, in {@link CANONICAL_ASPECTS} order. */
  aspects: string[];
}

export class ReportCardParseError extends Error {
  readonly line: number;

  constructor(message: string, line: number) {
    super(`LLM_REPORT_CARD.md:${line}: ${message}`);
    this.name = 'ReportCardParseError';
    this.line = line;
  }
}
