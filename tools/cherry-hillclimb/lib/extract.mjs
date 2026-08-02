// Reads the last N hours of an assistant's chat transcript directly out of
// Cherry Studio's IndexedDB (Dexie DB "CherryStudio", tables `topics` and
// `message_blocks`) via the live page's own indexedDB handle, so it always
// sees committed data and never touches the DB file on disk.

/**
 * @param {import('./cdp.mjs').CdpSession} session
 * @param {{id: string, topics: {id:string, name:string, updatedAt?:string, createdAt?:string}[]}} assistant
 * @param {number} hours lookback window
 */
export async function extractTranscript(session, assistant, hours) {
  const cutoffMs = Date.now() - hours * 3600 * 1000;
  const cutoffIso = new Date(cutoffMs).toISOString();

  // Only bother opening topics that were touched inside the window at all;
  // per-message filtering below is the source of truth for inclusion.
  const candidateTopicIds = assistant.topics
    .filter((t) => new Date(t.updatedAt || t.createdAt || 0).getTime() >= cutoffMs)
    .map((t) => t.id);

  if (candidateTopicIds.length === 0) {
    return [];
  }

  const expr = `
    (async () => {
      function idbGet(db, storeName, key) {
        return new Promise((resolve, reject) => {
          const tx = db.transaction(storeName, "readonly");
          const req = tx.objectStore(storeName).get(key);
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
        });
      }
      function idbGetMany(db, storeName, keys) {
        return Promise.all(keys.map((k) => idbGet(db, storeName, k)));
      }

      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open("CherryStudio");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });

      const topicIds = ${JSON.stringify(candidateTopicIds)};
      const cutoff = ${JSON.stringify(cutoffIso)};

      const topics = await idbGetMany(db, "topics", topicIds);

      const msgMeta = new Map();
      const blockIds = [];
      for (const topic of topics) {
        if (!topic || !Array.isArray(topic.messages)) continue;
        for (const m of topic.messages) {
          if (!m.createdAt || m.createdAt < cutoff) continue;
          msgMeta.set(m.id, {
            topicId: topic.id,
            topicName: topic.name,
            role: m.role,
            createdAt: m.createdAt,
            modelId: m.modelId || (m.model && m.model.id) || null,
            blocks: Array.isArray(m.blocks) ? m.blocks : [],
          });
          for (const bId of (m.blocks || [])) blockIds.push(bId);
        }
      }

      const blocks = await idbGetMany(db, "message_blocks", blockIds);
      const blockById = new Map();
      for (const b of blocks) if (b) blockById.set(b.id, b);

      const records = [];
      for (const [messageId, meta] of msgMeta) {
        let text = "";
        let hasThinking = false;
        let hasError = false;
        for (const bId of meta.blocks) {
          const b = blockById.get(bId);
          if (!b) continue;
          if (b.type === "main_text" && b.content) {
            text += (text ? "\\n" : "") + b.content;
          } else if (b.type === "thinking") {
            hasThinking = true;
          } else if (b.type === "error") {
            hasError = true;
          }
        }
        if (!text) continue;
        records.push({
          topicId: meta.topicId,
          topicName: meta.topicName,
          messageId,
          role: meta.role,
          createdAt: meta.createdAt,
          modelId: meta.modelId,
          hasThinking,
          hasError,
          text,
        });
      }

      db.close();
      records.sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1));
      return records;
    })()
  `;

  const records = await session.evaluate(expr);
  return records || [];
}
