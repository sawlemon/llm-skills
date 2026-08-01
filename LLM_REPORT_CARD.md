# LLM Report Card

Per-model report card of observed strengths and weaknesses, organized by provider → model.

## How to use

For each model, keep a running list of observations under each aspect — short bullets, not journal entries. Put strengths in `Pros` and weaknesses in `Cons`; do not mix them. Add new providers/models/aspects as needed.

```
## Provider

### Model name (exact id if known)

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | concise multi-step reasoning on math proofs | |
| Coding | | hallucinates nonexistent library functions |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | | |
```

---

## Anthropic

### Claude Sonnet 5

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | built LLM scorecard app using Apple Design Skill; every aspect of the resulting website's output was impressive — decent model for web design/front-end work on small coding tasks | |
| Instruction-following | when the system prompt actually reaches the model, follows every instruction given and remembers instructions from earlier in the same initial prompt | outside first-party tools (e.g. via Cherry Studio), doesn't reliably stick to an injected system prompt; not a model issue — Opus 5's investigation (see below) traced this to the CLI proxy stripping the custom system prompt and injecting its own, likely to avoid getting the account banned, so doesn't reflect on Sonnet 5 itself |
| Tool use / agentic | on medium settings, behaves quite agentic and completes tasks very quickly | did not commit and push when explicitly instructed to — asked for confirmation instead of just doing it; doesn't use third-party built-in search tools (e.g. Cherry Studio's) well |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | limited verbosity; doesn't give a lot of unnecessary/rubbish feedback | |
| Other | astonishingly good within Anthropic's own tools (Claude Code, Claude Desktop) | dislike Claude Desktop's UI/UX; lack of flexibility to use the model well through third-party tools/apps |

### Claude Opus 4.6

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | sticks to system and user prompts thoroughly, including when they are wrong; follows every instruction and remembers earlier instructions in same initial prompt; via Antigravity subscription, correctly follows custom Hindsight memory system prompt | unclear why same system prompt does not work as well through Claude Pro subscription |
| Tool use / agentic | via Antigravity CLI subscription, can invoke web search; given screenshot of podcast list, extracted list and correctly called Hindsight's retain without unnecessary recall | via Anthropic Claude Pro subscription, cannot use web search; seems plan/surface restriction rather than model limitation |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | always a favorite model | did not like Opus 4.7 or 4.8 at their initial launch by comparison |

### Claude Opus 4.8

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | methodical on Playwright script task; inferred idempotency unprompted and auto-implemented diff-only extraction to avoid rewriting Hindsight memories on repeated calls | |
| Instruction-following | when system prompt reaches model, follows every instruction and remembers earlier instructions in same initial prompt; intelligently interprets needs rather than following prompts literally | outside first-party tools (e.g. via Cherry Studio), doesn't reliably stick to injected system prompt; not a model issue — CLI proxy strips custom prompt and injects its own |
| Tool use / agentic | within Claude Code, self-verifies by running tests after implementing each feature | doesn't use third-party built-in search tools (e.g. Cherry Studio's) well |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | given the same documentation prompt as Opus 5 on a similar project via Claude Code (non-desktop), output markdown was noticeably less impressive and included no visual/diagram representation |
| Other | astonishingly good within Anthropic's own tools (Claude Code, Claude Desktop) | dislike Claude Desktop's UI/UX; lack of flexibility to use the model well through third-party tools/apps |

### Claude Opus 5

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | researched CLI proxy issue without source code and correctly traced it to proxy stripping custom prompt, setting Claude Code-style header, and injecting its own agent prompt; correctly concluded Cherry Studio was not problem; researched a GitHub Actions/PR sign-in issue and suggested logout/login even though the user was already signed in, which did fix it | failed to identify separate session's memory deletion as cause of missing Hindsight observations; instead gave false explanation; reasoning sometimes misses facts and relies on wrong assumptions |
| Coding | same OpenCode variant-selection debug task that MiMo 2.5 failed: solved it, though tried many approaches that did not work and were out of scope before landing the fix; debugging a cliproxyapi message-ID bug, cloned the cliproxyapi repo and independently replicated the bug from scratch to confirm root cause before fixing it — impressive but far more thorough than needed; claims the fix worked, plausible but not yet independently verified | |
| Instruction-following | follows every instruction and remembers earlier instructions in same initial prompt | outside first-party tools, does not reliably receive injected custom prompt; proxy strips it and injects its own system prompt |
| Tool use / agentic | performed requested Hindsight recall correctly and concisely; spawned two agents that identified CLI proxy root cause; thorough Hindsight memory management, including URL expansion and collateral-damage checks; independently found and surfaced separate bug for future conversation | even in auto mode, sometimes asks user to run shell commands or confirm continuation instead of executing; may need `/goal` more often |
| Context handling | | Claude Desktop reportedly defaults to 200k context; users must manually select 1M setting (not personally verified) |
| Speed / latency | | very slow to respond, noticeably slower than GLM 5.2 |
| Cost / efficiency | | CLI proxy investigation with two agents consumed roughly 30% of usage for one question; token-hungry, though less so than Fable 5; close to $90 worth of tokens spent on a documentation task via Claude Code desktop app; on a cliproxyapi message-ID bug, went on a wild-chase route of cloning and replicating the target repo's bug independently rather than a more economical fix, burning a lot of tokens for a task that wasn't explicitly scoped that way — not asked to be economical, so not a strict fault, but a less thorough approach would have been preferred |
| Refusals / safety behavior | | |
| Formatting / output quality | markdown documentation output via Claude Code desktop app was spot-on, well-formatted, and unprompted included a visual diagram representation | often emits multiple long paragraphs requiring reading and filtering instead of concise task-focused output |
| Other | impressive investigative/root-cause diagnosis; self-admits mistakes and addresses them later — without that self-admission there'd be no way to know it erred in the first place; on same documentation prompt/project, output via Claude Code desktop app was clearly better than Opus 4.8 via Claude Code, suggesting the desktop app may be stronger for documentation tasks | overall consensus (past early-impression phase): not that good; gave two wrong answers then corrected itself later; makes noticeably more mistakes than Opus 4.8 and self-corrects after rather than getting it right first time; Twitter discussion also includes substantial user dissatisfaction despite strong benchmark scores, with reports that it makes frequent mistakes and takes autonomous actions users did not request; on the custom ChatGPT-app provider integration task, claimed completion after using ~20% of a 5-hour session, but the ChatGPT app had no custom models listed — it fabricated success rather than admitting failure (same task DeepSeek V4 Flash also failed) |

---

## OpenAI

### GPT 5.6 Tera

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | on high reasoning effort, planned the LLM skills site build solidly and came up with the idea of filtering down per provider — a decent addition | responses are noticeably worse in the ChatGPT desktop app than when using the same OpenAI models through OpenCode or Claude Code |
| Coding | successfully refactored LLM Report Card template from one mixed `Notes` column into separate `Pros` and `Cons` columns after Opus 5's earlier template was unsatisfactory | when asked to debug and fix Hindsight MCP's re-rank model using the OpenRouter model provider, changed Docker image from `slim` to regular version and used FlashRank as model provider instead of investigating the reported issue |
| Instruction-following | works as expected in Cherry Studio with custom system prompts | did not preserve requested OpenRouter provider; completely switched model/provider approach without asking for confirmation |
| Tool use / agentic | with OpenCode, creates and works through a visible three-step todo list; workflow makes active model and todos clear | made consequential changes based on its own assumptions and executed them without user confirmation; behavior resembled Gemini 3.6 Flash High; the ChatGPT app harness produces weaker results than OpenCode or Claude Code, despite the underlying OpenAI model being capable |
| Context handling | the PET screen-snapshot concept makes it easy to send visual context | |
| Speed / latency | extremely fast for quick, small tasks | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | pairing GPT 5.6 Tera with OpenCode seems like a strong workflow: model selection and created todos remain visible; ChatGPT desktop app has excellent UI/UX, and the PET screen-snapshot animation is especially polished | still needs more testing |

### GPT 5.6 Sol

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | very token-hungry; ChatGPT Go monthly limit depleted in days; OpenAI models generally pricier than others on OpenRouter |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | heard good things on Twitter/elsewhere | little first-hand testing; Go plan rate limits cut testing short; no verdict until revisiting on Pro subscription |

---

## Google

### Gemini 3.1 Flash

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | initially fast with good results as Cherry Studio search assistant | hallucinated Taskmaster contestant details; switched back to DeepSeek V4 Flash |
| Context handling | | |
| Speed / latency | extremely fast | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | Cherry Studio chat titles wrong, all caps, weird format; suspect backend issue |
| Other | | unreliable as search assistant and poor for chat-naming; not used much |

### Gemini Flash 3.6

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | summarized scientific document in simple everyday English as requested | |
| Tool use / agentic | goes above and beyond to find and fix issues autonomously (e.g. fixed hindsight MCP server re-rank error by changing recall model provider, and replaced missing GPTOSS 120B model with GPT OSS20B after checking logs during Docker image update); frequently executes multiple tool calls and updates on its own | browser bookmark-extraction task stopped after four tool calls due to throttling/API rate limits; testing inconclusive; makes many autonomous decisions without asking the user for input or confirmation |
| Context handling | | |
| Speed / latency | insanely fast; possibly faster than DeepSeek V4 Flash; very quick to find out issues | Gemini endpoint unreliable at times; hard to confirm speed advantage due to provider variance |
| Cost / efficiency | high request volume on OpenRouter across all providers | comparison with DeepSeek V4 Flash not fair — DeepSeek V4 Flash inferred via OpenRouter depends on provider token output |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | now used for Cherry Studio chat-naming, replacing 3.1 Flash; very impressive overall; await more updates after further testing | chat-naming verdict pending |

---

## DeepSeek

### DeepSeek V4 Flash

| Aspect | Pros | Cons |
|---|---|---|---|
| Reasoning | | on custom ChatGPT-app provider integration (planned with Opus 4.8, executed here) made many mistakes and left a few old references behind; that said, Opus 5 failed the same task too — likely a hard/unsolvable task rather than a model-specific failure |
| Coding | | same integration task: did not perform well, made lots of mistakes, left old references |
| Instruction-following | adheres to system prompt consistently on every turn; gets things done in a neat way when prompted directly | needs a direct prompt; doesn't reliably infer implicit intent on its own; initially said it had not read the raindrop_tract session, then gave the right answer after a more specific follow-up |
| Tool use / agentic | excellent tool calling; reliably picks right tools; with CC Switch routing Codex desktop messages to it, handled the full edit-and-push workflow for this report card | integration reached a point where providers could be listed but nothing was usable, so the whole thing was reverted; asked to run the Raindrop extraction Python file, ran it without checking the existing JSON tracker and re-extracted all bookmarks |
| Context handling | | |
| Speed / latency | one of fastest models used so far; finished the whole integration task within 15 minutes | |
| Cost / efficiency | ran quite a few tasks on medium settings for about $0.18, mind-blowingly cheap; OpenRouter usage dashboard showed $0.12 spend for 182 requests / 8.57M tokens in 3 hours, a blended $0.01/1M tokens with 94.1% cache hit rate | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | favorite quick model; despite reported high hallucination rate, does not hallucinate much in practice and sticks to task; handled the Hill Climb scheduled task on medium settings by getting the transcript accurately and updating it | no vision support or native image inputs; initial criticism of complex-task performance softened — Opus 5 also failed the same custom ChatGPT-app integration, so verdict still open on whether any model can do it yet |

---

## Zhipu AI

### GLM 5.2

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | does research very well; admits when it does not know rather than making information up | missed that CrowdStrike Falcon repo `xdr_indicators` is a Falcon LogScale repo where XDR indicators are stored |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | | |
| Speed / latency | very fast, especially compared with Opus 5 | |
| Cost / efficiency | | high-thinking mode expensive; one research-heavy question cost close to $3 |
| Refusals / safety behavior | | |
| Formatting / output quality | accurate and concise in practice, with little unneeded text | |
| Other | favorite for writing system prompts; prompts transfer well and stick across other models | |

---

## xAI

### Grok 4.5

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | sticks to requests; behaved well on prompted tasks; only model observed in OpenCode that actually followed the Claude.md skill — loaded Hindsight MCP at the initial request, saved given info, and committed it to Hindsight at end of request completion | |
| Tool use / agentic | autonomously queried Hindsight MCP and synthesized weekly summary, including positives; commits to Hindsight memory bank before responding and pulls relevant user context; cleverly inspected git log to match local commit-message patterns before committing | when re-scoped from week to two days, still returned full-week summary |
| Context handling | | 500k context window is smaller than competitors' 1M, though sufficient for light usage |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | impressive overall and benchmarks look strong; Hindsight memory synthesis impressive; great for day-to-day use and understands user well; continues to impress on real agentic OpenCode workflows | xAI trial quota ended before further testing |

---

## Xiaomi

### MiMo 2.5

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | on OpenCode variant-selection availability debug: gave false ideas and an incredibly dull solution that would have required far more effort than needed |
| Coding | | failed same OpenCode variant-selection debug task that Opus 5 solved; proposed heavyweight path instead of the simple fix |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | | weak first impression on real debugging vs Opus 5 on identical task |

---

## NVIDIA (Speech-to-Text / ASR)

### Parakeet V3

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | | processes whole voice input before returning transcription instead of streaming live |
| Speed / latency | very fast | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | reliably accurate | |
| Other | previous go-to voice-to-text model | superseded by Parakeet Unified for live transcription |

### Parakeet Unified ENG 0.6B

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | supports live/streaming transcription | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | very accurate live transcription; correctly recognized colleagues' Tamil names mid-sentence | recognition accuracy degrading lately; misses the word "Deepseek" specifically until added as a custom word in Handy app, after which it works |
| Other | current voice-to-text model of choice; live performance impressive | overall experience degrading vs. earlier — needed custom vocabulary (Handy app) to fix specific word misses |

### Parakeet TDT V2

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | not a streaming model, so no live transcript view | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | does not force-capitalize words that should be acronyms (e.g. "LLM" stays lowercase as typed), feels more like natural human typing | |
| Other | testing well so far; disadvantage is lack of streaming/live transcription | |

### Nemotron Streaming 3.5

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | | |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | supports live/streaming transcription — a nice-to-have not realized was needed until offered | |
| Speed / latency | very fast | |
| Cost / efficiency | ~716 MB on disk, roughly the same size as Parakeet Unified EN 0.6B (~697 MB) and Parakeet TDT 0.6B v2 (~695 MB) | |
| Refusals / safety behavior | | |
| Formatting / output quality | picks up words reliably overall | bad at picking up single words, especially Tamil names |
| Other | works fine so far | mistook English speech for Hindi and transcribed the whole thing in Hindi instead |

---

## Unknown Provider

### Big Pickle

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | | |
| Coding | good at coding tasks | |
| Instruction-following | | |
| Tool use / agentic | good at agentic tasks; successfully SSHed into remote server and made config changes | |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | strong fallback when Anthropic or OpenAI subscription limits are reached | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | behaves well for simple tasks | model provider is anonymous; provider unknown, cannot categorize under a provider section yet; untested on long-running or highly complex tasks |

---

## LLM Harness

Harnesses are the apps/CLIs that models run inside. They're judged on different things than the models themselves, so these tables use harness-specific aspects: UI / UX, Ease of use, Customizability, Flexibility, Speed / responsiveness, Resource consumption, Model support, Other.

### Claude Code

| Aspect | Pros | Cons |
|---|---|---|
| UI / UX | clean CLI workflow; creates and works through visible todo lists so the active model and progress stay clear | |
| Ease of use | self-verifies by running tests after implementing each feature, so less hand-holding needed | |
| Customizability | | |
| Flexibility | | non-desktop Claude Code produced noticeably less polished documentation than the desktop app on the same prompt, with no visual/diagram representation |
| Speed / responsiveness | | |
| Resource consumption | | |
| Model support | reliably delivers first-party system prompts to Anthropic models, which then follow every instruction and remember earlier ones from the same initial prompt; strong pairing with GPT 5.6 Tera, outperforming the same model via ChatGPT desktop app | |
| Other | astonishingly good pairing with Anthropic's own models | |

### Claude Desktop

| Aspect | Pros | Cons |
|---|---|---|
| UI / UX | | dislike the UI/UX |
| Ease of use | | context defaults to 200k; users must manually select the 1M setting (reported, not personally verified) |
| Customizability | | |
| Flexibility | markdown documentation output was spot-on, well-formatted, and unprompted included a visual diagram; on the same prompt/project, desktop output was clearly better than through Claude Code, suggesting it may be stronger for documentation tasks | lack of flexibility to use models well compared with third-party tools/apps |
| Speed / responsiveness | | |
| Resource consumption | | close to $90 worth of tokens spent on a documentation task in one session |
| Model support | astonishingly good within Anthropic's own models | |
| Other | | |

### ChatGPT Desktop App

| Aspect | Pros | Cons |
|---|---|---|
| UI / UX | excellent UI/UX; the PET screen-snapshot animation is especially polished | |
| Ease of use | the PET screen-snapshot concept makes it easy to send visual context | |
| Customizability | third-party tooling ("better chat GPT" style) allows pointing the app at custom providers/models; DeepSeek V4 Flash integration ran, but output was unusable and had to be reverted | |
| Flexibility | | |
| Speed / responsiveness | | |
| Resource consumption | | |
| Model support | | responses are noticeably worse here than when using the same OpenAI models through OpenCode or Claude Code; the harness itself produces weaker results despite the underlying model being capable |
| Other | | |

### Cherry Studio

| Aspect | Pros | Cons |
|---|---|---|
| UI / UX | | chat titles sometimes wrong, all caps, weird format; suspect backend issue |
| Ease of use | | unreliable chat-naming with some models |
| Customizability | works as expected with custom system prompts for some models (e.g. GPT 5.6 Tera) | |
| Flexibility | | doesn't surface third-party built-in search tools well to Claude models |
| Speed / responsiveness | initially fast with good results as a search assistant (Gemini 3.1 Flash) | Gemini 3.1 Flash hallucinated details as search assistant |
| Resource consumption | | |
| Model support | | doesn't reliably deliver an injected system prompt to first-party Anthropic models; traced to the CLI proxy stripping the custom prompt and injecting its own, likely to avoid getting the account banned — a harness/proxy issue, not a model issue |
| Other | | general fragility around system-prompt delivery to Anthropic models |

### OpenCode

| Aspect | Pros | Cons |
|---|---|---|
| UI / UX | with GPT 5.6 Tera, creates and works through a visible three-step todo list; workflow makes active model and todos clear | |
| Ease of use | | |
| Customizability | | |
| Flexibility | | |
| Speed / responsiveness | | |
| Resource consumption | | |
| Model support | strong pairing with GPT 5.6 Tera; model selection and created todos remain visible | |
| Other | pairing GPT 5.6 Tera with OpenCode seems like a strong workflow | |

### CC Switch

| Aspect | Pros | Cons |
|---|---|---|
| UI / UX | small router switcher in the Codex desktop app for choosing which model receives the task | |
| Ease of use | quick to configure; first route to DeepSeek V4 Flash worked end to end | |
| Customizability | lets you modify the desktop-app router, so messages can go to non-native models | no way to choose thinking/reasoning effort per model — always defaults to high for every routed model, which sometimes just burns extra tokens; would rather run a frontier model at low effort, but that control isn't exposed, so it's a compromise to accept |
| Flexibility | opened up Codex desktop to DeepSeek V4 Flash for the current task; supports image input — pasted a screenshot while routed to Claude Sonnet 5 and it correctly recognized the image contents | |
| Speed / responsiveness | | |
| Resource consumption | | |
| Model support | successfully routed Codex desktop messages to DeepSeek V4 Flash; switching the upstream format for Anthropic models from Chat Completions to Responses (native) fixed tool use and enabled spawning sub-agents in Codex — Chat Completions as upstream caused errors and blocked both tool use and sub-agent spawning for Anthropic models | cliproxyapi bug: older CC Switch builds wrote assistant message IDs as `resp_<id>_msg`; when a Claude-model conversation history with those IDs later replayed against a GPT model via the OpenAI Responses API, it was rejected since Responses API IDs must start with `msg` — fixed by adding a Codex-protocol payload filter in `/opt/homebrew/etc/cliproxyapi.conf` to strip those IDs before forwarding, then restarting cliproxyapi |
| Other | | new setup; needs more testing before a broader verdict; cloud models routed through CC Switch can be troublesome on advanced tasks — a long-horizon task appeared to get stuck thinking, with the last command repeatedly shown while the thinking view was expanded; possibly a UI or streaming-response issue, but tool calling is not consistently smooth |
