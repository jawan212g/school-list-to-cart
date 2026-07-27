# AGENTS.md

## Purpose

This file contains the permanent operating instructions for Codex while working on the Capstone - AI Agentic project.

The specific project scope, users, requirements, platforms, and success criteria will be maintained in PROJECT.md.

The history of completed work, decisions, problems, and next steps will be maintained in JOURNAL.md.

## Start-of-Task Procedure

Before beginning any meaningful task:

1. Read this AGENTS.md file.
2. Read PROJECT.md if it exists.
3. Read the most recent entries in JOURNAL.md if it exists.
4. Inspect the current files and folders before creating or replacing anything.
5. Identify the user’s current objective and constraints.
6. Create a short implementation plan before making major changes.

If PROJECT.md or JOURNAL.md does not exist yet, continue with the requested task without inventing missing project information.

## Workspace Rules

- Keep all files inside the current Capstone - AI Agentic workspace.
- Never create another parent project folder.
- Do not save files in Documents, Desktop, OneDrive, or another location outside this workspace.
- Use relative file paths whenever possible.
- Inspect existing files before creating replacements.
- Do not overwrite original files unless the user explicitly approves it.
- Do not delete, rename, or move important files without permission.
- Do not expose passwords, API keys, tokens, proprietary data, or sensitive information.
- Use sample, mock, anonymized, or publicly available data when appropriate.
- Clearly label assumptions, placeholders, mock data, and incomplete work.

## Project Organization

Use the following folder structure when those folders are created:

- `research/` — research notes, findings, source summaries, and citations
- `references/` — original reference documents and source materials
- `data/` — datasets, sample data, cleaned data, and data documentation
- `src/` — application code, scripts, prompts, workflows, and configuration files
- `tests/` — test cases, evaluation data, and verification scripts
- `deliverables/` — final reports, presentations, demonstrations, and submission files
- `.agents/skills/` — reusable Codex skills for this project

Do not create unnecessary folders or files merely to fill out the structure.

## Development Workflow

For substantial work:

1. Review the project objective and relevant existing files.
2. Explain the proposed approach briefly.
3. Make the smallest practical set of changes needed.
4. Keep related work organized in the appropriate folder.
5. Test or verify the result.
6. Fix errors that can be safely resolved.
7. Clearly explain unresolved errors, limitations, or missing information.
8. Update project documentation when the scope or design changes.
9. Update JOURNAL.md after meaningful work is completed.

## Research Standards

When conducting research:

- Prefer authoritative, primary, official, academic, or government sources.
- Record the source title, organization, publication date, access date, and link when available.
- Separate sourced facts from assumptions or recommendations.
- Do not invent statistics, citations, quotations, or research findings.
- Explain when information cannot be independently verified.
- Avoid using proprietary Lockheed Martin information or controlled technical information.
- Use public, synthetic, anonymized, or classroom-approved information for demonstrations.

## Agentic AI Standards

When designing or evaluating an AI agent:

- Clearly define the user, goal, trigger, inputs, outputs, tools, constraints, and stopping condition.
- Distinguish between deterministic workflow steps and decisions made by the agent.
- Use human approval before purchases, external messages, irreversible actions, or sensitive decisions.
- Apply least-privilege access to tools and data.
- Include error handling and fallback behavior.
- Prevent the agent from claiming success without verification.
- Document where human review is required.
- Test normal cases, edge cases, incorrect inputs, missing data, and tool failures.
- Track accuracy, usefulness, reliability, latency, and completion rate when relevant.

## Coding Standards

When creating code:

- Prioritize readable and maintainable code.
- Use clear names for files, functions, variables, and components.
- Include comments where the purpose is not obvious.
- Avoid unnecessary complexity.
- Handle expected errors and missing inputs.
- Do not hard-code credentials, API keys, tokens, passwords, or private file paths.
- Store configuration separately from application logic when practical.
- Create or update setup instructions when dependencies are introduced.
- Do not install major dependencies without explaining why they are necessary.
- Run available tests or verification commands before declaring work complete.

## Change Management

Before making a major design or architecture change:

1. Explain the proposed change.
2. Explain why the change is needed.
3. Identify which files will be affected.
4. Preserve the existing version when practical.
5. Record the final decision in JOURNAL.md.

Update PROJECT.md when any of the following change:

- Problem statement
- Project goal
- Target user
- Scope
- Main features
- Platforms or tools
- Data sources
- Constraints
- Deliverables
- Success criteria

## JOURNAL.md Requirements

After meaningful work, append a dated entry to JOURNAL.md containing:

- Date
- Objective
- Work completed
- Decisions made
- Problems or limitations
- Files created or changed
- Testing or verification performed
- Remaining work
- Recommended next step

Do not rewrite or remove earlier journal entries unless explicitly instructed.

## Definition of Done

A task is complete only when:

- The requested work has been performed.
- Outputs are saved in the correct workspace location.
- The result has been reviewed, tested, or otherwise verified.
- Major assumptions and limitations are documented.
- Relevant documentation has been updated.
- JOURNAL.md has been updated when the task involved meaningful project work.
- The final response identifies what changed and the next recommended action.

## Communication Style

When reporting results:

- Use clear, direct language.
- Be concise but provide enough detail to review the work.
- State which files were created or modified.
- Summarize testing or verification.
- Identify assumptions, risks, and unresolved issues.
- Do not claim that something works unless it was tested or verified.
