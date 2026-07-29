export interface AspectEntry {
  /** Aspect name exactly as written in the report card, e.g. "Tool use / agentic". */
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
  /** Every distinct aspect name seen, in first-seen order. */
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
