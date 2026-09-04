---
name: wait-what
description: Re-explain the last answer in simpler, shorter technical language when the user says they do not understand, asks "wait, what?", or asks for a simpler explanation. Use only after a direct comprehension signal.
---

# Wait, what?

Stop and re-pitch the last relevant point.

1. Lead with the direct answer in one or two plain sentences.
2. Use the user's words and the target project's vocabulary when that vocabulary is available. If no context file exists, use the conversation and inspected code.
3. Explain only the missing connection or assumption. Use a small example when it removes ambiguity.
4. End when the point is understandable. Do not repeat the entire conversation, add unrelated background, or turn the repair into a lecture.

Keep commands, code, quotations, URLs, citations, and structured data exact. This is a comprehension repair, not a rewriting pass. Use `unslop` separately for human-facing prose polish when appropriate.
