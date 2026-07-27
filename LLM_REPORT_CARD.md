# LLM Report Card

Per-model report card of observed strengths and weaknesses, organized by provider → model.

## How to use

For each model, keep a running list of observations under each aspect — short bullets, not journal entries. Prefix each bullet with `+` (good) or `-` (bad). Add new providers/models/aspects as needed.

```
## Provider

### Model name (exact id if known)

| Aspect | Notes |
|---|---|
| Reasoning | + concise multi-step reasoning on math proofs |
| Coding | - hallucinates nonexistent library functions |
| Instruction-following | |
| Tool use / agentic | |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | |
```

---

## Anthropic

### Claude Sonnet 5

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | + when the system prompt actually reaches the model, follows every instruction given and remembers instructions from earlier in the same initial prompt; - outside first-party tools (e.g. via Cherry Studio), doesn't reliably stick to an injected system prompt; not a model issue — Opus 5's investigation (see below) traced this to the CLI proxy stripping the custom system prompt and injecting its own, likely to avoid getting the account banned, so doesn't reflect on Sonnet 5 itself |
| Tool use / agentic | - doesn't use third-party built-in search tools (e.g. Cherry Studio's) well |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + astonishingly good, but only within Anthropic's own tools (Claude Code, Claude Desktop); Claude Code is fine, but dislike Claude Desktop's UI/UX; main downside is lack of flexibility to use the model well through third-party tools/apps |

### Claude Opus 4.6

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | + sticks to the system prompt and the user's input prompt very thoroughly — will follow through on what's given even if it's wrong, rather than second-guessing it; this forces the user to think harder about the problem and write a good prompt, which was liked as a challenge; + follows every instruction given and remembers instructions from earlier in the same initial prompt; + via the Antigravity subscription, correctly follows the custom Hindsight memory system prompt; unclear why the same system prompt doesn't work as well through the Claude Pro subscription |
| Tool use / agentic | + via the Antigravity CLI subscription, is able to invoke the web search tool; - via the Anthropic Claude Pro subscription, cannot use web search — seems to be a restriction Anthropic imposes on that plan/surface rather than a model limitation; + given a screenshot of a podcast list, extracted the list and correctly called Hindsight's retain to save it, without triggering an unnecessary recall first — showing the memory-gate logic in the custom prompt is being followed properly |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + always a favorite model; didn't like Opus 4.7 or 4.8 at their initial launch by comparison |

### Claude Opus 4.8

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | + methodical on Playwright script task — inferred idempotency requirement unprompted, and auto-implemented a diff-only extraction after recognizing repeated calls would otherwise mean rewriting the memories on a hindsight server |
| Instruction-following | + when the system prompt actually reaches the model, follows every instruction given and remembers instructions from earlier in the same initial prompt; - outside first-party tools (e.g. via Cherry Studio), doesn't reliably stick to an injected system prompt; unlike Opus 4.6, given the same prompt it thinks on its own and intelligently interprets what the user needs rather than following the prompt literally as given; not a model issue — see Opus 5's root-cause investigation below (CLI proxy strips the custom system prompt, likely to avoid getting the account banned) |
| Tool use / agentic | - doesn't use third-party built-in search tools (e.g. Cherry Studio's) well; + within Claude Code, self-verifies by running its own tests after implementing each feature rather than assuming correctness |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + astonishingly good, but only within Anthropic's own tools (Claude Code, Claude Desktop); Claude Code is fine, but dislike Claude Desktop's UI/UX; main downside is lack of flexibility to use the model well through third-party tools/apps |

### Claude Opus 5

| Aspect | Notes |
|---|---|
| Reasoning | + asked to diagnose why a custom system prompt wasn't going through when invoked from Cherry Studio via a CLI proxy API; without being given the proxy's source code, it researched online and correctly traced the root cause: the proxy strips the custom system prompt, sets a "Claude Code"-style header, and injects its own agent system prompt instead — correctly concluded Cherry Studio itself was not the problem; - noticed a lot of observations were missing from Hindsight and tried to investigate by looking at the logs, but did not find that a separate session's deletion of some memory observations was what caused the reduction; instead gave a wrong answer, claiming the deleted bookmarks could have been extracted into multiple observations and that this was what led to the huge amount of observations missing — completely false; need to be careful when using Opus 5 for factual information, since without already knowing the real answer this would have been trusted; - reasoning sometimes weak, misses facts, goes with an assumption instead — assumption sometimes wrong |
| Coding | |
| Instruction-following | + follows every instruction given and remembers instructions from earlier in the same initial prompt; - like the other Claude models, outside first-party tools doesn't reliably receive a custom injected system prompt; not a model issue — its own root-cause investigation traced this to the CLI proxy stripping the custom system prompt and injecting its own, likely to avoid getting the account banned |
| Tool use / agentic | + when explicitly told (on a later turn) to use Hindsight MCP, performed the recall correctly and laid results out concisely — not over- or under-explained, just the right amount; + spawned two agents to investigate the CLI proxy issue, both completed their tasks and contributed to correctly identifying the root cause and suggesting fixes; + experimenting with using it to manage Hindsight MCP server memory banks; on a project to extract Raindrop bookmarks and upload them to Hindsight, was thorough — shortened URLs got expanded before being stored; + when asked to delete some memories, made sure no other collateral damage had happened; + in a separate session, some other memory references were deleted, and the first session recognized this and checked the logs to figure out why there was a sudden drop in memory extractions |
| Context handling | - heard on Twitter (not personally verified): Claude Desktop defaults to a 200k context window out of the box, and users have to manually switch the model setting to get the 1M context window; own take is that the 200k default is probably fine for quick tasks on Desktop, so it may not matter much in practice |
| Speed / latency | |
| Cost / efficiency | - the CLI proxy investigation (with two spawned agents) consumed roughly 30% of usage for a single question — token-hungry, though notably less so than Fable 5 was |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | initial impression is good; still early, needs more testing before a firm verdict; + impressive investigative/root-cause diagnosis capability; + behaves intelligently overall; - gave wrong answers twice, but corrected itself in the subsequent chat, admitting the earlier response was wrong — nothing critical this time, but this kind of after-the-fact self-correction could be destructive if it happened at a more crucial moment; - after a couple hours of testing, makes noticeably more mistakes than Opus 4.8 did, catching and self-correcting after the fact rather than getting it right the first time; would much rather it not make the mistake in the first place — need to stay alert for mistakes earlier in its process so they can be caught/prevented at the start rather than after the fact |

---

## OpenAI

### GPT 5.5 Terra

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | - the ChatGPT desktop app's built-in model harness behaves weirdly, doesn't understand what's being asked; + works as expected in Cherry Studio with custom system prompts |
| Tool use / agentic | |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + quite decent overall; still needs more testing |

### GPT 5.6 Sol

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | |
| Tool use / agentic | |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | - very token-hungry, unlike older GPT models; on the ChatGPT Go plan it burns through the entire monthly limit in a matter of days; OpenAI models generally pricier than others on OpenRouter |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | haven't personally tested much yet — Go plan rate limits cut testing short; heard good things about it on Twitter/elsewhere but no first-hand verdict; plan to revisit once on a Pro subscription |

---

## Google

### Gemini 3.1 Flash

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | |
| Tool use / agentic | - used as Cherry Studio's search assistant: initially fast with good results, but hallucinated on a Taskmaster question (wrong contestant details) — switched back to DeepSeek V4 Flash as default search assistant |
| Context handling | |
| Speed / latency | + extremely fast |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | - used for auto-naming Cherry Studio chat titles based on conversation content; names them wrongly, in all caps, in a weird format — suspect something wrong on the backend |
| Other | - overall utter trash for chat-naming and unreliable as search assistant; not used much |

### Gemini 3.6 Flash

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | |
| Tool use / agentic | tried on a browser task extracting Twitter bookmarks — made 4 tool calls then got throttled/hit API rate limits, so testing was cut short and inconclusive |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | now using it for Cherry Studio chat-naming (replacing 3.1 Flash); verdict on chat-naming quality still pending, to be updated later |

---

## DeepSeek

### DeepSeek V4 Flash

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | + adheres to system prompt very well, consistently, on every single turn |
| Tool use / agentic | + excellent tool calling — reliably picks the right tools |
| Context handling | |
| Speed / latency | + one of the fastest models used so far |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + favorite quick model currently; despite Artificial Analysis Index reporting a high hallucination rate, doesn't hallucinate much in practice — sticks to the task when asked to do things; - no vision support, doesn't natively accept image inputs — wish DeepSeek released a model that does |

---

## Zhipu AI

### GLM 5.2

| Aspect | Notes |
|---|---|
| Reasoning | + does research very well; when it doesn't know something, it admits it rather than making it up; - asked about a CrowdStrike Falcon repo ("xdr_indicators"), did thorough research and correctly said there's no publicly known info rather than guessing, but missed that it's actually a CrowdStrike Falcon LogScale repo where XDR indicators are stored |
| Coding | |
| Instruction-following | |
| Tool use / agentic | |
| Context handling | |
| Speed / latency | |
| Cost / efficiency | - high-thinking mode is expensive; a single research-heavy question cost close to $3 — think carefully about credit usage before invoking the high-thinking tier |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + favorite for writing system prompts — system prompts written by GLM 5.2 transfer well and are stuck to across other models, whereas system prompts written by Sonnet 5, Opus 4.8, and ChatGPT 5.5 Terra did not generalize as well across models |

---

## xAI

### Grok 4.5

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | + sticks to what's requested; behaved well on prompted tasks |
| Tool use / agentic | + asked how the week went, it queried Hindsight MCP and synthesized a summary across the whole week on its own — surfaced both the bad things that happened and unprompted highlighted the positives too; asked again scoped to just the past two days but it still returned a summary of the entire week; + on normal day-to-day interaction, commits to the Hindsight memory bank before even giving a response, and pulls in the proper context (e.g. knows about the user's ADHD and other relevant personal context) |
| Context handling | - 500k context window per spec sheet, smaller than other models now at up to 1M — but plenty for light usage, not a real downside in practice |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | |
| Other | + impressive overall, looks great on benchmarks, worth checking out more; tested via the xAI platform, ran out of trial quota before testing further; + memory-synthesis output over Hindsight MCP was very impressive, would love using this model; + great for day-to-day usage, really understands the user well |

---

## NVIDIA (Speech-to-Text / ASR)

### Parakeet V3

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | |
| Tool use / agentic | |
| Context handling | processes the full voice input and returns the transcription as a whole, rather than streaming live |
| Speed / latency | + very fast |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | + reliably accurate |
| Other | previous go-to for voice-to-text before switching to Parakeet Unified for live/streaming transcription |

### Parakeet Unified ENG 0.6B

| Aspect | Notes |
|---|---|
| Reasoning | |
| Coding | |
| Instruction-following | |
| Tool use / agentic | |
| Context handling | + supports live/streaming transcription (vs. Parakeet V3's whole-input-then-output approach) |
| Speed / latency | |
| Cost / efficiency | |
| Refusals / safety behavior | |
| Formatting / output quality | + very accurate on live transcription — correctly recognized colleagues' Tamil names spoken mid-sentence |
| Other | + current voice-to-text model of choice; impressed with its live performance |
