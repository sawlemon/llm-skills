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

/**
 * The aspect names an LLM harness table may use, in display order.
 *
 * Harnesses (Claude Code, ChatGPT desktop, Cherry Studio, ...) are the tools models run inside,
 * so they are judged on different things than the models themselves. They live under the reserved
 * `## LLM Harness` heading and use this set instead of {@link CANONICAL_ASPECTS}.
 */
export const HARNESS_ASPECTS = [
  'UI / UX',
  'Ease of use',
  'Customizability',
  'Flexibility',
  'Speed / responsiveness',
  'Resource consumption',
  'Model support',
  'Other',
] as const;

/** One of the {@link HARNESS_ASPECTS} names. */
export type HarnessAspect = (typeof HARNESS_ASPECTS)[number];

/** The exact top-level heading that switches a section from models to harnesses. */
export const HARNESS_SECTION_NAME = 'LLM Harness';

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
  /** Every distinct aspect name seen across models, in {@link CANONICAL_ASPECTS} order. */
  aspects: string[];
  /** Harness tools listed under the reserved "## LLM Harness" heading, in source order. */
  harnesses: ModelEntry[];
  /** Every distinct aspect name seen across harnesses, in {@link HARNESS_ASPECTS} order. */
  harnessAspects: string[];
}

export class ReportCardParseError extends Error {
  readonly line: number;

  constructor(message: string, line: number) {
    super(`LLM_REPORT_CARD.md:${line}: ${message}`);
    this.name = 'ReportCardParseError';
    this.line = line;
  }
}
