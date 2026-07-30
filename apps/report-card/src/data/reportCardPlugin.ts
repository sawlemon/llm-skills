import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';
import { parseReportCard } from './parseReportCard';

const VIRTUAL_ID = 'virtual:report-card';
const RESOLVED_ID = `\0${VIRTUAL_ID}`;

/** The report card lives at the repo root, four levels above `apps/report-card/src/data`. */
const DEFAULT_SOURCE_PATH = fileURLToPath(new URL('../../../../LLM_REPORT_CARD.md', import.meta.url));

/**
 * Parses `LLM_REPORT_CARD.md` at build time and exposes it as `virtual:report-card`.
 * A malformed report card fails the build with the offending line number.
 *
 * `sourcePath` may be absolute (recommended, since the Vite root is `apps/report-card`
 * while the report card lives at the repo root) or relative to the Vite root.
 */
export function reportCardPlugin(sourcePath = DEFAULT_SOURCE_PATH): Plugin {
  let absolutePath = '';

  return {
    name: 'llm-report-card',
    enforce: 'pre',
    configResolved(config) {
      absolutePath = resolve(config.root, sourcePath);
    },
    resolveId(id) {
      return id === VIRTUAL_ID ? RESOLVED_ID : null;
    },
    load(id) {
      if (id !== RESOLVED_ID) return null;
      this.addWatchFile(absolutePath);
      const markdown = readFileSync(absolutePath, 'utf8');
      const reportCard = parseReportCard(markdown);
      return `export default ${JSON.stringify(reportCard)};`;
    },
    handleHotUpdate({ file, server }) {
      if (file !== absolutePath) return;
      const virtualModule = server.moduleGraph.getModuleById(RESOLVED_ID);
      if (virtualModule) server.moduleGraph.invalidateModule(virtualModule);
      server.ws.send({ type: 'full-reload' });
    },
  };
}
