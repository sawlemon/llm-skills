# Fixture Report Card

Prose before the first provider heading is ignored by the parser.

## How to use

The fenced block below is the authoring template. The parser must skip it entirely, so nothing
inside it may show up as a provider, a model, or a note.

```
## Provider

### Model name (exact id if known)

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | template pro that must never be parsed | template con that must never be parsed |
| Other | | |
```

---

## Acme Labs

### Acme Prime 2

| Aspect                      | Pros                                                                     | Cons                                    |
| --------------------------- | ------------------------------------------------------------------------ | --------------------------------------- |
| Reasoning                   | plans multi-step tasks well; states its assumptions up front             | loses the thread past ten steps         |
| Coding                      | patches `parseReportCard.ts` without breaking callers                    |                                         |
| Instruction-following       |                                                                          | ignores explicit "no preamble" requests |
| Tool use / agentic          | picks the right tool first try (even when two tools overlap; no retries) |                                         |
| Context handling            |                                                                          |                                         |
| Speed / latency             | fast on short prompts                                                    | crawls once the context window is full  |
| Cost / efficiency           |                                                                          | token-hungry on long agent runs         |
| Refusals / safety behavior  |                                                                          |                                         |
| Formatting / output quality | renders `a \| b` inside a table cell correctly                           |                                         |
| Other                       | favourite for refactors                                                  | early impression only                   |

### Acme Mini

| Aspect                      | Pros | Cons |
| --------------------------- | ---- | ---- |
| Reasoning                   |      |      |
| Coding                      |      |      |
| Instruction-following       |      |      |
| Tool use / agentic          |      |      |
| Context handling            |      |      |
| Speed / latency             |      |      |
| Cost / efficiency           |      |      |
| Refusals / safety behavior  |      |      |
| Formatting / output quality |      |      |
| Other                       |      |      |

---

## Globex (Speech-to-Text / ASR)

### Globex Echo 0.6B

| Aspect                      | Pros                                   | Cons                                |
| --------------------------- | -------------------------------------- | ----------------------------------- |
| Context handling            | supports live streaming transcription  |                                     |
| Speed / latency             |                                        |                                     |
| Formatting / output quality | transcribes unfamiliar names correctly | drops the final word on short clips |
| Other                       | current voice-to-text model of choice  |                                     |

---

## LLM Harness

### Fixture Harness

| Aspect                 | Pros                              | Cons                          |
| ---------------------- | --------------------------------- | ----------------------------- |
| UI / UX                | clean, uncluttered layout         |                               |
| Ease of use            |                                   | steep learning curve at first |
| Customizability        | rich settings; scriptable         |                               |
| Flexibility            |                                   |                               |
| Speed / responsiveness | snappy on small projects          |                               |
| Resource consumption   |                                   | memory-hungry on long runs    |
| Model support          | works with every provider I tried |                               |
| Other                  | daily driver                      |                               |
