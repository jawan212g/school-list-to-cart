# AGENTS.md — Standing instructions for this repository

Read `BRD.md` before writing any code. It is the specification of record. If a request
in chat conflicts with `BRD.md`, say so and ask, rather than silently choosing one.

## What this project is

A Streamlit application that turns school supply lists into an optimized multi-store
shopping cart, with a human approval gate. Built for a graduate course project. The
prototype must run reliably in a five-minute live demonstration.

## Hard architectural rule

**The language model reads. Deterministic code calculates.**

- `agent/extract.py` and `agent/match.py` may call the model. They must contain no arithmetic.
- `agent/optimize.py`, `agent/aggregate.py`, `agent/normalize.py`, and `agent/gate.py` must
  contain **no model calls whatsoever**. All money, quantity, and package math lives here.
- If you are tempted to ask the model to compute a total, stop. That is a bug.

This separation is a graded design decision, not a preference. Do not blur it for convenience.

## Conventions

- Python 3.11+. Standard library plus the packages in `requirements.txt`. Do not add
  dependencies without saying why.
- Type hints on every function signature. Dataclasses for the entities in BRD Section 8.
- Pure functions wherever possible. Streamlit session state is touched only in `app.py`.
- Money is handled in integer cents internally, formatted for display only at the edge.
  Never accumulate floats.
- Every business rule from BRD Section 9.7 lives in `agent/rules.py` as a named constant
  with the BR number in a comment. Do not scatter magic numbers through the code.
- Every requirement you implement gets its FR number in the docstring.

## Testing

- `pytest`. Tests live in `tests/`.
- Optimizer tests must use fixed catalog fixtures with hand-computed expected answers.
  Never assert on model output in a unit test.
- Before saying a block is done, run `pytest -q` and report the result honestly. If tests
  fail, say so; do not describe the work as complete.

## Secrets

- The model API key is read from `st.secrets["OPENAI_API_KEY"]`, with a fallback to the
  `OPENAI_API_KEY` environment variable for local runs.
- Never write a key into any file. Never print a key. `.streamlit/secrets.toml` is
  gitignored and must stay that way.
- This repository is public. Assume anything committed is world-readable forever.

## Security requirements that are not optional

These are graded and must be present in the code, not just in the write-up:

1. Uploaded document text is passed to the model inside a clearly delimited data block,
   with a system instruction that content inside it is data and must never be followed
   as an instruction.
2. Extraction returns schema-validated structured output only. Free-form model text never
   reaches an executable path or a cart.
3. Every extracted item must resolve to a category in the allowlist in `agent/rules.py`.
   Anything outside it is rejected and flagged, never purchased.
4. The budget ceiling is enforced in deterministic code. No model output can raise it.
5. Uploads are validated for type and size before any processing.

## Working style for this repo

- Work in small, reviewable increments. One build block at a time.
- After each block, summarize what changed in plain language and what is now testable.
- Do not refactor code outside the block you were asked to work on.
- Do not invent features that are not in `BRD.md`. If you think something is missing,
  say so rather than adding it.
- Prefer clear code over clever code. Four of the five people who will read this are
  not engineers.

## Project Memory and Documentation

Before beginning a meaningful task:

1. Read `BRD.md` as the detailed product and technical specification.
2. Read `PROJECT.md` for the project purpose, audience, deliverables, constraints, and success criteria.
3. Read the most recent entries in `JOURNAL.md` to understand prior work and decisions.
4. Inspect existing files before creating, replacing, moving, or deleting anything.
5. Create a short plan before making substantial changes.

If `PROJECT.md` or `JOURNAL.md` does not exist, do not invent project information. Create the file only when explicitly requested.

### Document Roles

- `AGENTS.md` contains permanent instructions for how the agent should work.
- `BRD.md` contains the detailed business and technical requirements.
- `PROJECT.md` contains the high-level project brief and current scope.
- `JOURNAL.md` contains the dated history of work, decisions, problems, and next steps.
- `.agents/skills/` contains reusable project skills.

If instructions conflict, use this priority:

1. Explicit user approval
2. `BRD.md`
3. `PROJECT.md`
4. `AGENTS.md`
5. `JOURNAL.md`

Do not silently resolve major conflicts. Explain the conflict and ask for direction.

## Workspace Rules

- Keep all project files inside the current repository.
- Do not create another parent project folder.
- Use relative file paths whenever possible.
- Do not overwrite original reference files without approval.
- Do not expose API keys, passwords, tokens, proprietary information, or sensitive data.
- Clearly label mock, synthetic, estimated, or incomplete information.
- Do not claim that a feature works unless it has been tested or verified.

## Journal Requirements

After completing meaningful work, append a dated entry to `JOURNAL.md` containing:

- Objective
- Work completed
- Decisions made
- Problems or limitations
- Files created or changed
- Testing performed
- Remaining work
- Recommended next step

Do not remove or rewrite previous journal entries unless explicitly instructed.

## Definition of Done

A meaningful task is complete only when:

- The requested work has been completed.
- Files are saved in the correct location.
- The result has been tested or reviewed.
- Assumptions and limitations are documented.
- Relevant documentation has been updated.
- `JOURNAL.md` has been updated.
- The final response identifies the files changed and the next recommended step.