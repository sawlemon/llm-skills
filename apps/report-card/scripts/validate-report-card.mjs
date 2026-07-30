/**
 * Validates the real `LLM_REPORT_CARD.md` against the parser the site is built with.
 *
 * This is deliberately NOT a unit test: the document is content the owner edits daily, so a
 * content change must only ever be able to fail *validation*, and only for a genuine schema
 * violation (bad table shape, unknown aspect, duplicate model, ...).
 *
 * Run with `npm run validate -w report-card`.
 *
 * The parser is TypeScript with extensionless imports, which Node cannot load on its own, and
 * `tsx` is not a dependency. Vite is (it builds the site), and its `runnerImport` runs a module
 * through Vite's own transform pipeline — so this needs no new dependency and no build step.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { runnerImport } from 'vite';

const REPORT_CARD_PATH = fileURLToPath(new URL('../../../LLM_REPORT_CARD.md', import.meta.url));
const PARSER_PATH = fileURLToPath(new URL('../src/data/parseReportCard.ts', import.meta.url));

/** ReportCardParseError crosses a module-runner boundary, so check the shape, not the identity. */
function isParseError(error) {
  return error instanceof Error && error.name === 'ReportCardParseError';
}

const { module: parser } = await runnerImport(PARSER_PATH, {
  configFile: false,
  logLevel: 'silent',
});

let card;
try {
  card = parser.parseReportCard(readFileSync(REPORT_CARD_PATH, 'utf8'));
} catch (error) {
  // ReportCardParseError already prefixes its message with `LLM_REPORT_CARD.md:<line>: `.
  console.error(isParseError(error) ? error.message : `LLM_REPORT_CARD.md: ${error}`);
  process.exitCode = 1;
  process.exit();
}

const pros = card.models.reduce((total, model) => total + model.prosCount, 0);
const cons = card.models.reduce((total, model) => total + model.consCount, 0);
const covered = new Set(card.models.flatMap((model) => model.coveredAspects));
const orderedCovered = card.aspects.filter((aspect) => covered.has(aspect));

console.log(`LLM_REPORT_CARD.md is valid — "${card.title}"`);
console.log(`  providers: ${card.providers.length} (${card.providers.map((p) => p.name).join(', ')})`);
console.log(`  models:    ${card.models.length}`);
console.log(`  harnesses: ${card.harnesses.length} (${card.harnesses.map((h) => h.name).join(', ')})`);
console.log(`  aspects:   ${orderedCovered.length} of ${card.aspects.length} with observations`);
console.log(`  notes:     ${pros} pros, ${cons} cons`);
