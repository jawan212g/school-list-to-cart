# Project Journal

## 2026-07-25 — Establish the project charter

### Objective

Convert the approved School List-to-Cart Agent proposal and API-risk feedback into an authoritative `PROJECT.md` that can guide implementation.

### Work completed

- Defined the problem, project goal, value proposition, and target users.
- Established a seeded fictional catalog as the Phase 1 data strategy.
- Defined the Phase 1 scope and explicitly deferred live retailer integrations and real checkout.
- Documented the agent's user, trigger, inputs, outputs, tools, constraints, and stopping condition.
- Separated model-assisted interpretation from deterministic arithmetic and rules.
- Defined cost, optimization, approval, replanning, security, privacy, testing, and success requirements.
- Established four implementation milestones and the Phase 1 definition of done.

### Decisions made

- Use Python and Streamlit for the prototype.
- Use a seeded catalog of four fictional stores rather than live retailer APIs.
- Include tax and fulfillment fees in landed cost.
- Apply a $6 implicit comparison penalty for each additional store without presenting it as a user charge.
- Build and test the deterministic optimizer before adding model-based extraction.
- Treat stockout injection and targeted replanning as central demonstration features.
- Keep checkout simulated and require human approval for material decisions.

### Problems or limitations

- No usable real-time retailer inventory interface is assumed.
- The product catalog and prices will be representative rather than live.
- The project charter is based on the supplied proposal; measured accuracy and time-saving results do not exist yet.
- The detailed schema and optimizer implementation remain to be created and tested.

### Files created or changed

- Created `PROJECT.md`.
- Created `JOURNAL.md`.

### Testing or verification performed

- Confirmed before creation that neither `PROJECT.md` nor `JOURNAL.md` existed.
- Reviewed the charter against the supplied proposal, API feedback, and permanent workspace instructions.
- No application code exists yet, so no runtime or automated tests were applicable.

### Remaining work

- Define executable core data schemas.
- Create a compact seeded catalog fixture.
- Implement deterministic package, landed-cost, and store-selection logic.
- Add automated tests for the core business rules.
- Build the Streamlit vertical slice after the deterministic foundation is verified.

### Recommended next step

Create the core schemas and a small test catalog, then implement the deterministic optimizer and its first unit tests.

## 2026-07-26 — Set up the handed-over application

### Objective

Bring the existing Ready, Set, School application from the Team 6 GitHub repository into the local project workspace and verify that the handed-over build runs safely.

### Work completed

- Connected the local Git repository to `https://github.com/jawan212g/school-list-to-cart.git`.
- Fetched and checked out the repository's `main` branch at commit `b3b0797`.
- Preserved the previous root workspace instructions at `references/pre-handover/AGENTS.md`.
- Retained the existing `PROJECT.md` and `JOURNAL.md`.
- Created a local Python 3.12 virtual environment in `.venv`.
- Installed exactly the dependencies declared in `requirements.txt`.
- Confirmed that the seeded catalog contains four stores and 120 offers.
- Confirmed that `.streamlit/secrets.toml` is excluded by `.gitignore`.

### Decisions made

- Treat `BRD.md` as the specification of record, consistent with the repository's official `AGENTS.md`.
- Preserve prior local documentation rather than deleting or silently overwriting it.
- Keep the local environment and API secret outside version control.
- Do not push to GitHub or update the live application during setup.

### Problems or limitations

- No local `OPENAI_API_KEY` environment variable or `.streamlit/secrets.toml` file is configured.
- Model-backed extraction and matching cannot be exercised locally until the user supplies a valid API key through a private local secret.
- The handover reports two realistic project-created sample lists, but genuine school-list validation remains outstanding.

### Files created or changed

- Checked out all tracked application files from `origin/main`.
- Created the ignored `.venv/` local environment.
- Moved the previous local `AGENTS.md` to `references/pre-handover/AGENTS.md`.
- Updated `JOURNAL.md`.

### Testing or verification performed

- Ran the complete automated suite: 138 tests passed in 2.54 seconds.
- Started the Streamlit application locally in headless mode.
- Confirmed the local application returned HTTP 200.
- Confirmed local `main`, `origin/main`, and the checked-out commit all match.
- Confirmed the local secret path is ignored and no secret file is present.

### Remaining work

- Configure a local OpenAI API key without committing or displaying it.
- Exercise both sample lists through the local interface at $150 and $85.
- Collect and hand-label ten genuine school supply lists.
- Time one manual cart-building baseline.
- Reconcile `BRD.md` with the implementation drift listed in the handover.
- Address the open defects and partial requirements in handover priority order.

### Recommended next step

Configure the local API secret, then run the two supplied sample lists through the local application before making any code changes.

## 2026-07-26 — Kid-friendly interface refresh

### Objective

Make the Ready, Set, School interface feel more welcoming and school-themed while preserving accessibility, parent-focused clarity, and all existing application behavior.

### Work completed

- Replaced the restrained visual palette with brighter blue, coral, yellow, mint, and purple accents.
- Added a subtle ruled-notebook-paper background.
- Updated headings to use a friendly rounded system typeface and added a pencil title accent.
- Made cards, forms, metrics, notifications, tables, inputs, and buttons more rounded and visually distinct.
- Added clearer focus styling and gentle button hover feedback.
- Updated the progress indicator to use a multi-color school-supply palette.
- Added a backpack browser icon.
- Preserved the responsive layout and simplified the decorative background on small screens.

### Decisions made

- Keep the application friendly rather than overly childish because parents and caregivers remain the primary users.
- Use CSS and an emoji page icon rather than adding image assets or new dependencies.
- Preserve the existing warm and plain tone registers, especially for shortfall and error states.
- Make no changes to business logic, model behavior, security controls, or screen flow.

### Problems or limitations

- The visual review covered the initial intake screen; later screens retain the same shared style but should also be reviewed during a full API-backed session.
- A local OpenAI API key is still required to exercise extraction and matching through the complete interface.

### Files created or changed

- Updated `app.py`.
- Updated `.streamlit/config.toml`.
- Updated `JOURNAL.md`.

### Testing or verification performed

- Ran the complete automated suite: 138 tests passed.
- Reloaded the local Streamlit application in the Codex side browser.
- Confirmed the application title and intake screen render successfully.
- Visually inspected the refreshed desktop layout for readability, spacing, and contrast.

### Remaining work

- Configure the local OpenAI API secret.
- Review approval, budget-shortfall, stockout, and summary screens with real application state.
- Validate the responsive layout at a narrow viewport.

### Recommended next step

Configure the local API secret and run the supplied two-list scenario so every refreshed screen can be visually reviewed.

## 2026-07-26 — Animated school buddies

### Objective

Add cute animated school-child decorations to the sides of the application without interfering with the parent workflow.

### Work completed

- Added a book-carrying school child to the left margin.
- Added a backpack-carrying school child to the right margin.
- Added gentle floating and waving CSS animations.
- Kept both decorations outside the main content area and disabled pointer interaction.
- Hid the decorations on narrower screens where the margins are not large enough.
- Disabled animation automatically for users who prefer reduced motion.

### Decisions made

- Use native emoji artwork and CSS animation so no image files or dependencies are required.
- Treat the characters as decorative content and hide them from assistive technology.
- Preserve all application copy, workflow, and business logic.

### Problems or limitations

- Emoji artwork can vary slightly across operating systems and browsers.
- The decorations intentionally disappear below a 1,240-pixel viewport width.

### Files created or changed

- Updated `app.py`.
- Updated `JOURNAL.md`.

### Testing or verification performed

- Ran the complete automated suite: 138 tests passed.
- Reloaded and visually inspected the application in the Codex side browser.
- Confirmed both characters render in the outer margins.
- Confirmed both decorations ignore pointer input and do not cover application controls.

### Remaining work

- Review the decorations alongside the approval and summary screens during a full session.

### Recommended next step

Configure the local API key and run a full two-list scenario through every screen.

## 2026-07-26 — Brighter color refresh

### Objective

Make the Ready, Set, School interface more colorful while preserving readability, accessibility, and the existing workflow.

### Work completed

- Increased the saturation and contrast of the blue, coral, yellow, mint, purple, and pink accent palette.
- Added soft yellow, pink, and mint background shapes over the notebook-paper treatment.
- Gave section headings a subtle yellow highlight.
- Added lightly tinted gradients to cards, forms, metrics, inputs, and secondary buttons.
- Updated primary buttons to use a clear blue-to-purple-to-coral gradient.
- Aligned the Streamlit theme colors with the brighter application palette.

### Decisions made

- Keep the background colors translucent so the interface remains calm and text stays easy to read.
- Preserve the existing dark text color and white or near-white control surfaces for contrast.
- Make visual-only changes; do not alter application logic, copy, data, or workflow.

### Problems or limitations

- The visual review covered the initial intake screen. Later workflow screens should be checked during a complete API-backed session.
- Pytest reported a cache-write warning because the current environment could not update `.pytest_cache`; the tests themselves all passed.

### Files created or changed

- Updated `app.py`.
- Updated `.streamlit/config.toml`.
- Updated `JOURNAL.md`.

### Testing performed

- Ran the complete automated suite: 138 tests passed.
- Reloaded the local Streamlit application.
- Visually verified the refreshed background, heading, notice, progress bar, form, inputs, and decorative characters.

### Remaining work

- Review approval, budget-shortfall, stockout, and summary screens during a full session.
- Validate the refreshed palette at a narrow viewport.

### Recommended next step

Run the supplied two-list scenario with a local API key and review every workflow screen for color consistency.

## 2026-07-26 — Develop the capstone project skill

### Objective

Expand the capstone project skill into a reliable, reusable workflow for reviewing, building, testing, demonstrating, and documenting the application.

### Work completed

- Rewrote the skill description so it triggers for status reviews, requirements work, implementation, debugging, Streamlit changes, deterministic cart logic, model-assisted tasks, security controls, testing, demos, and journal updates.
- Added context-loading and task-routing instructions.
- Added explicit architecture, security, approval, testing, UI-verification, and closeout gates.
- Added UI metadata for the skill list and invocation prompt.
- Validated the completed skill with the official skill-creator validator.

### Decisions made

- Keep the skill concise and point to `BRD.md`, `PROJECT.md`, and `JOURNAL.md` instead of duplicating their detailed content.
- Treat status review, diagnosis, implementation, interface work, demo preparation, and documentation as distinct task modes.
- Encode the project's graded architecture and safety requirements directly in the workflow because they apply across implementation tasks.

### Problems or limitations

- The official generator and validator required PyYAML, which is not part of the application environment.
- PyYAML was installed only into a disposable validation folder outside the application dependency set.
- No multi-agent forward test was run.

### Files created or changed

- Updated `.agents/skills/capstone-project/SKILL.md`.
- Created `.agents/skills/capstone-project/agents/openai.yaml`.
- Updated `JOURNAL.md`.

### Testing performed

- Ran the official `quick_validate.py` validator.
- Result: `Skill is valid!`
- Confirmed the generated `agents/openai.yaml` contains the intended display name, short description, and default prompt.

### Remaining work

- Exercise the revised skill on the next real status-review or implementation request.
- Refine task-routing language if real use reveals ambiguity or unnecessary steps.

### Recommended next step

Invoke `$capstone-project-workflow` for a fresh project status review and confirm that it reports evidence, gaps, risks, and the next milestone without modifying files.

## 2026-07-26 — Add the intake and plan-building workflow to the skill

### Objective

Make the user-defined supply-list intake, human-review, plan-building, and final-approval workflow a reusable part of the capstone skill.

### Work completed

- Added a dedicated skill reference for the complete intake-to-approval workflow.
- Defined the four required visible application stages.
- Documented supported input formats, readable-content validation, and unsupported-format rejection.
- Documented the structured supply-item schema and deterministic numeric validation rule.
- Added list-cleaning rules, human-review controls, plan inputs, and required plan outputs.
- Updated the main skill to require reading the workflow reference for relevant work.

### Decisions made

- Store the detailed workflow in a one-level `references/` file to keep the main skill concise.
- Treat the user's explicit `.docx` requirement as an approved scope update.
- Retain existing BRD-required PDF support unless the user explicitly removes it.
- Preserve the mandatory review stage even when extraction confidence is high.

### Problems or limitations

- The skill requirements are now documented, but this task did not implement or verify missing application features.
- Current application behavior still requires a separate gap analysis against the new workflow.

### Files created or changed

- Updated `.agents/skills/capstone-project/SKILL.md`.
- Created `.agents/skills/capstone-project/references/intake-plan-workflow.md`.
- Updated `JOURNAL.md`.

### Testing performed

- Ran the official skill validator.
- Result: `Skill is valid!`
- Confirmed the main skill is 79 lines and the workflow reference is 126 lines.

### Remaining work

- Compare the current application against every workflow requirement.
- Add missing `.docx` extraction, schema fields, review controls, plan inputs, outputs, and stage behavior in BRD-aligned increments.
- Add automated and end-to-end tests for each implemented gap.

### Recommended next step

Run a read-only workflow gap analysis before changing application code.

## 2026-07-26 — Implement supply-list intake and organized review

### Objective

Implement the approved DOCX, image, text, and manual-list intake workflow with a mandatory editable review stage, confirmed-only planning, and a stable offline demonstration path.

### Work completed

- Added DOCX upload validation and extraction of paragraphs, bullet paragraphs, and table cells.
- Retained PDF, JPG, JPEG, PNG, TXT, and manual text support.
- Added an editable `SupplyItemReview` schema that preserves source text, confidence, issue flags, confirmation state, already-owned state, optional status, brand requirements, and equivalent-product permission.
- Added deterministic sorting, review-issue detection, unresolved-required-item blocking, and conversion back to cart-ready requirements.
- Added a mandatory `Review extracted items` screen with editable rows and dynamic row creation.
- Changed the initial action from `Build my plan` to `Organize my list`.
- Added an explicit organized-list confirmation gate.
- Added a confirmed-extraction pipeline entry point so matching and optimization receive only reviewed items.
- Added four visible workflow stages: upload and organize, review extracted items, build the shopping plan, and approve the final plan.
- Added stable offline demo mode with deterministic sample extraction, structured catalog matching, the seeded fictional catalog, and no OpenAI or retailer request.
- Added repeatable TXT, DOCX, PNG, and JPEG test fixtures.
- Updated the BRD, project scope, and runbook.

### Decisions made

- Keep the editable review contract separate from the frozen cart-ready `Requirement` schema.
- Permit missing quantities in the review layer, but require resolution or explicit user approval before planning.
- Exclude deleted and already-owned items from plan generation.
- Retain PDF support while adding DOCX.
- Use `python-docx` for reliable paragraph, bullet, and table extraction.
- Keep arbitrary image interpretation on the image-capable model path; offline demo mode uses deterministic text/document samples.
- Keep all package, quantity, tax, fee, budget, and optimization arithmetic deterministic.

### Problems or limitations

- Arbitrary JPG, JPEG, and PNG interpretation still requires the configured model in normal mode.
- Offline demo mode intentionally rejects arbitrary images instead of pretending to read them.
- The Streamlit data editor exposes issue flags as evidence; users resolve them by editing and explicitly confirming the row or approving remaining uncertainty.
- Pytest reports a cache-write warning because this environment cannot update `.pytest_cache`; the tests themselves pass.

### Files created or changed

- Updated `app.py`.
- Updated `agent/extract.py`.
- Updated `agent/pipeline.py`.
- Updated `agent/schema.py`.
- Created `agent/review.py`.
- Created `agent/demo.py`.
- Updated `requirements.txt`.
- Updated `tests/test_app.py`.
- Updated `tests/test_extract.py`.
- Updated `tests/test_pipeline.py`.
- Created `tests/test_review.py`.
- Created `tests/test_demo.py`.
- Created `tests/conftest.py`.
- Updated `BRD.md`.
- Updated `PROJECT.md`.
- Updated `RUNBOOK.md`.
- Updated `JOURNAL.md`.

### Testing performed

- Ran focused intake, review, demo, application, and pipeline tests: 43 passed.
- Ran the complete automated suite after implementation: 149 passed.
- Ran the complete automated suite again after end-to-end corrections: 149 passed.
- Exercised offline demo mode in a fresh local Streamlit process.
- Verified Stage 1 list intake, Stage 2 mandatory review, Stage 4 approval, and the final plan summary.
- Confirmed the deterministic demo produced a non-empty $58.41 landed-cost plan from the seeded catalog.

### Remaining work

- Run a normal API-backed image extraction through the complete review workflow.
- Add a real classroom-approved DOCX and representative photographed list to the evaluation set.
- Review the editable table at a narrow viewport.
- Consider a bundled image demo fixture if an offline image demonstration becomes a presentation requirement.

### Recommended next step

Run one API-backed JPG or PNG list through all four stages, then perform a narrow-screen accessibility review.
