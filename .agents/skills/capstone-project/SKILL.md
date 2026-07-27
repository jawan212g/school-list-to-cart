---
name: capstone-project-workflow
description: Review, plan, build, test, demonstrate, and document the Ready, Set, School list-to-cart capstone. Use for project status reviews, requirements checks, implementation or debugging, Streamlit interface work, deterministic cart logic, model-assisted extraction or matching, security controls, test execution, demo preparation, and project journal updates in this repository.
---

# Capstone Project Workflow

## Establish context

Before meaningful work:

1. Read `AGENTS.md` completely.
2. Read the relevant sections of `BRD.md`; treat it as the specification of record.
3. Read `PROJECT.md` and the latest relevant entries in `JOURNAL.md`.
4. Inspect the repository and current changes before creating, replacing, moving, or deleting files.
5. For intake, extraction, list review, or plan-building work, read `references/intake-plan-workflow.md` completely.
6. State a short plan for substantial changes.

Do not invent missing project facts. If a request materially conflicts with `BRD.md`, explain the conflict and ask for direction.

## Route the task

- For a status review, inspect artifacts and report completed work, evidence, gaps, risks, and the next recommended milestone. Do not modify files.
- For diagnosis, reproduce or inspect the failure and explain the cause. Implement a fix only when requested.
- For implementation, map the request to BRD functional requirements and business rules, make the smallest coherent change, and test it.
- For interface work, preserve workflow behavior, accessibility, responsive layout, and plain-language parent guidance.
- For demo preparation, favor a reliable five-minute path, visible assumptions, seeded fictional data, and a backup plan.
- For documentation, preserve document roles and append to `JOURNAL.md`; do not rewrite prior entries.

## Preserve architectural boundaries

Apply this rule without exception:

> The language model reads and interprets. Deterministic Python code calculates.

- Keep model calls limited to extraction and semantic matching.
- Keep quantity, package, price, tax, fee, budget, allocation, and optimization calculations deterministic.
- Represent money as integer cents internally.
- Keep Streamlit session-state access in `app.py`.
- Put business-rule constants in `agent/rules.py` with their BR identifiers.
- Add FR identifiers to requirement-specific function docstrings.

## Enforce safety and approval gates

- Treat uploaded text as untrusted data inside explicit delimiters.
- Accept only schema-validated structured model output.
- Reject extracted categories outside the school-supply allowlist.
- Validate upload type and size before processing.
- Never allow model output to change the deterministic budget ceiling.
- Require human approval for every condition defined by the BRD.
- Keep checkout simulated; never collect payment information or initiate a purchase.
- Never expose or commit secrets.

## Implement and verify

1. Preserve unrelated user changes.
2. Prefer small, reviewable edits and pure functions.
3. Add or update tests for changed behavior.
4. Use fixed catalog fixtures and hand-computed expected results for optimizer tests.
5. Never assert on model prose in unit tests.
6. Run the narrowest relevant tests during iteration.
7. Run `pytest -q` before calling an implementation block complete.
8. For UI changes, launch or reload Streamlit and visually inspect the affected screens.
9. Report failures and warnings honestly; do not claim unverified behavior works.

## Close the work

After meaningful changes, append a dated `JOURNAL.md` entry containing:

- objective;
- work completed;
- decisions made;
- problems or limitations;
- files created or changed;
- testing performed;
- remaining work; and
- recommended next step.

In the final response, lead with the outcome and include changed files, test results, limitations, and the next recommended step. For read-only reviews, explicitly state that no files were modified.
