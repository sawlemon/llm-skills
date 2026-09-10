---
name: big-brain
description: Conserve the main top-tier model's usage by making it orchestrate smaller subagents for exploration, implementation, and verification while retaining critical decisions and final responsibility. Use only when the user explicitly invokes big-brain or `/big-brain`; never trigger automatically from task size or complexity.
---

# Big Brain

Act as the lead model, not the primary worker. Protect the user's limited top-tier model quota by delegating as much token-heavy work as practical while keeping judgment, direction, and accountability in the main conversation.

## Division of responsibility

The main model owns:

- understanding the user's actual goal and constraints;
- deciding how to divide the work;
- making architectural, product, security, scope, and other consequential decisions;
- resolving conflicts between subagent findings;
- reviewing evidence before accepting a result;
- communicating with the user and delivering the final answer.

Subagents own most execution:

- repository and documentation exploration;
- gathering, filtering, and consolidating large amounts of information;
- implementing code after the main model has settled the direction;
- running focused checks and reporting exact results;
- independent review or verification when useful.

Do not redo a delegated task in the main context. Read the returned consolidation, inspect only the evidence needed for decisions, and delegate follow-up work when the result is incomplete.

## Route work by model

### Luna

Prefer Luna for work that consumes many tokens but does not require the strongest judgment:

- broad repository exploration and inventories;
- reading many files or documents;
- searching across naming conventions and directories;
- extracting facts, patterns, interfaces, dependencies, or test coverage;
- consolidating long outputs into a decision-ready summary;
- running settled, deterministic verification and organizing the results.

Luna gathers and compresses evidence. Do not ask Luna to make the final architectural decision, reinterpret unclear user intent, or silently expand scope.

### Sonnet

Prefer Sonnet when execution needs stronger reasoning:

- writing or modifying code from a settled direction;
- designing a focused implementation within boundaries chosen by the main model;
- diagnosing a bounded technical issue after enough evidence exists;
- reviewing code for correctness, maintainability, security, or specification compliance;
- producing tests that exercise an agreed behavior;
- reconciling a small number of technically subtle findings.

Sonnet may recommend a decision, but the main model accepts, rejects, or changes it when the choice is consequential.

### Fallbacks

Check that economical subagents are available before starting token-heavy work. Use the named Luna and Sonnet agent types when the harness exposes them. If one is unavailable, use the closest available smaller subagent and preserve the same role split. Do not substitute another top-tier model merely for convenience. If the harness exposes no subagent mechanism, or no suitable smaller model is available, stop before bulk exploration or execution. Report the limitation concisely and explain that the task needs a compatible session or the user's explicit authorization to spend the main model's quota. Do not silently continue the full task in the main context.

## Delegate with a complete task contract

Every subagent prompt must be self-contained. Include all of the following:

1. **Objective and deliverable.** State the exact question to answer or artifact to produce, plus what a successful result looks like.
2. **Scope.** Name what is in scope and explicitly out of scope.
3. **Ordered method.** Give the steps to follow, including the files, evidence, interfaces, or commands to inspect when known. Do not prescribe guessed commands before evidence supports them.
4. **Constraints.** Carry forward relevant user instructions, repository rules, safety limits, ownership boundaries, and restrictions on edits or outward-facing actions.
5. **Verification.** State the tests, checks, observations, or evidence that define completion.
6. **Return format.** Require a concise consolidation containing findings or changes, exact evidence such as file paths and line numbers, checks run and their results, unresolved issues, and decisions the main model must make.
7. **Stop condition.** If evidence conflicts with the contract, a required step cannot be completed, or the work needs a scope change, stop and report the conflict and smallest proposed deviation instead of improvising.

Use this shape when drafting a delegation:

```text
Objective:
Expected deliverable:
In scope:
Out of scope:
Ordered steps:
Constraints to preserve:
Completion checks:
Return exactly:
Stop and report if:
```

Specific contracts save main-model tokens because they prevent wandering, repeated exploration, and unusable file dumps.

## Orchestration workflow

1. Read enough of the request and current context to identify the desired outcome, hard constraints, and decisions that genuinely require the main model.
2. Split the task into independent work packets. Keep tightly coupled work together, and never assign parallel agents to edit the same files.
3. Route broad exploration and consolidation to Luna. Route code and reasoning-heavy execution to Sonnet.
4. Launch independent packets in parallel. Use sequential delegation only when a later packet depends on an earlier result.
5. Ask subagents for conclusions and evidence, not transcript-sized dumps. The main context should receive only information needed to decide or integrate.
6. Make the critical decisions in the main conversation. Record those decisions explicitly in later implementation contracts so subagents do not reopen them.
7. Delegate implementation. Give each editing agent clear file ownership and instruct it not to touch unrelated or pre-existing work.
8. Delegate verification to a separate subagent when practical. For deterministic checks, Luna is usually sufficient. Use Sonnet when verification requires nuanced code judgment.
9. Review the returned evidence. If agents disagree, narrow the disputed question and commission a focused follow-up rather than redoing all work personally.
10. Deliver one coherent final response. State what changed or what was found, the important decisions, verification actually performed, failures or skipped checks, and any blocker only the user can resolve.

## Parallelism rules

- Run independent research, codebase exploration, and review packets concurrently.
- Do not parallelize work with an unresolved shared decision. The main model decides first, then delegates.
- Do not let multiple agents edit overlapping files or race on shared state.
- Prefer one well-scoped agent over several agents duplicating the same search.
- Use a second agent for independent verification only when it adds evidence rather than ceremony.

## Main-model discipline

- Spend main-model tokens on judgment, not bulk reading or routine command output.
- Do not narrate every delegation. Give the user only brief progress updates when a finding changes the direction or reveals a blocker.
- Do not accept a subagent's confidence as proof. Require paths, lines, command results, test output, or other checkable evidence.
- Do not claim work passed because an agent said it should pass. Report only checks that actually ran and their observed results.
- Preserve normal confirmation requirements for destructive or outward-facing actions. Delegation does not transfer or bypass the user's authority.
- The main model remains responsible for the final result even when subagents performed the work.
