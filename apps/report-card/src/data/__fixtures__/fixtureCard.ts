import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseReportCard } from '../parseReportCard';
import type { ReportCard } from '../types';

/**
 * A representative report card used by tests instead of the real `LLM_REPORT_CARD.md`.
 *
 * The real document is prose the owner edits daily, so nothing about its content may be
 * asserted in a unit test. This fixture exercises the same grammar — several providers,
 * several models per provider, every canonical aspect, empty cells, `;`-separated cells,
 * semicolons nested in parentheses, escaped pipes, inline backticks, and a fenced authoring
 * template that must be ignored — and only ever changes when a test wants it to.
 */
export const FIXTURE_MARKDOWN: string = readFileSync(resolve(__dirname, './sample-report-card.md'), 'utf8');

/** The parsed {@link FIXTURE_MARKDOWN}, for tests that need data rather than markdown. */
export const fixtureCard: ReportCard = parseReportCard(FIXTURE_MARKDOWN);

/** Looks up a fixture model by name, failing loudly if the fixture ever loses it. */
export function fixtureModel(name: string) {
  const model = fixtureCard.models.find((entry) => entry.name === name);
  if (!model) throw new Error(`fixture has no model named "${name}"`);
  return model;
}
