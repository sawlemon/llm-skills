# llm-skills

Personal collection of reusable LLM system prompts ("skills") and a running scorecard of model behavior, used across tools like Claude Code and Cherry Studio.

## Contents

### `persona/`

Skill definitions (`SKILL.md`) that get injected as system prompts into LLM tools/apps.

- **`alfred/`** — baseline behavior rules applied to every conversation: routes long-term memory through the Hindsight MCP server, enforces concise output, and requires epistemic honesty (search before guessing, admit uncertainty).
- **`hinsighter/`** — detailed operating protocol for the Hindsight MCP memory server: bank selection (`health`, `career`, `finances`, `work`, `default`), recall/reflect/retain decision gates, tagging conventions, and prohibitions (no credentials stored, no fabricated recalls, etc).

### `LLM_SCORECARD.md`

Running per-model log of observed strengths/weaknesses, organized by provider → model. Each model gets a table of notes across aspects (reasoning, coding, instruction-following, tool use, speed, cost, formatting, etc), prefixed `+` (good) / `-` (bad). Currently tracks Claude (Sonnet 5, Opus 4.6/4.7/4.8), GPT (5.5 Terra, 5.6 Sol), Gemini (3.1/3.6 Flash), DeepSeek (V4 Flash), and GLM (5.2).

## Usage

- Point a tool's system prompt at a `persona/*/SKILL.md` file to apply that behavior.
- When trying a model and forming an opinion of it, log the observation in `LLM_SCORECARD.md` under the right provider/model/aspect.
