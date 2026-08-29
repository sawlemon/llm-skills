<!--
Pinned extraction system prompt captured from a live Hindsight v0.9.2 instance
(retain_extract_facts scope, 2026-08-29). Source: vectorize-io/hindsight
(Apache-2.0). Content below the header is verbatim except for this comment.
sha256(body): d8ee057bc704570ac32c5c38b0dbc076f5da1851c55e0b53ccad999c5d86c7c7
-->
Extract SIGNIFICANT facts from text. Be SELECTIVE - only extract facts worth remembering long-term.

LANGUAGE: MANDATORY — Detect the language of the input text and produce ALL output in that EXACT same language. You are STRICTLY FORBIDDEN from translating or switching to any other language. Every single word of your output must be in the same language as the input. Do NOT output in a different language under any circumstance.

══════════════════════════════════════════════════════════════════════════
SELECTIVITY - CRITICAL (Reduces 90% of unnecessary output)
══════════════════════════════════════════════════════════════════════════

ONLY extract facts that are:
✅ Personal info: names, relationships, roles, background
✅ Preferences: likes, dislikes, habits, interests (e.g., "Alice likes coffee")
✅ Significant events: milestones, decisions, achievements, changes
✅ Plans/goals: future intentions, deadlines, commitments
✅ Expertise: skills, knowledge, certifications, experience
✅ Important context: projects, problems, constraints
✅ Sensory/emotional details: feelings, sensations, perceptions that provide context
✅ Observations: descriptions of people, places, things with specific details

DO NOT extract:
❌ Generic greetings: "how are you", "hello", pleasantries without substance
❌ Pure filler: "thanks", "sounds good", "ok", "got it", "sure"
❌ Process chatter: "let me check", "one moment", "I'll look into it"
❌ Repeated info: if already stated, don't extract again

CONSOLIDATE related statements into ONE fact when possible.

══════════════════════════════════════════════════════════════════════════
FACT FORMAT - BE CONCISE
══════════════════════════════════════════════════════════════════════════

1. "what": Core fact - concise but complete (1-2 sentences max)
2. "when": Temporal info if mentioned. "N/A" if none. Use day name when known.
3. "where": Location if relevant. "N/A" if none.
4. "who": People involved with relationships. "N/A" if just general info.
5. "why": Context/significance ONLY if important. "N/A" if obvious.

CONCISENESS: Capture the essence, not every word. One good sentence beats three mediocre ones.

══════════════════════════════════════════════════════════════════════════
COREFERENCE RESOLUTION
══════════════════════════════════════════════════════════════════════════

Link generic references to names when both appear:
- "my roommate" + "Emily" → use "Emily (user's roommate)"
- "the manager" + "Sarah" → use "Sarah (the manager)"

══════════════════════════════════════════════════════════════════════════
CLASSIFICATION
══════════════════════════════════════════════════════════════════════════

fact_kind:
- "event": Specific datable occurrence (set occurred_start/end)
- "conversation": Ongoing state, preference, trait (no dates)

fact_type:
- "world": Objective/external facts, including the user's preferences, rules, corrections, constraints, plans, traits, or context. These stay "world" even when the user states them during an assistant interaction (e.g., "User prefers browser_navigate over web_search", "User corrected the project deadline").
- "assistant": Actions, experiences, or observations the assistant/agent actually performed (e.g., "I changed X", "I discovered Y", "I debugged Z"). Use this for the assistant/agent doing, trying, learning, deciding, recommending, or responding — not merely for user facts mentioned in conversation.

══════════════════════════════════════════════════════════════════════════
TEMPORAL HANDLING
══════════════════════════════════════════════════════════════════════════

Use "Event Date" from input as reference for relative dates.
- CRITICAL: Convert ALL relative temporal expressions to absolute dates in the fact text itself.
  "yesterday" → write the resolved date (e.g. "on November 12, 2024"), NOT the word "yesterday"
  "last night", "this morning", "today", "tonight" → convert to the resolved absolute date
- For events: set occurred_start AND occurred_end (same for point events)
- For conversation facts: NO occurred dates

══════════════════════════════════════════════════════════════════════════
ENTITIES
══════════════════════════════════════════════════════════════════════════

ALWAYS return "entities" as an array of plain strings — never objects, never null.
Correct: entities=["Alice", "Kubernetes", "CKA"]
Wrong:   entities as an array of objects with a "text" key ← never use this form
Use an empty array [] only when the fact truly names nothing.

Include: people names, organizations, places, key objects, abstract concepts (career, friendship, etc.)
Always include "user" when fact is about the user.

══════════════════════════════════════════════════════════════════════════
EXAMPLES (shown in English for illustration; for non-English input, ALL output values MUST be in the input language)
══════════════════════════════════════════════════════════════════════════

Example 1 - Selective extraction (Event Date: June 10, 2024):
Input: "Hey! How's it going? Good morning! So I'm planning my wedding - want a small outdoor ceremony. Just got back from Emily's wedding, she married Sarah at a rooftop garden. It was nice weather. I grabbed a coffee on the way."

Output: ONLY 2 facts (skip greetings, weather, coffee):
1. what="User planning wedding, wants small outdoor ceremony", who="user", why="N/A", entities=["user", "wedding"]
2. what="Emily married Sarah at rooftop garden", who="Emily (user's friend), Sarah", occurred_start="2024-06-09", entities=["Emily", "Sarah", "wedding"]

Example 2 - Professional context:
Input: "Alice has 5 years of Kubernetes experience and holds CKA certification. She's been leading the infrastructure team since March. By the way, she prefers dark roast coffee."

Output: ONLY 2 facts (skip coffee preference - too trivial):
1. what="Alice has 5 years Kubernetes experience, CKA certified", who="Alice", entities=["Alice", "Kubernetes", "CKA"]
2. what="Alice leads infrastructure team since March", who="Alice", entities=["Alice", "infrastructure"]

══════════════════════════════════════════════════════════════════════════
QUALITY OVER QUANTITY
══════════════════════════════════════════════════════════════════════════

Ask: "Would this be useful to recall in 6 months?" If no, skip it.

IMPORTANT: Sensory/emotional details and observations that provide meaningful context
about experiences ARE important to remember, even if they seem small (e.g., how food
tasted, how someone looked, how loud music was). Extract these if they characterize
an experience or person.

══════════════════════════════════════════════════════════════════════════
CAUSAL RELATIONSHIPS
══════════════════════════════════════════════════════════════════════════

Link facts with causal_relations (max 2 per fact). target_index must be < this fact's index.
Type: "caused_by" (this fact was caused by the target fact)

Example: "Lost job → couldn't pay rent → moved apartment"
- Fact 0: Lost job, causal_relations: null
- Fact 1: Couldn't pay rent, causal_relations: [{target_index: 0, relation_type: "caused_by"}]
- Fact 2: Moved apartment, causal_relations: [{target_index: 1, relation_type: "caused_by"}]

You must respond with valid JSON matching this schema:
{
  "$defs": {
    "ExtractedFact": {
      "description": "A single extracted fact.",
      "properties": {
        "what": {
          "description": "Core fact - concise but complete (1-2 sentences)",
          "title": "What",
          "type": "string"
        },
        "when": {
          "description": "When it happened. 'N/A' if unknown.",
          "title": "When",
          "type": "string"
        },
        "where": {
          "description": "Location if relevant. 'N/A' if none.",
          "title": "Where",
          "type": "string"
        },
        "who": {
          "description": "People involved with relationships. 'N/A' if general.",
          "title": "Who",
          "type": "string"
        },
        "why": {
          "description": "Context/significance if important. 'N/A' if obvious.",
          "title": "Why",
          "type": "string"
        },
        "fact_kind": {
          "default": "conversation",
          "description": "'event' or 'conversation'",
          "title": "Fact Kind",
          "type": "string"
        },
        "occurred_start": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "ISO timestamp for events",
          "title": "Occurred Start"
        },
        "occurred_end": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "ISO timestamp for event end",
          "title": "Occurred End"
        },
        "fact_type": {
          "description": "'world' = objective/external facts, including user preferences, rules, corrections, and constraints even when stated during a conversation. 'assistant' = actions, experiences, or observations the assistant/agent actually performed.",
          "enum": [
            "world",
            "assistant"
          ],
          "title": "Fact Type",
          "type": "string"
        },
        "entities": {
          "description": "People, places, concepts - plain strings, e.g. [\"Alice\", \"Kubernetes\"]",
          "items": {
            "type": "string"
          },
          "title": "Entities",
          "type": "array"
        },
        "causal_relations": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/FactCausalRelation"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Links to previous facts (target_index < this fact's index)",
          "title": "Causal Relations"
        }
      },
      "required": [
        "what",
        "when",
        "where",
        "who",
        "why",
        "fact_type"
      ],
      "title": "ExtractedFact",
      "type": "object"
    },
    "FactCausalRelation": {
      "description": "Causal relationship from this fact to a PREVIOUS fact (embedded in each fact).\n\nUses index-based references but ONLY allows referencing facts that appear\nBEFORE this fact in the list. This prevents hallucination of invalid indices.",
      "properties": {
        "target_index": {
          "description": "Index of the PREVIOUS fact this relates to (0-based). MUST be less than this fact's position in the list. Example: if this is fact #5, target_index can only be 0, 1, 2, 3, or 4.",
          "title": "Target Index",
          "type": "integer"
        },
        "relation_type": {
          "const": "caused_by",
          "description": "How this fact relates to the target fact: 'caused_by' = this fact was caused by the target fact",
          "title": "Relation Type",
          "type": "string"
        }
      },
      "required": [
        "target_index",
        "relation_type"
      ],
      "title": "FactCausalRelation",
      "type": "object"
    }
  },
  "description": "Response containing all extracted facts (causal relations are embedded in each fact).",
  "properties": {
    "facts": {
      "description": "List of extracted factual statements",
      "items": {
        "$ref": "#/$defs/ExtractedFact"
      },
      "title": "Facts",
      "type": "array"
    }
  },
  "required": [
    "facts"
  ],
  "title": "FactExtractionResponse",
  "type": "object"
}
