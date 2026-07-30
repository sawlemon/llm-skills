import {
  CANONICAL_ASPECTS,
  ReportCardParseError,
  type AspectEntry,
  type ModelEntry,
  type ProviderEntry,
  type ReportCard,
} from './types';

const EXPECTED_COLUMNS = ['aspect', 'pros', 'cons'];

const CANONICAL_ASPECT_SET: ReadonlySet<string> = new Set(CANONICAL_ASPECTS);

/** Canonical aspects keyed by their loose form, for suggesting a fix on a near miss. */
const ASPECTS_BY_LOOSE_KEY: ReadonlyMap<string, string> = new Map(
  CANONICAL_ASPECTS.map((aspect) => [looseAspectKey(aspect), aspect]),
);

/** Folds case and drops all whitespace, so "Tool use/agentic" keys the same as "Tool use / agentic". */
function looseAspectKey(aspect: string): string {
  return aspect.toLowerCase().replace(/\s+/g, '');
}

interface SourceLine {
  text: string;
  /** 1-based line number in the original document. */
  number: number;
}

/** Removes fenced code blocks (the authoring template) while preserving line numbers. */
function stripFencedBlocks(markdown: string): SourceLine[] {
  const lines: SourceLine[] = [];
  let fence: string | null = null;

  markdown.split(/\r?\n/).forEach((text, index) => {
    const fenceMatch = /^\s*(`{3,}|~{3,})/.exec(text);
    if (fence === null && fenceMatch) {
      fence = fenceMatch[1][0];
      return;
    }
    if (fence !== null) {
      if (fenceMatch && fenceMatch[1][0] === fence) fence = null;
      return;
    }
    lines.push({ text, number: index + 1 });
  });

  return lines;
}

export function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'section';
}

/** Splits a table row into its cells, honouring escaped pipes. */
function splitRow(row: string): string[] {
  const cells: string[] = [];
  let current = '';

  for (let i = 0; i < row.length; i += 1) {
    const char = row[i];
    if (char === '\\' && row[i + 1] === '|') {
      current += '|';
      i += 1;
    } else if (char === '|') {
      cells.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  cells.push(current);

  // A leading and trailing pipe produce empty edge cells; drop them.
  if (cells.length && cells[0].trim() === '') cells.shift();
  if (cells.length && cells[cells.length - 1].trim() === '') cells.pop();

  return cells.map((cell) => cell.trim());
}

function isDelimiterRow(cells: string[]): boolean {
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

/** Splits a note cell into separate bullets on top-level semicolons. */
export function splitNotes(cell: string): string[] {
  const notes: string[] = [];
  let current = '';
  let depth = 0;

  for (const char of cell) {
    if (char === '(') depth += 1;
    else if (char === ')') depth = Math.max(0, depth - 1);

    if (char === ';' && depth === 0) {
      notes.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  notes.push(current);

  return notes.map((note) => note.trim()).filter((note) => note.length > 0);
}

/**
 * Builds the error for an aspect name that is not in `CANONICAL_ASPECTS`, pointing at the
 * closest canonical name when the difference is only case or whitespace.
 */
function unknownAspectError(aspect: string, modelName: string, line: number): ReportCardParseError {
  const suggestion = ASPECTS_BY_LOOSE_KEY.get(looseAspectKey(aspect));
  const fix = suggestion
    ? `did you mean "${suggestion}"?`
    : `expected one of [${CANONICAL_ASPECTS.join(', ')}]`;
  return new ReportCardParseError(`model "${modelName}" has unknown aspect "${aspect}"; ${fix}`, line);
}

export function parseReportCard(markdown: string): ReportCard {
  const lines = stripFencedBlocks(markdown);

  let title = 'LLM Report Card';
  const providers: ProviderEntry[] = [];
  const models: ModelEntry[] = [];
  const seenAspects = new Set<string>();
  const seenModelIds = new Set<string>();

  let provider: ProviderEntry | null = null;
  let model: ModelEntry | null = null;
  let modelLine = 0;
  let inTable = false;

  const finishModel = () => {
    if (model && model.aspects.length === 0) {
      throw new ReportCardParseError(
        `model "${model.name}" has no aspect table; expected a "| Aspect | Pros | Cons |" table`,
        modelLine,
      );
    }
    model = null;
    inTable = false;
  };

  for (const { text, number } of lines) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(text);

    if (heading) {
      const level = heading[1].length;
      const name = heading[2].trim();

      if (!name) throw new ReportCardParseError('heading has no text', number);

      if (level === 1) {
        finishModel();
        provider = null;
        title = name;
      } else if (level === 2) {
        finishModel();
        provider = { id: slugify(name), name, models: [] };
      } else if (level === 3) {
        finishModel();
        if (!provider) {
          throw new ReportCardParseError(
            `model "${name}" appears before any provider heading; add a "## Provider" heading above it`,
            number,
          );
        }
        const id = `${provider.id}--${slugify(name)}`;
        if (seenModelIds.has(id)) {
          throw new ReportCardParseError(
            `duplicate model "${name}" under provider "${provider.name}"`,
            number,
          );
        }
        seenModelIds.add(id);
        model = {
          id,
          name,
          provider: provider.name,
          providerId: provider.id,
          aspects: [],
          coveredAspects: [],
          prosCount: 0,
          consCount: 0,
        };
        modelLine = number;
        if (!providers.includes(provider)) providers.push(provider);
        provider.models.push(model);
        models.push(model);
      }
      continue;
    }

    if (!text.trim().startsWith('|')) {
      inTable = false;
      continue;
    }

    const cells = splitRow(text.trim());

    if (!model) {
      throw new ReportCardParseError(
        'table row found outside of a model section; add a "### Model name" heading above it',
        number,
      );
    }

    if (!inTable) {
      const header = cells.map((cell) => cell.toLowerCase());
      if (header.join('|') !== EXPECTED_COLUMNS.join('|')) {
        throw new ReportCardParseError(
          `model "${model.name}" has table columns [${cells.join(', ')}]; expected [Aspect, Pros, Cons]`,
          number,
        );
      }
      inTable = true;
      continue;
    }

    if (isDelimiterRow(cells)) continue;

    if (cells.length !== EXPECTED_COLUMNS.length) {
      throw new ReportCardParseError(
        `model "${model.name}" has a row with ${cells.length} column(s); expected 3 (Aspect | Pros | Cons)`,
        number,
      );
    }

    const [aspect, prosCell, consCell] = cells;
    if (!aspect) {
      throw new ReportCardParseError(`model "${model.name}" has a row with an empty Aspect`, number);
    }
    if (!CANONICAL_ASPECT_SET.has(aspect)) {
      throw unknownAspectError(aspect, model.name, number);
    }

    const entry: AspectEntry = {
      aspect,
      pros: splitNotes(prosCell),
      cons: splitNotes(consCell),
    };

    model.aspects.push(entry);
    model.prosCount += entry.pros.length;
    model.consCount += entry.cons.length;
    if (entry.pros.length || entry.cons.length) model.coveredAspects.push(aspect);
    seenAspects.add(aspect);
  }

  finishModel();

  if (models.length === 0) {
    throw new ReportCardParseError(
      'no models found; expected at least one "## Provider" / "### Model name" pair',
      1,
    );
  }

  // Present aspects in canonical order regardless of authoring order, keeping only those used.
  const aspects = CANONICAL_ASPECTS.filter((aspect) => seenAspects.has(aspect));

  return { title, providers, models, aspects };
}
