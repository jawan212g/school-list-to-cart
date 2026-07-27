---
name: capstone-project-workflow
description: Use this skill when planning, researching, building, testing, documenting, or reviewing the School List-to-Cart Agent capstone project.
---

# Capstone Project Workflow

## Purpose

Use this skill to complete structured work on the School List-to-Cart Agent while following the project requirements, preserving project memory, and keeping all work organized inside the current repository.

## When to Use This Skill

Use this skill for tasks involving:

- Project planning
- Requirements review
- Research
- Application development
- AI agent design
- Product matching
- Cart optimization
- Testing
- Documentation
- Demonstration preparation
- Final project review

## Required Reading

Before beginning meaningful work:

1. Read `AGENTS.md`.
2. Read `BRD.md` as the detailed specification of record.
3. Read `PROJECT.md` for the project purpose, audience, scope, deliverables, constraints, and success criteria.
4. Read the most recent entries in `JOURNAL.md`.
5. Inspect the existing project files before creating, replacing, moving, or deleting anything.

If instructions conflict, do not silently choose one. Explain the conflict and ask for direction.

## Workflow

### 1. Understand the Task

- Identify the current objective.
- Identify the requested deliverable.
- Identify relevant requirements from `BRD.md`.
- Identify constraints, assumptions, and missing information.
- Ask for clarification only when the missing information prevents safe or accurate work.

### 2. Inspect Existing Work

- Review relevant files before making changes.
- Reuse existing code, functions, data structures, and documentation when practical.
- Do not recreate functionality that already exists.
- Do not overwrite original files without approval.

### 3. Create a Plan

Before substantial changes, provide a short implementation plan that identifies:

- What will be changed
- Which files will be affected
- How the result will be verified
- Any risks or limitations

### 4. Complete the Work

- Make the smallest practical set of changes needed.
- Keep all files inside the current repository.
- Follow the folder and naming conventions in `AGENTS.md`.
- Use readable, maintainable code.
- Clearly label placeholders, mock data, assumptions, and incomplete work.

### 5. Test and Verify

Test the result before declaring the task complete.

Verification may include:

- Running automated tests
- Running the Streamlit application
- Checking expected outputs
- Testing normal inputs
- Testing missing or incorrect inputs
- Testing edge cases
- Testing tool or API failures
- Confirming calculations independently
- Reviewing documentation for accuracy

Do not claim that something works unless it was tested or otherwise verified.

### 6. Update Documentation

Update `PROJECT.md` when the following change:

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

After meaningful work, append a dated entry to `JOURNAL.md`.

### 7. Report Results

At the end of the task, report:

- What was completed
- Files created or modified
- Testing or verification performed
- Assumptions or limitations
- Unresolved problems
- Recommended next step

## Core Architecture Rule

**The language model reads and interprets. Deterministic code calculates.**

The language model may:

- Extract supply-list information
- Normalize item descriptions
- Classify products
- Match required items to possible products
- Explain recommendations
- Ask the user for clarification

The language model must not:

- Calculate prices
- Calculate cart totals
- Calculate package quantities
- Calculate unit conversions
- Calculate optimization scores
- Invent availability
- Invent product data
- Claim that an order was completed without verification

Python or other deterministic code must calculate:

- Required quantities
- Package counts
- Unit prices
- Extended prices
- Store subtotals
- Fees
- Taxes when included
- Cart totals
- Optimization results
- Comparison scores

## Agentic AI Requirements

Every agentic workflow should clearly define:

- User
- Goal
- Trigger
- Inputs
- Outputs
- Tools
- Constraints
- Approval points
- Error handling
- Fallback behavior
- Stopping condition

The agent must not continue indefinitely. It must stop when:

- The requested cart or recommendation is complete
- Required information is unavailable
- The user must provide clarification
- A tool fails and no safe fallback exists
- Human approval is required
- The maximum allowed retry count is reached

## Human Approval Requirements

Require explicit human approval before:

- Purchasing products
- Adding products to a live retailer account
- Sending external messages
- Sharing personal information
- Making irreversible changes
- Using paid services
- Submitting an order

A recommendation or simulated cart is not the same as an approved purchase.

## Data Requirements

Use only:

- Public data
- Mock data
- Synthetic data
- Anonymized data
- Classroom-approved data
- User-provided data that is appropriate for the project

Do not use:

- Proprietary Lockheed Martin information
- Controlled technical information
- Export-controlled information
- Personal credentials
- Private API keys
- Passwords
- Tokens stored directly in source code

Record the source and date of important datasets when available.

## Product-Matching Requirements

When matching school-supply requirements to products:

- Preserve required quantities.
- Preserve required sizes, colors, brands, and materials when mandatory.
- Distinguish required attributes from preferences.
- Do not substitute products that violate mandatory requirements.
- Explain uncertain matches.
- Request human confirmation for ambiguous matches.
- Allow the user to reject or replace a recommendation.

## Optimization Requirements

The optimization logic should be deterministic and explainable.

Possible objectives may include:

- Lowest total cost
- Fewest stores
- Best availability
- Fastest pickup or delivery
- Preferred retailer
- Balanced cost and convenience

The system must clearly state which objective is being used.

Optimization results should account for applicable factors such as:

- Product price
- Required quantity
- Package quantity
- Store availability
- Pickup or delivery fees
- Minimum-order requirements
- Number of stores
- User preferences

Do not hide tradeoffs from the user.

## Error Handling

The project should handle:

- Missing supply-list information
- Unreadable uploads
- Ambiguous item descriptions
- Products with no valid match
- Duplicate items
- Incorrect quantities
- Missing prices
- Missing availability
- Tool failures
- API failures
- Empty results
- Network problems
- Invalid user inputs

When an error occurs:

1. Explain the problem clearly.
2. Preserve completed work when possible.
3. Use a safe fallback when available.
4. Ask for human input when necessary.
5. Do not fabricate missing information.

## Testing Expectations

Include tests for:

- Correct item extraction
- Correct quantity normalization
- Correct package calculations
- Correct product matching
- Correct price calculations
- Correct store totals
- Correct optimization behavior
- Human approval gates
- Missing data
- Invalid inputs
- No-match scenarios
- Tool failure scenarios

Use repeatable test data whenever possible.

## Demonstration Requirements

The prototype should support a reliable five-minute demonstration.

The demonstration should show:

1. A school-supply list being uploaded, entered, or selected.
2. Required items being extracted.
3. Products being matched.
4. Quantities and prices being calculated.
5. A recommended cart being produced.
6. Tradeoffs being explained.
7. Human approval being required before purchase-related action.

The demonstration should avoid unnecessary setup, long waits, and unstable external dependencies.

## Journal Update Format

After meaningful work, append an entry to `JOURNAL.md` containing:

- Date
- Objective
- Work completed
- Decisions made
- Problems or limitations
- Files created or changed
- Testing or verification performed
- Remaining work
- Recommended next step

Do not remove or rewrite previous entries unless explicitly instructed.

## Completion Checklist

Before finishing a task, confirm:

- The request was completed.
- The result follows `BRD.md`.
- Existing files were reviewed.
- Files were saved in the correct location.
- Calculations were performed by deterministic code.
- Human approval requirements were preserved.
- Relevant testing or verification was completed.
- Assumptions and limitations were documented.
- `PROJECT.md` was updated when necessary.
- `JOURNAL.md` was updated.
- The final response identifies what changed and what should happen next.