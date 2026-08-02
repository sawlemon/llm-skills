// Resolves a Cherry Studio assistant by name from the live Redux store and
// guards against the `defaultAssistant` footgun: Cherry Studio keeps a
// separate `assistants.defaultAssistant` object that also carries the
// literal id "default" but is NOT part of the `assistants.assistants` array
// and is never what a user-named assistant like "Personal" refers to, even
// though today Personal's own id also happens to be the string "default".
// We always select from the `assistants` array by name, never by id alone,
// and explicitly assert we did not pick up the sibling object.

class AssistantResolutionError extends Error {}

/**
 * @param {import('./cdp.mjs').CdpSession} session
 * @param {string} name exact assistant display name to match
 */
export async function resolveAssistant(session, name) {
  const expr = `
    (async () => {
      const state = window.store.getState();
      const slice = state.assistants;
      if (!slice) throw new Error("assistants slice missing from store");
      const matches = (slice.assistants || []).filter((a) => a.name === ${JSON.stringify(name)});
      return {
        matchCount: matches.length,
        matches: matches.map((a) => ({
          id: a.id,
          name: a.name,
          prompt: a.prompt || "",
          model: a.model || null,
          topics: (a.topics || []).map((t) => ({
            id: t.id,
            name: t.name,
            createdAt: t.createdAt,
            updatedAt: t.updatedAt,
          })),
        })),
        defaultAssistantId: slice.defaultAssistant ? slice.defaultAssistant.id : null,
        defaultAssistantPromptLen: slice.defaultAssistant ? (slice.defaultAssistant.prompt || "").length : 0,
      };
    })()
  `;

  const result = await session.evaluate(expr);
  if (!result) {
    throw new AssistantResolutionError('Could not read assistants slice from window.store');
  }
  if (result.matchCount === 0) {
    throw new AssistantResolutionError(`No assistant named ${JSON.stringify(name)} found`);
  }
  if (result.matchCount > 1) {
    throw new AssistantResolutionError(
      `${result.matchCount} assistants named ${JSON.stringify(name)} found; name must be unique`,
    );
  }

  const assistant = result.matches[0];

  // Guard: make sure we did not accidentally resolve the sibling
  // `defaultAssistant` object instead of the array element. They can share
  // an id (both "default" today) but are different objects; the array
  // element is authoritative for `assistants/updateAssistant` dispatches.
  if (assistant.id === result.defaultAssistantId && assistant.prompt.length === 0) {
    throw new AssistantResolutionError(
      'Resolved assistant looks like the sibling defaultAssistant placeholder (empty prompt), not a real named assistant',
    );
  }

  return assistant;
}

export { AssistantResolutionError };
