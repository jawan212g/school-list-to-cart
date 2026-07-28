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

## 2026-07-27 — Add layout-preserving district PDF intake

### Objective

Replace interleaved PDF text extraction with vision-based page rendering, add
parent-confirmed document-section selection, preserve real-list structure and source
evidence, and expand the catalog for three real district reference PDFs without
changing matching, approval-gate, or optimizer logic.

### Work completed

- Added `pypdfium2` and changed PDF intake to render every page as a PNG for document
  structure detection.
- Kept PDF text extraction only as a logged fallback when page rendering fails.
- Added a PDFium render lock after concurrent real-PDF verification exposed a Windows
  ARM64 page-loading failure; model calls remain concurrent.
- Added schema-validated document structure, section, and parent selection contracts
  for grades, teachers, named sections, page numbers, matrix columns, languages, and
  translated duplicates.
- Added a document-section selection screen before item extraction. A single
  unambiguous grade skips the picker; every selected and ignored section is named.
- Limited item extraction to the rendered page numbers selected by the parent.
- Added structured fields for individual/shared scope, school-provided items,
  conditional applicability, source section/page/language, uninterpreted lines, and
  deliberately skipped lines.
- Added parent review controls for conditional applicability, supply scope, and
  school-provided items.
- Added deterministic duplicate suppression before quantity aggregation.
- Added visible source-line interpretation, read/ignored sections, school-provided
  items, uninterpreted content, and deliberately skipped content to the summary and
  text export.
- Added explicit summary copy separating model-based list reading from deterministic
  quantity, package, price, tax, fee, and total calculations.
- Expanded the seeded catalog from 120 to 162 unique offers and from 25 to 35
  categories, including play dough, modeling compound, watercolor paints, dry-erase
  markers, permanent markers, sticky notes, baby wipes, water bottles, pencil
  sharpeners, and pencil pouches.
- Added 1.5-inch and 2-inch binders, 5-tab subject dividers, plastic folders, and
  block/cap/kneaded eraser choices while preserving the seeded non-monotonic pricing
  cases.
- Changed the default OpenAI text/vision model from `gpt-5.6-sol` to
  `gpt-5.4-mini` after the former completed structure detection but timed out twice
  on a selected one-page structured extraction under the required 30-second call
  limit.
- Added the three real district PDFs as reference fixtures and model-free tests that
  verify page rendering and selected-page scoping.

### Decisions made

- Structure detection sees the whole document; item extraction sees only the
  parent-selected pages plus the exact selected grade/column/named-section metadata.
- Translated copies remain visible in detected structure but are not selectable when
  marked as duplicates.
- Global school-provided boxes are attached to each affected grade and preserved as
  display-only items rather than cart requirements.
- Matrix source evidence joins the exact row label and exact selected cell so the
  parent can verify both item and quantity at a glance.
- Model-reported duplicate rows are suppressed deterministically and named as skipped.
- No silent fallback from a configured text-only Kelley provider to OpenAI vision was
  added. PDF/JPG/PNG intake fails early with a clear message when no vision model is
  configured, preserving the prior provider rule.

### Problems or limitations

- Model reading remains variable. In the final Machias Grade 4 verification,
  `gpt-5.4-mini` extracted the gallon A-G and sandwich Q-Z conditional bag rows, but
  incorrectly named the quart H-P row as a blank skipped line. The skipped exact row
  is visible in review/summary so it is not silent, but this run did not extract all
  three branches.
- The active Kelley settings still have no vision model. Real PDF/image intake
  therefore requires using the OpenAI configuration or configuring a verified
  vision-capable provider model.
- OpenAI latency varied materially: selected-page extraction ranged from about 16 to
  59 seconds. The prior `gpt-5.6-sol` default exceeded the timeout; the new mini model
  completed the reference runs but one run used most of the retry window.
- Streamlit is intentionally not installed on this Windows ARM64 machine, so the
  interface was not launched locally. UI structure was verified by import and pytest
  only, per the environment constraint.

### Files created or changed

- Updated `README.md`, `requirements.txt`, `app.py`, `agent/provider.py`,
  `agent/extract.py`, `agent/schema.py`, `agent/review.py`, `agent/rules.py`,
  `agent/demo.py`, and `data/catalog.json`.
- Updated focused application, approval-display, catalog, extraction, normalization,
  and review tests.
- Created `tests/test_real_pdf_intake.py`.
- Added the three district PDFs under `tests/sample_lists/`.
- Updated `JOURNAL.md`.

### Testing performed

- Focused PDF/extraction/review/catalog/application/provider tests: 119 passed.
- Complete automated suite: 194 passed in 2.55 seconds.
- Live OpenAI vision structure verification:
  - Machias: grade matrix plus Highly Capable section; selected Fourth Grade on page
    2 and named every ignored grade/section.
  - New School: Kindergarten through Fifth Grade matrix; selected Fourth Grade with
    Individual Supplies, Shared Supplies, and Optional named sections.
  - Milford checklist: 10 English primary grade sections and 20 Haitian Creole/
    Spanish translated duplicates; Grade 5 includes the global District will be
    supplying section.
- Live selected-grade extraction:
  - Machias Fourth Grade: 22 requirements, exact selected-cell evidence, two
    low-confidence review items, two extracted last-name conditions, and six named
    skipped rows including the missed quart-bag condition.
  - New School Fourth Grade: 21 requirements with separate individual, shared, and
    optional scopes.
  - Milford Grade 5: nine parent-purchased requirements plus four school-provided
    items excluded from cart scope.

### Remaining work

- Perform a deployed Streamlit walkthrough with a working vision configuration.
- Decide whether the missed Machias quart-bag condition warrants a second
  model-reading strategy or a parent-facing "add skipped line" shortcut.
- Measure a two-PDF end-to-end build in the deployed environment with the selected
  default model.

### Recommended next step

Deploy with OpenAI vision enabled, run the three PDFs through the parent review screen,
and confirm the section picker, exact source lines, conditional choices, and
school-provided display at presentation width.

## 2026-07-27 — Restore full vision model and group conditional branches

### Objective

Restore the higher-capability OpenAI extraction model with a realistic rendered-page
timeout, and make mutually exclusive last-name supply branches one required parent
choice rather than multiple cart requirements.

### Work completed

- Restored the default OpenAI text and vision model from `gpt-5.4-mini` to the prior
  `gpt-5.6-sol` value.
- Added a 120-second timeout used only for model calls containing rendered page or
  image content. Text extraction and semantic matching retain the existing 30-second
  request ceiling.
- Added condition-group fields to the validated requirement and review schemas.
- Tightened the vision prompt to inspect every adjacent last-name bag row and to
  treat gallon A-G, quart H-P, and sandwich Q-Z as mutually exclusive branches.
- Added deterministic grouping for extracted last-name ranges so all branches share
  one parent-facing question.
- Replaced per-row condition choices for grouped items with one review question:
  “This list assigns bags by last name. Which applies?”
- Added deterministic enforcement that exactly one grouped branch must be selected.
  The unresolved-item override cannot allow zero or multiple branches into cart
  scope.
- Preserved unselected branches as visible, non-purchasable source evidence.

### Decisions made

- Chose the full 120-second end of the requested 90–120 second range because rendered
  structured vision extraction legitimately exceeded 30 seconds on two reference
  pages.
- Kept the general model-client timeout at 30 seconds and applied the longer ceiling
  per request only when input contains an image.
- Kept conditional interpretation in extraction/review and did not change matching,
  approval-gate, optimizer, package, tax, fee, or budget calculations.

### Problems or limitations

- The timing measurements cover document structure detection and selected-grade item
  extraction. They exclude the time a parent spends choosing a section and do not
  predict network variability in the deployed environment.
- The New School full-model run returned two optional lines as uninterpreted rather
  than guessing. They remain visible for parent review.
- Streamlit remains unavailable on this Windows ARM64 machine, so the new review
  control was verified through pure app helpers and pytest rather than a local
  browser launch.

### Files created or changed

- Updated `agent/provider.py`, `agent/rules.py`, `agent/extract.py`,
  `agent/schema.py`, `agent/review.py`, and `app.py`.
- Updated `tests/test_provider.py`, `tests/test_extract.py`,
  `tests/test_review.py`, and `tests/test_app.py`.
- Updated `JOURNAL.md`.

### Testing performed

- Focused provider, extraction, review, and application tests: 73 passed.
- Complete suite after the implementation: 200 passed in 2.50 seconds.
- Live OpenAI `gpt-5.6-sol` selected-grade extraction:
  - Machias Grade 4: 66.03 seconds; all A-G, H-P, and Q-Z bag branches read.
  - New School Grade 4: 56.34 seconds.
  - Milford Grade 5: 29.24 seconds.
- Live structure detection:
  - Machias: 7.08 seconds; eight selectable sections.
  - New School: 10.24 seconds; six selectable grade sections.
  - Milford: 23.90 seconds; ten primary sections and twenty translated duplicates.
- Combined model-processing time by document:
  - Machias: 73.11 seconds.
  - New School: 66.58 seconds.
  - Milford: 53.14 seconds.

### Remaining work

- Confirm the grouped radio control visually in the deployed Streamlit interface.
- Recheck deployed latency during the five-minute presentation rehearsal because
  hosted network and provider load can vary.

### Recommended next step

Run the Machias Grade 4 flow in the deployed app, select each last-name option once,
and confirm that the summary always shows one purchased bag branch and two
condition-not-applicable source lines.

## 2026-07-27 — Simplify the document section picker

### Objective

Reduce the document-section screen to the least information a parent needs to choose
the applicable grade or teacher, and reliably preselect the section matching the
grade already entered at intake.

### Work completed

- Removed the section-table Status column.
- Removed placeholder text from empty section metadata; blank values now remain
  blank.
- Made section metadata columns conditional. Teacher, named-part, page, and grade
  columns appear only when populated and useful for distinguishing choices.
- Suppressed the table entirely when it would contain only section names; the
  section multiselect becomes the simple list of choices.
- Limited the Language column to documents with more than one detected language.
- Marked translated duplicates in the Language column with the primary section they
  repeat and kept those duplicates out of the selectable choices.
- Expanded grade matching to recognize numeric, ordinal, and word forms such as
  `2`, `2nd Grade`, and `Second Grade`.
- Seeded the keyed Streamlit multiselect in session state so Streamlit cannot ignore
  the grade-matched default after a rerun.
- Added a visible explanation naming the preselected section, the entered grade that
  caused the choice, and that the parent may change it.
- Preserved parent changes instead of reapplying the default on later reruns.

### Decisions made

- Use no evidence table when section names alone answer the question.
- Keep a compact table only when teacher, named-part, differing page, grade, or
  multilingual context materially helps distinguish sections.
- Keep translated copies visible as context but non-selectable so quantities cannot
  be duplicated.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so the visual layout was
  verified through pure display helpers, import/compile checks, and pytest rather
  than a local browser launch.

### Files created or changed

- Updated `app.py`.
- Updated `tests/test_app.py`.
- Updated `JOURNAL.md`.

### Testing performed

- Focused application tests: 28 passed.
- Complete suite: 203 passed in 2.65 seconds.
- Python compilation completed without errors.
- Git diff validation reported only the existing Windows line-ending notice.

### Remaining work

- Confirm the compact table and grade-preselection message at presentation width in
  the deployed Streamlit application.

### Recommended next step

Open each real district PDF in the deployed app and verify that Machias and New
School show a simple grade choice while Milford shows only the multilingual context
needed to explain its hidden translated copies.

## 2026-07-28 — Rebuild the extracted-item review

### Objective

Replace the wide technical extraction grid with a parent-facing comparison of exact
source text and plain-language interpretation while preserving mandatory review,
secondary editing, real-PDF evidence, and multi-child behavior.

### Work completed

- Replaced the primary `data_editor` review path with compact rows ordered as
  “What the list said,” “What we understood,” and “Confirm.”
- Kept the exact original source line at the front of every purchase row.
- Added plain interpretations such as “24 Ticonderoga pencils, brand required.”
- Moved item, quantity, unit, package size, brand, equivalent-brand permission,
  attributes, optional status, individual/shared scope, already-owned, parent note,
  and delete controls into a collapsed per-row “More detail” expander.
- Removed internal identifiers and raw confidence decimals from the visible review.
- Added `clear`, `worth checking`, and `uncertain` confidence bands while retaining
  numeric confidence internally for BR-11.
- Accepted clear rows through the single page submit action; only ambiguous or
  low-confidence rows require an explicit checkbox.
- Added concrete uncertainty explanations for quantity ranges, missing package
  counts, missing quantities, and low-confidence readings.
- Deduplicated identical uncertainty confirmations across children and labelled the
  shared row with every affected child label.
- Deduplicated identical conditional questions across children and expanded one
  parent answer back to every affected source requirement.
- Grouped purchase rows by the parent-entered child label with flagged rows first.
- Moved non-purchasable directions into one collapsed “Notes from the teacher”
  section, deduplicated across children.
- Moved district-provided supplies into a separate collapsed section and kept them
  excluded from cart scope.
- Preserved selected and ignored document sections, uninterpreted content, skipped
  content, conditional choices, exact source evidence, and individual/shared scope.
- Added an “Add a missing item” secondary form for each child.
- Added a shared district-document intake option. One upload now creates a separate
  child-scoped list input for each entry, with one section choice per child.
- Reused document structure detection for identical shared uploads so the same PDF
  is inspected once rather than once per child.
- Preserved quantity-range metadata through the editable review boundary.

### Decisions made

- Keep conditional questions above purchase rows because they determine which
  mutually exclusive rows can enter cart scope.
- Anchor a cross-child ambiguity once under the first affected child and mark every
  affected label rather than asking the same question twice.
- State explicitly that product matching has not run on the extraction-review
  screen; unmatched products are named later when matching exists.
- Require per-ambiguity confirmation rather than retaining the former global
  unresolved-item bypass.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so the final visual
  layout could not be opened locally. The UI path was verified through pure
  presentation helpers, source-structure tests, compilation, and pytest.
- Shared-document intake currently applies one document to all entries in the
  session. Selecting an arbitrary subset of children for one shared document remains
  a possible refinement.

### Files created or changed

- Updated `agent/schema.py`, `agent/review.py`, `agent/rules.py`, and `app.py`.
- Updated `tests/test_review.py` and `tests/test_app.py`.
- Updated `JOURNAL.md`.

### Testing performed

- Focused review and application tests: 48 passed.
- Complete automated suite: 215 passed in 4.63 seconds.
- Python compilation completed without errors.
- Git diff validation reported only Windows line-ending notices.

### Remaining work

- Review the new compact row layout in the deployed Streamlit application at desktop
  and narrow presentation widths.
- Run one two-child district-PDF session to confirm the upload-once and per-child
  section-selection wording with live model output.

### Recommended next step

Deploy this branch, open the shared Machias document for Grade 2 and Grade 5, and
verify that one upload produces two grade choices, one deduplicated bag question when
applicable, and compact source-versus-understanding rows without horizontal scrolling.

## 2026-07-28 — Redesign the parent intake

### Objective

Make the first screen readable and self-explanatory for a parent while preserving
the existing extraction, matching, approval, and deterministic calculation paths.

### Work completed

- Replaced the single long intake form with three guided setup steps: students,
  budget, and shopping preferences.
- Added a short, dismissible first-arrival walkthrough explaining the four stages
  from setup through the final shopping plan.
- Replaced parent-facing “Child,” “Entry,” “Label,” and “Shopping mode” wording with
  student-centered plain language across intake, list organization, document-section
  selection, item review, summary attribution, text export, and displayed decision
  rationales.
- Added immediate name, grade, budget, store-selection, and tax-rate validation beside
  the relevant field. Step navigation remains unavailable while the visible step has
  an error.
- Moved the stable offline demo control into the existing development-only area. The
  control is available only through `?debug=1` or the development environment flag;
  normal intake explicitly disables demo mode.
- Added a state dropdown with state-level general tax-rate defaults and an editable
  override. The existing 7.0% BR-02 default remains when no state is selected.
- Kept pickup radius, pickup-or-delivery preference, the simulated store-distance
  table, state selection, and tax override in one advanced-options expander.
- Replaced the low-contrast illustrated background and gradients with a plain
  near-white background, dark text, white content cards, and solid notebook blue,
  pencil yellow, chalkboard green, and crayon red accents.
- Updated the Streamlit theme and README terminology to match the parent interface.

### Decisions made

- Used state-level general rates dated January 1, 2026 and stated the date in the
  interface. City and county rates remain deliberately unmodeled.
- Preserved all internal `child_id` and `children` field names so the UI redesign
  does not alter pipeline contracts or calculations.
- Kept the walkthrough non-blocking: parents can begin the form without dismissing
  it and can hide it for the rest of the in-memory session.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so the redesign could
  not be opened locally. Structure, copy, import safety, and state helpers were
  verified through pytest and Python compilation.
- State defaults do not include local rates or determine whether a particular school
  supply is exempt. The interface states this next to the tax controls.

### Files created or changed

- Updated `app.py`, `.streamlit/config.toml`, `README.md`, and
  `tests/test_app.py`.
- Updated `JOURNAL.md`.

### Testing performed

- Focused application tests: 38 passed.
- Complete automated suite: 220 passed in 5.52 seconds.
- Python compilation completed without errors.
- Git diff validation reported only Windows line-ending notices.

### Remaining work

- Visually confirm the three-step intake, advanced-options expander, and narrow-screen
  spacing in the deployed Streamlit application.
- Recheck the state-rate defaults before a future school year because state tax rates
  can change.

### Recommended next step

Deploy the branch and walk through one single-student and one two-student setup at
desktop and phone widths, paying particular attention to the immediate validation
placement and the state-to-tax-rate prefill.

## 2026-07-28 — Unify the landing journey and visual identity

### Objective

Remove the competing numbering and repeated purpose copy from the landing screen,
restore a readable school-notebook identity, and make grade entry bounded without
changing extraction, matching, approval, or calculation behavior.

### Work completed

- Made the four-stage journey the only numbered sequence: set up students and budget,
  add supply lists, review what was read, then approve decisions and get the plan.
- Removed step numbers from the Students, Budget, and Shopping preferences sections
  and aligned every screen's visible stage label with the canonical journey.
- Consolidated the landing explanation into one dismissible introduction with one
  purpose sentence and the four-stage journey.
- Replaced the old tagline with “Sorted before the first bell.”
- Reduced the persistent limitation copy to one visible line and moved the complete
  explanation into a “How this works and what is simulated” expander. The tax
  limitation remains beside the tax controls.
- Rendered Ready, Set, and School in separate crayon red, notebook blue, and
  chalkboard green title colors on every screen.
- Restored ruled-notebook decoration behind a solid opaque application card, and
  applied opaque cards, stronger accents, high-contrast text, consistent spacing,
  and responsive narrow-screen rules across the whole application.
- Replaced free-form grade entry with Pre-K, Kindergarten, Grades 1–12, and Classroom
  group choices. Selecting Classroom group continues to expose student count.
- Updated the Streamlit theme, README tagline, and application tests.

### Decisions made

- Kept all four journey labels in one constant so the introduction and progress
  display cannot drift independently.
- Mapped document-section selection to Add supply lists, extracted-item review to
  Review what we read, and cart building, approvals, and summary to the final stage.
- Kept the ruled-paper treatment outside the opaque main content surface so decorative
  lines never sit behind body text.
- Preserved internal grade and student identifiers where they are pipeline contracts;
  only the parent-facing controls and copy changed.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so an actual browser
  rendering at desktop and phone widths could not be inspected locally. Responsive
  rules, copy, structure, imports, and state behavior were verified through source
  tests and Python compilation.

### Files created or changed

- Updated `app.py`, `.streamlit/config.toml`, `README.md`,
  `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 39 passed.
- Complete automated suite: 221 passed in 2.65 seconds.
- Python compilation completed without errors.
- Git diff validation reported no content errors; only expected Windows line-ending
  notices were shown.

### Remaining work

- Confirm the final visual rhythm in the deployed Streamlit application at desktop
  and phone widths.

### Recommended next step

Deploy the branch and check the Students, Budget, and Shopping preferences sections
at both widths, including one Classroom group selection and one full journey through
the final plan.

## 2026-07-28 — Compact the intake and repair classroom grade capture

### Objective

Move the first student form above the fold, remove repeated navigation and explanation
content, and ensure classroom groups retain the grade needed for district-list section
selection.

### Work completed

- Replaced the progress bar, stage caption, and large journey overview with one compact
  horizontal stepper used on every screen.
- Renamed the journey to Your students, Their lists, Check our work, and Your plan.
- Combined purpose, workflow, simulated-data details, calculation transparency, and
  privacy information into one collapsed “How Ready, Set, School works” expander.
- Reframed privacy as a benefit and moved name guidance into the field placeholder.
- Separated “Who this covers” from Grade. A classroom group now records both its
  actual grade and its student count.
- Added a regression test proving a Grade 3 classroom preselects the Grade 3 section
  of a district-wide document.
- Removed repeated Students, Budget, and Shopping preferences headings beneath the
  intake section labels.
- Removed the intake-section progress bar, tightened page and card spacing, used wider
  multi-column field layouts, and added explicit borders and focus styles to every
  text, number, select, multiselect, and text-area control.
- Kept the four-stage stepper horizontal at phone width while allowing form field
  columns to stack for readability.

### Decisions made

- Kept the three intake section names as a compact local orientation row, without
  numbering or another progress bar.
- Migrated a hot-reloaded legacy Classroom group grade value into the classroom type
  control and requires the parent to choose the real grade.
- Kept the full simulation explanation accessible on every screen, but collapsed by
  default so it does not block the task.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so above-the-fold placement
  and the input border could not be inspected in a live browser. The reduction in
  rendered elements, responsive CSS, state conversion, and HTML output were verified
  through automated tests and Python compilation.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 39 passed.
- Complete automated suite: 221 passed in 5.21 seconds.
- Python compilation completed without errors.

### Remaining work

- Confirm the compact stepper, first student row, and control borders in the deployed
  Streamlit application at laptop and phone widths.

### Recommended next step

Deploy the branch and verify that the first student fields are visible without
scrolling on a normal laptop, then select a Grade 3 classroom group and confirm its
district-list section is preselected.

## 2026-07-28 — Personalize intake wording, flow, and motion

### Objective

Frame list review as parent-controlled cart personalization, reveal only fields that
apply to the selected entry type, defer validation until navigation, and restore
lightweight motion without changing pipeline or calculation behavior.

### Work completed

- Renamed the four stages to Your students, Their lists, Personalize, and Your
  shopping plan everywhere they appear.
- Reframed the organized-list screen around choosing what enters the cart. The primary
  columns are now From the list, For your cart, and Choose, while original source
  evidence and confirmation controls remain intact.
- Replaced the collapsed explainer with the exact requested purpose, How it works,
  What's real and what isn't, and Your privacy copy.
- Changed student intake to ask Student or Classroom first with no default selection.
  Student reveals name or nickname and grade; Classroom reveals teacher name, grade,
  and number of students.
- Kept separate temporary student-name and teacher-name widget values so switching
  type does not carry an irrelevant name into the other form.
- Removed the introductory student instruction and retained the example only as the
  name-field placeholder.
- Changed student, budget, and preference validation to appear only after the parent
  tries to continue. Navigation buttons remain available so the validation can occur
  on exit.
- Strengthened first-render input borders with an explicit input-parent border and
  inset edge, plus hover and focus treatment.
- Added quick card, field, step, button, and focus transitions; all motion is reduced
  to effectively zero when the browser requests reduced motion.
- Added a short, nonblocking ready-state animation only for a complete, within-budget
  warm plan.

### Decisions made

- Preserved the mandatory FR-12 source evidence and human confirmation while changing
  the screen's framing from auditing the model to personalizing the cart.
- Kept incomplete, shortfall, and error states free of celebration.
- Implemented motion in CSS only, avoiding timers or state changes that could delay
  the five-minute demonstration path.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so first-render border
  appearance and animation timing could not be observed in a live browser. DOM
  selectors, output copy, state paths, reduced-motion handling, and complete-plan
  conditions were verified through automated tests and Python compilation.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 40 passed.
- Complete automated suite: 222 passed in 5.32 seconds.
- Python compilation completed without errors.

### Remaining work

- Confirm the first-render text-input border, type reveal, transition speed, and
  ready-state moment in the deployed Streamlit application.

### Recommended next step

Deploy the branch and test one Student and one Classroom entry, including switching
between the types once, leaving a required field blank, and completing an in-budget
plan with reduced-motion both enabled and disabled.

## 2026-07-28 — Complete intake fixes and add no-budget planning

### Objective

Clarify student and classroom intake, repair per-entry classroom budgets, and add an
explicit no-budget path without changing extraction, matching, or optimizer
calculations.

### Work completed

- Reworded the entry-count question and shortened the student-name placeholder to
  Maya.
- Added separate display counters, so mixed intake entries read Student 1,
  Classroom 1, Student 2, and Classroom 2. Stable internal record IDs remain unique
  and independent of those display labels.
- Moved Continue actions to the right side of their intake cards and enforced white
  text for every primary button, including nested Streamlit label elements.
- Renamed the classroom-size field and added an information tooltip explaining that
  list quantities are multiplied by the classroom count.
- Changed per-entry budget copy and coverage so both student and classroom records
  receive an allocation.
- Added the non-default No set budget option. It passes `None` as the deterministic
  budget ceiling, so the existing optimizer still minimizes landed cost while budget
  interrupts and shortfall comparisons remain absent.
- Reconciled BR-05 for sessions without a budget: donation add-ons are offered after
  required coverage is complete because there is no 90% threshold to evaluate. Their
  exact added landed cost is still calculated through the normal optimization path.
- Updated the summary and text export to identify a no-budget plan without implying
  that a budget constraint was satisfied.

### Decisions made

- Kept Student and Classroom numbering strictly presentational. Internal IDs remain
  the existing globally unique `child-1`, `child-2` sequence so list ownership and
  decision references do not collide.
- Preserved every non-budget approval condition when no budget is selected.
- Recorded the requested no-budget donation behavior as a named BR-05 reconciliation
  rather than weakening the existing 90% rule for budgeted sessions.

### Problems or limitations

- BRD BR-05 describes only budgeted sessions; the no-budget behavior requested in
  chat is an explicit specification extension and should be added to the BRD later.
- Streamlit is unavailable on this Windows ARM64 machine, so right alignment, tooltip
  placement, and button contrast were verified structurally rather than in a live
  browser.

### Files created or changed

- Updated `app.py`, `agent/addons.py`, `agent/pipeline.py`, `agent/rules.py`,
  `tests/test_app.py`, `tests/test_addons.py`, `tests/test_gate.py`, and
  `JOURNAL.md`.

### Testing performed

- Focused intake, add-on, and gate suites: 61 passed.
- Complete automated suite: 229 passed in 2.61 seconds.
- Python compilation completed without errors.
- Git whitespace validation completed without errors; only the repository's existing
  LF-to-CRLF conversion warnings were reported.

### Remaining work

- Confirm the mixed Student/Classroom display counters, classroom help tooltip,
  primary-button contrast, and no-budget donation panel in deployed Streamlit.

### Recommended next step

Run one deployed no-budget session with a student and a classroom, confirm both
receive their own per-entry budget field when that mode is selected, then return to
no-budget mode and verify the summary shows exact landed cost without a budget
comparison.
