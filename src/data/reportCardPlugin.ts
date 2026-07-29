import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';
import { parseReportCard } from './parseReportCard';

const VIRTUAL_ID = 'virtual:report-card';
const RESOLVED_ID = `\0${VIRTUAL_ID}`;

/**
 * Parses `LLM_REPORT_CARD.md` at build time and exposes it as `virtual:report-card`.
 * A malformed report card fails the build with the offending line number.
 */
export function reportCardPlugin(sourcePath = 'LLM_REPORT_CARD.md'): Plugin {
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
