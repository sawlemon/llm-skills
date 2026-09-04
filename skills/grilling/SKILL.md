---
name: grilling
description: Stress-test a plan, decision, design, or idea through a structured interview. Use when the user asks to grill an idea, wants assumptions challenged, or needs a plan made decision-complete.
---

# Grilling

Build a decision tree for the requested outcome. Separate settled decisions from unresolved branches.

1. Inspect the repository, files, tools, and existing documentation for facts you can establish yourself. Do not ask the user to find facts the agent can inspect.
2. Find the current frontier: decisions whose prerequisites are already settled.
3. Ask about the frontier in one round. For each question, give a short recommendation and the reason it is the default.
4. Wait for the user's answers. Do not silently decide user-owned choices.
5. Recompute the frontier after each answer. Keep settled decisions visible and remove resolved questions.
6. Stop when the route to implementation is clear, the important branches are resolved, and the remaining choices do not change the outcome.

Use plain Markdown. Keep questions concrete. Do not turn this into an intake questionnaire. Do not implement or make outward-facing changes until the planning gate is complete and the user asks for execution.

This workflow is intentionally different from `i-have-adhd`: `i-have-adhd` reduces work to one next action, while `grilling` is an explicit deeper planning mode. Never invoke `grilling` automatically from ADHD coaching.
