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

## 2026-07-28 — Reset removed entries and repair mixed-entry budgets

### Objective

Prevent positional Streamlit widget values from reappearing after entry removal or
crossing between Student and Classroom types, and prove that every mixed entry
receives a budget field and retains its allocation through cart review.

### Work completed

- Added deterministic intake-state cleanup for every removed entry slot, including
  its type, names, grade, classroom multiplier, budget, list widgets, and document
  section selection.
- Added a previous-type marker for each active slot. Switching between Student and
  Classroom now clears both name variants, the shared grade, classroom count, budget,
  and list values before the new type's fields render.
- Changed a missing stored label to remain empty instead of becoming a synthetic
  Student-number label, so an increased count always creates a genuinely blank entry.
- Made budget rendering and budget parsing share one unfiltered list of field
  specifications derived from every intake entry.
- Rendered per-entry budget fields in a simple vertical sequence rather than routing
  them through separate columns.
- Shortened the third budget option to `No set budget`.
- Added tests covering reduce-then-increase, both type-switch directions, two rendered
  budget widgets for a Student and Classroom, app-to-pipeline allocation transfer,
  proportional per-entry cost attribution, and the resulting aggregate budget
  interrupt.

### Decisions made

- Kept stable internal child IDs unchanged; only values associated with a removed or
  repurposed position are cleared.
- Preserved the current BRD behavior in which per-entry allocations sum to the
  deterministic session ceiling. Per-entry rebalance prompts remain the deferred
  E-22 feature.
- Changed no optimizer, matching, extraction, or approval-gate implementation.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so live widget lifecycle
  behavior could not be observed locally. The actual rendering function was executed
  through a Streamlit-shaped test double instead of relying only on source inspection
  or allocation parsing.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, `tests/test_pipeline.py`, and `JOURNAL.md`.

### Testing performed

- Focused intake, pipeline, gate, and optimizer suites: 90 passed.
- Complete automated suite: 234 passed in 2.65 seconds.
- Python compilation completed without errors.
- Git whitespace validation completed without errors; only the repository's existing
  LF-to-CRLF conversion warnings were reported.

### Remaining work

- Confirm in deployed Streamlit that lowering and restoring the count produces a
  blank slot, both type-switch directions clear immediately, and two mixed entries
  display two budget fields.

### Recommended next step

Repeat the reported Jesse reproduction in the deployed app, then enter one Student
and one Classroom, assign distinct budgets, and verify both budget variances appear
in the final per-entry summary.

## 2026-07-28 — Preserve form values across backward navigation

### Objective

Make every backward navigation action reviewable and reversible without weakening
the intentional clearing behavior for removed entries or Student/Classroom type
changes.

### Work completed

- Added a durable navigation snapshot for Student, Budget, Shopping preferences,
  pasted-list, document-section, and extracted-item review widgets.
- Restored saved widget values before Streamlit initializes defaults, preventing
  hidden controls from being reset when the parent returns to an earlier screen.
- Preserved list source choices and pasted text across setup, lists, working, and
  review screens.
- Added an in-memory uploaded-file draft so a selected file remains usable after
  navigating away. The file widget itself is not programmatically repopulated; the
  retained filename is shown and the stored bytes remain available to list intake.
- Kept deliberate deletion authoritative by removing both the live widget value and
  its navigation snapshot when an entry count decreases.
- Kept type changes authoritative by removing both live and saved values belonging
  to the previous Student or Classroom form.
- Preserved unsaved extracted-item review controls through their existing stable
  review keys when the parent returns to the lists screen.

### Decisions made

- Used non-widget shadow values because Streamlit automatically cleans widget keys
  when their widgets disappear on another screen.
- Stored uploaded-file bytes separately rather than assigning a value back into a
  browser file-upload control.
- Made no changes to extraction, matching, optimization, calculations, or the
  approval gate.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so the browser-level widget
  cleanup cycle could not be observed live. Tests simulate that cleanup by removing
  hidden widget keys and then exercising the same restore path called by `main`.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`. The previously modified
  `tests/test_pipeline.py` remains part of the same uncommitted intake-fix block.

### Testing performed

- Focused application and pipeline suites: 60 passed.
- Complete automated suite: 237 passed in 3.60 seconds.
- Python compilation completed without errors.
- Git whitespace validation completed without errors; only the repository's existing
  LF-to-CRLF conversion warnings were reported.

### Remaining work

- Confirm in deployed Streamlit that Student, Budget, Shopping preferences, pasted
  lists, uploaded-list drafts, section choices, and review edits all remain visible
  after moving backward and forward.

### Recommended next step

Run the deployed sequence Students → Budget → Students → Budget → Shopping
preferences → Budget, then continue to Lists and Review and use each Back action once
before completing the plan.

## 2026-07-28 - Standardize navigation button sizing

### Objective

Make paired Back and Continue actions the same size throughout the application,
including the oversized Continue to shopping preferences button.

### Work completed

- Replaced the unequal one-third/two-thirds navigation layouts with one shared
  equal-width column helper.
- Made both actions fill their matching columns on the Budget, Shopping preferences,
  Lists, section selection, extracted-item review, and Summary screens.
- Kept the first Students screen's single Continue action aligned to the same
  right-hand half-width position.
- Added a regression test covering the equal column specification and its use by
  every screen with a paired navigation row.

### Decisions made

- Standardized paired actions structurally in Python rather than imposing a global
  CSS width that could distort unrelated buttons such as approval choices, downloads,
  and donation controls.
- Made no changes to extraction, matching, optimization, calculations, or the
  approval gate.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so the final visual
  proportions were verified structurally rather than in a live browser.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 52 passed.
- Complete automated suite: 238 passed in 2.77 seconds.
- Python compilation completed without errors.
- Git whitespace validation completed without errors; only the repository's existing
  LF-to-CRLF conversion warnings were reported.

### Remaining work

- Confirm in deployed Streamlit that Back and Continue buttons have matching widths
  at desktop and phone sizes.

### Recommended next step

Open the Budget and Shopping preferences screens in the deployed app and confirm the
navigation row is balanced at both desktop and phone widths.

## 2026-07-28 - Harden intake state and delivery-only preferences

### Objective

Clear all Student/Classroom values on a type switch, preserve values through every
backward navigation path, simplify intake guidance, and make pickup radius respond
clearly to delivery-only shopping.

### Work completed

- Gave Student and Classroom grade selectors separate widget identities while
  retaining the existing canonical grade value used by the rest of the application.
- Extended type-change cleanup to remove both grade widget values and their saved
  navigation snapshots.
- Added explicit intake-step and backward-screen navigation helpers that snapshot
  the current form values immediately before navigation.
- Applied the navigation helper across Students, Budget, Shopping preferences,
  Lists, section selection, extracted-item review, working-screen recovery, and
  Summary return paths.
- Replaced the combined-budget helper with: "Enter the total you want to spend, for
  example 75 or 85.50."
- Simplified the remaining Budget and Shopping preferences captions and tooltips.
- Kept pickup radius at a 10-mile initial default, disabled it for delivery-only
  shopping, displayed "Not needed for delivery.", and restored 10 miles when pickup
  or best-available fulfillment is selected again.
- Extended tests for grade cleanup, the complete forward-and-back intake sequence,
  the 10-mile default, delivery-only disabling, and reset behavior.

### Decisions made

- Used type-specific grade widget keys because clearing a shared Streamlit widget key
  did not prevent the browser from restoring the previous selection.
- Disabled the pickup radius without changing its stored value while delivery-only
  is active; the value resets only when pickup becomes relevant again.
- Made no changes to extraction, matching, optimization, calculations, or the
  approval gate.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so the disabled styling and
  browser widget lifecycle were verified through state tests and source structure,
  not a live local rendering.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 53 passed.
- Complete automated suite: 239 passed in 2.67 seconds.
- Python compilation completed without errors.
- Git whitespace validation completed without errors; only the repository's existing
  LF-to-CRLF conversion warnings were reported.

### Remaining work

- Confirm in the deployed app that a Student/Classroom switch visibly blanks both
  name and grade, and that delivery-only greys out the radius control.

### Recommended next step

Repeat the live forward-and-back intake sequence, then toggle Delivery only to Pickup
only and confirm the radius returns to 10 miles.

## 2026-07-28 - Add safe banner navigation and narrow edit cascades

### Objective

Turn both progress banners into navigation controls for completed work while
preserving every entered value and clearing only downstream state made invalid by an
actual edit.

### Work completed

- Replaced the static four-stage indicator with four equal banner buttons.
- Made completed stages clickable, highlighted the current stage, and kept unreached
  stages disabled with a distinct visual treatment.
- Added the same completed/current/unavailable behavior to Students, Budget, and
  Shopping preferences within intake.
- Preserved the existing Back and Continue buttons without changing their wording or
  behavior.
- Added guarded stage-navigation helpers that snapshot widget values before every
  jump and reject attempts to open an unreached stage.
- Tracked the furthest valid stage and intake section, including reducing access when
  an edit invalidates later work.
- Scoped entry removal by child ID: the removed entry's allocation, list, document
  structure, section choice, extraction state, and review rows are removed while
  other entries remain untouched.
- Preserved the combined budget when an entry is removed.
- Cleared only the edited entry's document section choice when its grade changes;
  uploaded list data and other entries' choices remain.
- Cleared only the fields belonging to the budget mode being left.
- Added plain, immediate notices for removed allocations, lists, section choices,
  type-change details, and budget-mode fields.
- Added visual styling for current, completed, and unavailable banner controls.

### Decisions made

- Treated "completed" as reached and still valid. A downstream stage becomes
  unavailable when an upstream edit invalidates it, but its unaffected source data
  remains in session state.
- Used stable child IDs for every narrow cascade so one entry cannot clear another
  entry's data.
- Kept navigation and invalidation in `app.py`; no model, matching, gate, optimizer,
  or money-calculation behavior changed.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so clickable and disabled
  banner behavior was exercised with Streamlit-shaped test doubles rather than a
  live local browser.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 57 passed.
- Complete automated suite: 243 passed in 2.61 seconds.
- Python compilation completed without errors.
- Git whitespace validation completed without errors; only the repository's existing
  LF-to-CRLF conversion warnings were reported.

### Remaining work

- Confirm in the deployed app that completed banner buttons are visually obvious,
  unreached buttons look unavailable, and notices appear beside the edit that caused
  each narrow cascade.

### Recommended next step

Run one deployed session through Summary, use the four-stage banner to jump to
Students, then verify one-click return to each still-valid completed stage before
testing a grade change and entry removal.

## 2026-07-28 - Restore banner choices and refine budget and shopping setup

### Objective

Make completed intake sections reliably revisitable, make budget-mode switching
reversible and exact, and clarify the shopping-preference controls without changing
the cart pipeline or business calculations.

### Work completed

- Removed unfinished-stage circles from both banners while retaining completion
  checkmarks.
- Made navigation snapshots section-aware so hidden widget defaults cannot overwrite
  saved Students, Budget, or Shopping preferences values during a banner jump.
- Restored the saved widgets for a completed section before rendering it, including
  per-entry budget fields and advanced shopping settings.
- Verified that a parent can complete intake, jump back through the banner, and still
  continue to Their lists.
- Kept both budget-mode drafts while the parent switches between them and clears only
  the unused mode after Continue.
- Seeded per-entry budgets from a combined budget with exact-cent remainder handling,
  and seeded an empty combined budget from the exact sum of per-entry allocations.
- Suppressed clearing notices when no value was actually removed.
- Accepted an optional leading dollar sign and correctly grouped thousands commas;
  rejected pound, euro, yen, and cent symbols with a US-dollar message.
- Ensured Shopping preferences starts with a 10-mile pickup radius and a populated
  state-rate tax value.
- Added plain-language help for shopping mode, store selection, maximum stores,
  fulfillment, pickup radius, state, and the optional tax override.

### Decisions made

- Reused the deterministic proportional-cent allocator already used for BR-09 so
  budget seeds sum exactly with no float arithmetic.
- Treated alternative budget-mode figures as editable drafts until the parent leaves
  Budget; switching the radio alone is not a commitment.
- Kept all state and display work in `app.py`. Extraction, matching, approval-gate,
  and cart-calculation behavior were not changed.

### Problems or limitations

- Streamlit is unavailable on this Windows ARM64 machine, so the interactive banner
  and widget behavior was verified with Streamlit-shaped test doubles rather than a
  local browser.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.

### Testing performed

- Focused application suite: 63 passed.
- Complete automated suite: 249 passed in 4.89 seconds.

### Remaining work

- Confirm the restored field values, help icons, and banner styling in the deployed
  Streamlit app at desktop and phone widths.

### Recommended next step

In the deployed app, enter a combined budget with an odd-cent split, switch between
budget modes twice, jump to Students through the banner, then return to Shopping
preferences and continue to Their lists.

## 2026-07-28 - Bind intake values outside the Streamlit widget lifecycle

### Objective

Correct intake state that passed dictionary-based tests but was lost when real
Streamlit widgets were conditionally unmounted and remounted.

### Work completed

- Reviewed Streamlit's documented widget cleanup behavior: a keyed widget that is
  not rendered loses its widget key and returns as a new widget when remounted.
- Replaced direct intake widget keys with Streamlit's recommended two-key pattern:
  one temporary widget key and one durable application key copied through an
  `on_change` callback.
- Applied the durable binding to every prefilled intake control: entry count and
  type, names, grades, classroom count, both budget modes, shopping mode, custom
  stores and store count, fulfillment, radius, state, and tax.
- Preserved combined and per-entry budget drafts across conditional unmounting while
  the parent remains on Budget.
- Preserved advanced Shopping preferences across section-banner navigation.
- Committed untouched displayed defaults to durable state before Continue can read
  them.
- Limited the type-change notice to cases where a name, grade, changed classroom
  count, budget, or list value was actually discarded.
- Hid Streamlit's automatic heading-anchor action globally.
- Reclassified the prior Streamlit-shaped banner test as a display-boundary unit
  test rather than lifecycle evidence.
- Added a separate `st.testing.v1.AppTest` suite that drives the real application
  through widget reruns, cleanup, and remounting.

### Decisions made

- Used the documented temporary-widget/durable-value pattern instead of relying on
  copied widget keys or a Streamlit-version-specific persistence parameter.
- Kept the existing navigation snapshots as a compatibility layer, but made durable
  values the source of truth for intake.
- Did not change `requirements.txt`; the deployed environment already installs
  Streamlit, while the supported local ARM64 environment intentionally does not.

### Problems or limitations

- The real Streamlit lifecycle tests are collected but skipped on this Windows
  ARM64 machine because Streamlit is not installed. They must run in the deployed
  x86 environment before the interactive behavior can be called verified.
- No deployed URL is recorded in the repository, so this session could not perform
  a browser check against the hosted application.

### Files created or changed

- Updated `app.py`, `tests/test_app.py`, and `JOURNAL.md`.
- Added `tests/test_streamlit_lifecycle.py`.

### Testing performed

- Focused application and lifecycle selection: 65 passed, 1 skipped.
- Complete local suite: 251 passed, 1 skipped in 5.44 seconds.
- Python compilation and Git whitespace validation completed without errors.

### Remaining work

- Run `tests/test_streamlit_lifecycle.py` in an x86 environment with Streamlit
  installed and confirm all four integration tests pass.
- Repeat the reported interactions in the deployed app after the updated code is
  deployed.

### Recommended next step

Run `python -m pytest -q tests/test_streamlit_lifecycle.py` in the deployment or CI
environment, then manually confirm one Budget mode round-trip and one advanced
preferences banner round-trip in the hosted app.

## 2026-07-28 - Resolve document sections deterministically

### Objective

Replace the district-document section spreadsheet with a rule-driven statement of
what will be read, while retaining one-click source evidence and explicit handling
for genuinely unresolved sections.

### Work completed

- Added BR-14 through BR-18 for matching-grade selection, other-grade exclusion,
  translated-copy provenance, ungraded parent questions, and the zero-match stop.
- Added BR-19 so non-paginated list evidence consistently uses page 1.
- Added a pure section-resolution layer that consumes the production Pydantic
  structure envelope and returns one choice object used by both display and submit.
- Removed label and column-text guessing from grade resolution. Only the extractor's
  explicit grade tokens can cause automatic selection.
- Kept translated copies out of parent controls and attached them to their
  source-language originals as provenance.
- Added an explicit mismatch outcome naming the student, document, and covered
  grades, with paths to select manually, upload another document, or return to setup.
- Carried trusted document names, page numbers, and exact source lines through list
  input, extraction, and review models.
- Added one-click rendered-page previews for document sections, unresolved section
  questions, and extracted item source lines.
- Fixed the demo structure label so a stored value such as `Grade 1` is not prefixed
  a second time.
- Added production-shape unit tests plus a real Streamlit `AppTest` for the Ms. K
  state/explanation mismatch. The AppTest remains locally skipped by platform policy.
- Added a non-English injection case proving that translated document text cannot
  change section resolution and that an out-of-domain injected item is rejected.

### Decisions made

- Diagnosed the Ms. K defect as two sources of truth: a retained multiselect widget
  and a separately computed caption. The replacement fingerprints widget state to
  the actual document and grade, then derives the statement and submission from one
  `ResolvedSectionChoice`.
- Required the structure model to return only source facts (`primary_language` and
  `source_line`); all section decisions remain deterministic.
- Moved page-number indexing to a model-free document-page utility so
  `agent/extract.py` contains no quantity, money, or page arithmetic.
- Did not add translation, review redesign, approval changes, or calculation changes.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so the new production
  `AppTest` is collected but cannot execute locally.
- The requested live OpenAI Maple regression attempt timed out for both list
  extractions. The resulting empty plan was correctly treated as extraction failure
  and is not a valid replacement for the recorded $111.21 and $71.07 baselines.

### Files created or changed

- Added `agent/document_pages.py`, `agent/sections.py`, and
  `tests/test_sections.py`.
- Updated `agent/extract.py`, `agent/pipeline.py`, `agent/review.py`,
  `agent/rules.py`, `agent/schema.py`, `app.py`, `tests/test_app.py`,
  `tests/test_extract.py`, and `tests/test_streamlit_lifecycle.py`.

### Testing performed

- Focused section, extraction, application, review, and pipeline suite:
  124 passed.
- Complete local suite: 259 passed, 1 skipped.
- Real PDF source preview verified against page 3 of the Machias reference PDF.
- Live OpenAI regression attempt: both list reads timed out; no comparable cart.

### Remaining work

- Run `tests/test_streamlit_lifecycle.py` in the deployed x86 Streamlit environment.
- Re-run the $150 and $85 OpenAI Maple baselines when the endpoint is reachable.

### Recommended next step

Deploy the Part A screen, run the Ms. K Grade 1/Highly Capable scenario once, and
then repeat the two Maple baseline runs while OpenAI connectivity is healthy.

## 2026-07-28 - Consolidate repeated section requirements

### Objective

Correct same-student duplicates across selected document sections or separate lists,
and make every section-resolution explanation derive from the parent's live choice.

### Work completed

- Diagnosed the pre-fix requirement path as concatenation: extracted requirements
  were appended before normalization, and aggregation then summed matching rows.
- Added a deterministic same-student merge keyed by the normalized identity already
  used for aggregation.
- Made agreeing quantities count once, while disagreeing quantities produce one
  parent question with total-all as the default, a source-specific choice for every
  contributing line, and a custom quantity.
- Added source provenance to production Requirement and SupplyItemReview objects and
  retained it across review confirmation, pipeline execution, and replanning.
- Allowed separate list inputs for one student and merged their extraction envelopes
  before normalization.
- Corrected BR-18 so an explicit section selection resolves the document; a mismatched
  selection is an inline warning identifying it as the parent's choice.
- Routed whole-document grade context through DocumentStructureEnvelope rather than
  the selected extraction pages.
- Recomputed the other-grade exclusion count from ResolvedSectionChoice.
- Deduplicated section source links by document and page, and identified the old
  duplicate as two display paths rather than a double cart resolution.
- Added per-section rule-versus-parent attribution, named multilingual repetitions in
  plain language, and kept the no-grade checkbox enabled with its exact line and page.

### Decisions made

- Added BR-20 through BR-22 without renumbering existing rules.
- Kept quantity consolidation and conflict resolution entirely model-free.
- Put the quantity-conflict question in the list-resolution stage before Personalize,
  leaving the Personalize, approval, setup, matching, gate, and optimizer behavior
  unchanged.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 environment. The new AppTest is
  collected but skipped locally and must execute in the deployed x86 environment.
- The required OpenAI Maple regression attempt timed out for both lists again, so its
  zero-dollar failure object is not a valid baseline.
- A same-extraction Kelley run completed, but provider reading drift produced a
  $75.94 cart at both $150 and $85, four visible interrupt groups, and no $85 budget
  plan. The merge reported zero duplicate conflicts, so this difference from the
  historical $111.21/$71.07 OpenAI baseline was not caused by requirement merging.
- The full configured Kelley path, including production model-assisted matching,
  produced a $108.31 landed cart with four interrupts at $150. Reusing that same
  extraction at $85 produced a $69.19 recommended plan and five interrupts. Neither
  run contained a requirement-merge interrupt.

### Files created or changed

- Added `agent/requirement_merge.py` and `tests/test_requirement_merge.py`.
- Updated `agent/aggregate.py`, `agent/extract.py`, `agent/pipeline.py`, `agent/review.py`,
  `agent/rules.py`, `agent/schema.py`, `agent/sections.py`, `app.py`,
  `tests/test_app.py`, `tests/test_pipeline.py`, `tests/test_sections.py`, and
  `tests/test_streamlit_lifecycle.py`.

### Testing performed

- Focused requirement, section, pipeline, app, and AppTest selection: 92 passed,
  1 skipped.
- Kelley shared-extraction regression: $75.94 at both budget settings, four visible
  interrupt groups, zero merge interrupts.
- Kelley production matching: $108.31 landed and four interrupts at $150; $69.19
  recommended budget plan and five interrupts at $85.
- OpenAI regression: both extraction requests timed out; no comparable cart produced.

### Remaining work

- Execute the Streamlit AppTest in the deployed environment.
- Re-run the historical OpenAI Maple baselines when the endpoint responds within the
  configured timeout.

### Recommended next step

Deploy this list-resolution block, verify the mixed Grade 5 plus Highly Capable
selection once, then repeat the OpenAI Maple baseline from one shared extraction.

## 2026-07-28 - Stabilize assumptions and reconcile merged constraints

### Objective

Make package assumptions reproducible, merge same-item requirements despite
non-identity descriptors, and remove split section/brand/quantity state from the
lists workflow.

### Work completed

- Added deterministic package-count recovery and assumptions keyed by canonical
  item; unsupported model-supplied counts are discarded and flagged for review.
- Made exact-brand locks depend on explicit source wording. Bare brand mentions and
  preference language now leave equivalent brands available.
- Narrowed same-student merge identity to the canonical item context, reconciled
  compatible constraints, and emitted one source-backed parent choice for genuinely
  incompatible constraints.
- Routed the section override multiselect through `ResolvedSectionChoice`, made the
  review brand choice mutually exclusive, displayed every consolidated source, and
  made custom or named-source quantity choices change the merged requirement.
- Normalized grade display text and exposed retained list filename, page count, and
  student assignment on the lists screen.

### Decisions made

- Added BR-23 through BR-26 without renumbering prior rules.
- Kept model correction at the schema boundary and all quantity/constraint
  reconciliation deterministic and model-free.
- Preserved size, material, and acceptable-color fields because matching uses them;
  the optimizer does not inspect them directly.

### Problems or limitations

- The configured Kelley GPT API was nondeterministic across two consecutive
  regression attempts: the first produced 33 requirements and a $104.69 cart; the
  paired baseline produced 31 requirements and a $90.31 cart. This prevents
  attributing the full historical baseline change to this code block.
- Streamlit remains intentionally unavailable on Windows ARM64, so the production
  AppTest module is skipped locally and must run in the deployed x86 environment.

### Testing performed

- `py -3.12-arm64 -m pytest -q`: 276 passed, 1 skipped.
- Kelley GPT API (`gpt-oss-20b`) paired regression: $90.31 landed and four
  interrupts at $150; using the exact same extraction at $85 produced an $83.72
  recommended plan and six interrupts. No requirement-merge interrupt appeared.

### Remaining work

- Run the Streamlit AppTest module in the deployed x86 environment.
- Re-run the paired Maple comparison with a stable captured extraction if a strict
  before/after attribution is required.

### Recommended next step

Deploy Part A-3 and verify the Grade 5 plus Highly Capable section override, merged
source display, and custom quantity control once in the live Streamlit interface.

## 2026-07-28 - Scope merges and organize Personalize by student

### Objective

Keep deliberately enumerated same-section items additive, combine every open
same-item question into one decision, and make the Lists and Personalize screens
compact and student-centered.

### Work completed

- Added document-section origin to deterministic requirement merge scope. Repeated
  same-item rows within one section stay separate; cross-section or cross-document
  restatements can consolidate.
- Grouped quantity and detail conflicts into one item decision and allowed zero-or-
  greater quantities per source-backed variant, retaining the source-requested
  quantities as defaults.
- Replaced generic missing-detail validation with item names and a link to the first
  affected card.
- Grouped Personalize content by student with one document/section/page summary,
  collapsed excluded content, and per-item sources only for uncertainty,
  consolidation, assumptions, or deterministic reconciliation.
- Hid size, material, and acceptable-color editors unless the source supplied the
  field or available catalog offers differ on the mapped matching attribute.
- Removed matrix annotations at the display edge, preserved exact provenance,
  removed “Included by default,” formatted canonical item names, and corrected
  quantity pluralization.

### Decisions made

- Added BR-27 through BR-29 without renumbering existing rules.
- Used the same catalog attribute aliases as matching for detail visibility; direct
  JSON-key coverage alone would incorrectly treat catalog color as absent.
- Kept shared conditional questions and teacher notes deduplicated, anchoring each
  under the first affected student's section.

### Problems or limitations

- Streamlit remains intentionally unavailable on Windows ARM64, so the real AppTest
  module is skipped locally and must execute in the deployed x86 environment.
- Kelley remained nondeterministic. The $85 suitability pass produced a higher
  baseline cart than the $150 pass even though it reused the same extractions, so
  the regression movement cannot be attributed solely to BR-27.
- Direct catalog coverage is sparse: size 14/162, material 22/162, and
  acceptable_colors 0/162. Matching-effective alias coverage is 35/162, 22/162,
  and 50/162 respectively.

### Files created or changed

- Updated `agent/requirement_merge.py`, `agent/review.py`, `agent/rules.py`,
  `agent/schema.py`, `app.py`, `tests/test_app.py`,
  `tests/test_requirement_merge.py`, and `tests/test_sections.py`.

### Testing performed

- `py -3.12-arm64 -m pytest -q`: 287 passed, 1 skipped.
- Verified cross-section consolidation for backpack, scissors, composition
  notebooks, and folders; verified two same-section Sharpie variants remain two
  additive requirements.
- Kelley GPT API (`gpt-oss-20b`): $94.81 landed and five interrupts at $150.
  Reusing the extraction at $85 produced a $110.04 baseline cart and a $71.47
  recommended plan with four interrupts.

### Remaining work

- Run the Streamlit AppTest module and visually inspect Lists and Personalize in the
  deployed x86 environment.
- Use a captured extraction and candidate map for any future strict cart-regression
  attribution; live provider calls do not isolate merge behavior.

### Recommended next step

Deploy Part A-4 and verify the mixed-section Sharpie example, per-variant quantity
controls, student summaries, and collapsed excluded-content panel in one live pass.

## 2026-07-28 - Correct quantity semantics and simplify item verification

### Objective

Make cross-section quantities reflect restated needs rather than automatic addition,
preserve source-backed variants and provenance, and reorganize Lists/Personalize item
cards around the facts a parent needs to verify.

### Work completed

- Changed the deterministic cross-section/document conflict default from the sum to
  the largest requested quantity, while retaining sum, named-source, and custom
  choices.
- Added synchronized quick choices and editable quantity fields for both plain
  quantity conflicts and source-backed variants.
- Preserved every contributing source on resolved variants while keeping each
  variant's own detail source and quantity; prevented review-question deduplication
  from overwriting distinct variant attributes.
- Reordered each Personalize item card to show the interpreted item, exact source
  evidence, one factual decision line, the cart-use control, and collapsed details.
- Removed the confidence tag, made owned items visibly quantity zero and cart
  ineligible, and made an exact brand impossible without a populated brand.
- Retained preferred brands as non-locking hints and removed duplicated preference
  prose from other required details.
- Separated ignored sections, uninterpreted lines, deliberately unused content, and
  understood items absent from the catalog; preserved source links for actionable
  gaps.

### Decisions made

- Added BR-30 without renumbering earlier rules: cross-section/document restatements
  default to the largest requested quantity, and summing is parent-selected.
- Kept Supply use and Units in one package in this block pending the requested
  follow-up decision; neither control was removed.
- Did not alter matching, gate, approval, setup, optimizer arithmetic, or money
  handling.

### Problems or limitations

- Streamlit is intentionally unavailable on this Windows ARM64 environment, so the
  Lists and Personalize screens could not be visually exercised locally. The
  Streamlit-only AppTest remains skipped.
- Kelley model output remains nondeterministic across runs. The paired A-5 run reused
  one extraction for both budgets to isolate the budget comparison, but its $150
  result is not directly comparable to A-4 as a code-only delta.
- The Personalize screen can identify a missing stocked category without running
  matching. Attribute-, brand-, radius-, or fulfillment-specific infeasibility is
  still determined later by the unchanged matching and approval flow.

### Files created or changed

- Updated `agent/extract.py`, `agent/pipeline.py`,
  `agent/requirement_merge.py`, `agent/review.py`, `agent/rules.py`,
  `agent/schema.py`, and `app.py`.
- Updated `tests/test_app.py`, `tests/test_extract.py`, and
  `tests/test_requirement_merge.py`.

### Testing performed

- `py -3.12-arm64 -m pytest -q`: 295 passed, 1 skipped.
- Kelley GPT API (`gpt-oss-20b`) shared extraction: 25.28 seconds.
- The $150 plan landed at $109.83 with three visible interrupts.
- Reusing the same extraction at $85 produced a $109.83 base plan and a $71.47
  recommended plan with four visible interrupts.
- Maple quantities remained separate by student and constraint: Grade 2 had 24
  exact-brand pencils and four large glue sticks; Grade 5 had 36 generic pencils
  and six unconstrained glue sticks.

### Remaining work

- Visually verify the conflict controls and item-card spacing in deployed Streamlit.
- Decide in the next scoped revision whether to remove or relabel Supply use and
  Units in one package after reviewing their current behavior.

### Recommended next step

Deploy Part A-5 and exercise one cross-section quantity conflict, one two-variant
composition-notebook conflict, an owned item, and an out-of-catalog item before
starting the next Personalize revision.

## 2026-07-29 — Part A-6 product identity and Personalize revision

### What changed

- Added BR-31 through BR-35 for product-defining attributes, ambiguous
  descriptors, classroom shared-item scaling, the per-item package preference
  default, and explicit package-quantity states.
- Captured graph, quad, lined, plain, wide-ruled, college-ruled, point style,
  format, and binding evidence in the validated production Requirement.
- Split requirement conflicts into quantity-only, different-product, and
  ambiguous decisions. Product variants now retain a production variant identity
  through review, aggregation, matching, selected-SKU consolidation, and cart lines.
- Rebuilt the conflict cards around a source table and type-appropriate controls.
- Made inferred package counts visible and editable, removed the per-item Supply
  use control, exposed exact-brand choice whenever a brand is present, and added
  a per-item package fulfillment preference without changing optimizer code.
- Added live acknowledgment counts, approve-all-defaults, student-scoped repeatable
  missing-item entry, and narrower source link-outs.
- Changed classroom aggregation so explicit shared supplies do not scale by
  classroom size; individual and unspecified supplies retain scaling.

### Diagnosis and limitations

- The prior two-cart-line test was not a production proof: it forced separate
  candidate SKUs. In the live path both composition variants could select the same
  wide-ruled SKU, after which selected-SKU consolidation recombined them. Product
  variant identity now prevents that recombination.
- Supply scope still comes from model interpretation of explicit headings. It is
  not reliable enough to infer every real-world shared item; unspecified scope
  conservatively retains the existing individual scaling default.
- The new closest-quantity preference is preserved in production review and
  Requirement objects, but does not alter package arithmetic because Part A-6
  explicitly required `agent/optimize.py` to remain unchanged.
- Streamlit is unavailable on this Windows ARM64 machine, so the deployed visual
  layout still needs a browser review. The one Streamlit lifecycle suite remains
  skipped locally.

### Verification

- `py -3.12-arm64 -m pytest -q`: 311 passed, 1 skipped.
- Static architecture inspection: `agent/optimize.py` has no model calls;
  `agent/extract.py` has zero arithmetic binary operations.
- Kelley GPT API (`gpt-oss-20b`) live retry completed in 52.14 seconds after the
  first concurrent attempt timed out.
- The shared extraction produced no merge conflicts. At $150, landed cost was
  $110.04 with three interrupts. Reusing it at $85 kept the $110.04 base cart and
  produced a $76.97 recommended plan with four interrupts.
- These differ from A-5's $109.83 and $71.47, but the A-6 product-identity rules
  were not exercised by this Maple extraction. The change cannot honestly be
  attributed to code rather than Kelley extraction nondeterminism.

### Recommended next step

Visually exercise all three conflict-card types and the repeatable missing-item
flow in deployed Streamlit, then decide whether a later scoped change may update
optimizer package-selection behavior for the recorded closest-quantity preference.

## 2026-07-29 — Part A-7 source integrity and conflict-card revision

### Objective

Prevent quantity-only matrix cells from masquerading as exact source lines,
let the parent override same-item versus different-product classification on
every merge card, and keep concurrent list extraction from repeating successful
documents when another document fails.

### Work completed

- Added BR-36 through BR-38 for exact source evidence, parent-overridable
  product identity with rule-derived defaults, and failed-document-only
  sequential extraction fallback.
- Rejected purchasable requirements and provenance records whose purported
  exact source text is only a number. The existing schema-validation retry can
  correct that model defect; otherwise the list fails visibly instead of
  showing false evidence.
- Added one same-item/two-kinds control to every conflict card. Type A, Type B,
  and ambiguous classification now determines the default, while deterministic
  merge resolution honors the parent's override.
- Reworked quantity choices to lead with the amount, name section and page,
  mark exactly one source-backed default, and avoid a duplicate largest-value
  option.
- Added bordered source rows, a wider non-wrapping source control, and visible
  pending treatment for a custom quantity until the parent edits the field.
- Kept concurrent extraction and added a sequential retry only for each failed
  document in both the Lists workflow and the pipeline. Successful documents
  are never repeated.
- Changed the shared application tagline to “School supplies sorted before the
  first bell.”

### Decisions made

- The source-line defect was diagnosed as a data/provenance-boundary problem:
  the renderer used `RequirementSource.exact_line` correctly, but merge had
  received a quantity-only `Requirement.raw_text`.
- No PDF text-reading path or model prompt was added. The validated schema
  enforces honest evidence while retaining the existing model call and retry
  behavior.
- Product classification rules remain unchanged; BR-31 and BR-32 now determine
  only the initial same/different selection.

### Problems or limitations

- Streamlit is unavailable on Windows ARM64, so the card borders, control
  re-rendering, and source-button width still require deployed visual review.
- Kelley GPT API was unstable during live verification. Before the code change,
  both concurrent Maple extractions succeeded in 60.74 seconds. Afterward, both
  concurrent attempts and both targeted sequential fallbacks timed out, ending
  after 243.35 seconds with no complete extraction. A final sequential retry
  failed Grade 2 after 61.45 seconds while Grade 5 succeeded after 61.12 seconds
  with 16 requirements. Because no shared two-list extraction completed, no
  honest post-change $150 or $85 cart baseline could be produced.
- Static AST tools count Python union annotations (`A | B`) and one instruction
  string append as binary operations in `agent/extract.py`; inspection found no
  numeric, quantity, package, tax, fee, or money arithmetic there. No code was
  changed merely to appease that false-positive check.

### Files changed

- Updated `agent/rules.py`, `agent/schema.py`,
  `agent/requirement_merge.py`, `agent/pipeline.py`, `app.py`,
  `tests/test_app.py`, `tests/test_extract.py`, and
  `tests/test_requirement_merge.py`.

### Testing performed

- `py -3.12-arm64 -m pytest -q`: 317 passed, 1 skipped.
- Production-shaped tests cover full source-line retention, rejection of
  quantity-only evidence, all conflict identity defaults and overrides, custom
  quantity pending state, and failed-document-only extraction retry.
- Architecture inspection confirmed no model call in `agent/optimize.py` and no
  numeric calculation in `agent/extract.py`; neither file was modified.

### Remaining work

- Re-run both Maple baselines once Kelley can complete both documents in one
  shared extraction.
- Visually inspect the revised Lists conflict cards in deployed Streamlit.

### Recommended next step

Deploy Part A-7 for one conflict-card visual pass, then repeat the Maple
regression run when the Kelley endpoint is responsive enough to finish both
lists.

## 2026-07-29 — Part A-8 extraction timeout and conflict simplification

### Objective

Remove the extraction client timeout as the binding failure, separate selected
document sections from unresolved possibilities, and make same-student
quantity conflicts deterministic and easier for a parent to resolve.

### Work completed

- Added BR-39 through BR-42 for a 120-second text-extraction request ceiling,
  per-item plausible annual quantity maxima, bounded source-button labels, and
  display-only removal of a duplicated leading quantity.
- Kept the general matching timeout at 30 seconds; only extraction text now
  receives the same 120-second ceiling already used by rendered-page vision.
- Split the section card into “What we will extract” and “Other sections that
  might apply.” Selected sections name whether they matched the entered grade
  or were chosen by the parent; ungraded possibilities retain their checkbox
  and source evidence.
- Limited the main same-item/two-kinds question to BR-32 ambiguity. The rule
  classification stands for clear cases, with an override retained under item
  detail.
- Replaced the blanket largest-quantity default with a deterministic
  canonical-item table. Combined quantity is selected when it stays within the
  annual maximum; otherwise the largest source quantity is selected.
- Fixed quantity-choice ordering to combined, each named source, then custom,
  with exactly one marked preselection and a rule-generated rationale.
- Added “Do not add this item to the cart” to every conflict card and made
  deterministic consolidation omit that requirement without requiring a
  quantity choice.
- Preserved every exact source line while stripping a leading quantity only
  from the parent-facing description. Source filenames are truncated in the
  control and constrained by CSS.
- Removed the BR-34 number from the closest-package preference because the
  optimizer does not enforce it. The field remains recorded as deferred intent
  for a future optimizer-scoped revision.

### Verification

- `py -3.12-arm64 -m pytest -q`: 328 passed, 1 skipped.
- OpenAI (`gpt-5.6-sol`) extracted Grade 2 in 57.82 seconds and Grade 5 in
  63.32 seconds; concurrent wall-clock time was 63.33 seconds. Both completed.
- Reusing that OpenAI extraction, the $150 run landed at $110.04 with three
  interrupts. The $85 run had the same $110.04 required cart and a $78.67
  recommended plan with four interrupts.
- Kelley GPT API (`gpt-oss-20b`) extracted Grade 2 in 32.67 seconds and Grade 5
  in 33.47 seconds; concurrent wall-clock time was 33.47 seconds.
- Kelley model-assisted matching varied between the two budget runs: $95.07
  with five interrupts at $150, and a $94.81 base cart with an $81.13
  recommended plan and six interrupts at $85. Those figures are not a
  calculation-only comparison.
- Both provider runs reported zero requirement-merge interrupts for Maple
  because the repeated categories belong to different students. The movement
  from the historical $111.21 and $71.07 figures therefore was not caused by
  BR-40; it reflects current model extraction/matching output.
- Static inspection confirmed `agent/optimize.py` contains no model calls.
  `agent/extract.py` contains model-assisted reading and transport handling but
  no money, quantity, package, tax, fee, or cart arithmetic.

### Limitations

- Streamlit is intentionally unavailable on this Windows ARM64 environment.
  The Streamlit lifecycle test remains skipped, and the revised spacing and
  source-button truncation still need a deployed visual check.
- Live model output is nondeterministic. The OpenAI and Kelley figures above
  are actual paired runs, not stable golden values.

### Recommended next step

Deploy Part A-8 and visually verify one unchecked Highly Capable section, one
ambiguous composition-notebook conflict, and one source filename longer than
the column before expanding scope beyond Lists and Personalize.

## 2026-07-29 — Part A-9 identity state and deterministic rationale

### Objective

Make the Lists conflict card's rationale, identity selection, and quantity
controls agree; narrow identity questions to genuinely unresolved wording; and
keep source-backed product identity when a parent merges different products.

### Diagnosis before the fix

- `RequirementItemDecision.default_identity` was the authoritative
  deterministic classification.
- The rationale was generated from that fresh classification, but Streamlit
  could retain an older radio value under the same widget key. The quantity
  control then followed the stale radio, producing the contradictory folders
  card.
- When a parent merged different products, constraint reconciliation could
  keep the first conflicting value while also retaining a compatible attribute
  from another source. That could synthesize a folder description not present
  in either source.

### Work completed

- Added one fingerprinted resolved identity state consumed by the radio,
  rationale, and quantity-control renderer. Changed source facts reset stale
  widget state to the current deterministic default.
- Defined notebook “regular” as lined ruling and removed it from the explicit
  ambiguous-descriptor set, which is now empty.
- Limited the main identity question to residual description wording that
  remains different after quantities, filler, aliases, brand, exclusions, and
  resolved attributes are removed.
- Reframed identity controls around same versus different products, removed
  selection suffixes from option labels, and hid default rationale after an
  override.
- Centralized all new rationale copy as deterministic templates in
  `agent/rules.py`.
- Moved the exclusion checkbox beneath the source evidence and quantity
  controls.
- Widened the source column and exposed the full document and page in the
  source control's hover help while keeping BR-41's compact visible label.
- Changed a same-product override of rule-distinct products to retain the first
  complete source-backed variant, with all provenance preserved and a
  deterministic explanation carried into Personalize.

### Business rules

- Amended BR-32: “regular” means lined ruling for notebooks; the explicit
  ambiguous-descriptor set is empty.
- Amended BR-41: the 30-character source label retains full source text through
  hover help.
- Added BR-43: normalized-equivalent descriptions do not ask an identity
  question; unresolved residual wording asks once.
- Added BR-44: one resolved state drives identity presentation and quantity
  behavior; same-product overrides retain one complete source-backed variant.
- Added BR-45: rationale uses deterministic rule templates and disappears when
  the parent overrides the preselection.

### Verification

- Focused A-9 suite:
  `py -3.12-arm64 -m pytest -q tests/test_requirement_merge.py tests/test_app.py tests/test_extract.py`
  — 153 passed.
- Full suite: `py -3.12-arm64 -m pytest -q` — 332 passed, 1 skipped.
- OpenAI provider using `gpt-5.6-sol`: Grade 2 extracted in 58.53 seconds and
  Grade 5 in 59.19 seconds, with 59.19 seconds concurrent wall time.
- The $150 Maple run landed at $109.83 with three raw interrupts.
- The $85 Maple run had the same $109.83 required cart and a $69.24
  recommended plan with four raw interrupts.
- Both runs had zero requirement-merge interrupts. The difference from A-8's
  $110.04 and $78.67 figures is therefore not caused by A-9's deterministic
  merge changes; it reflects current nondeterministic model-assisted extraction
  and matching output. There is not enough retained prior model evidence to
  claim that either live cart is more correct.
- Static AST inspection found no model-like calls in `agent/optimize.py`.
  `agent/extract.py` had only type-union `BitOr` nodes and no arithmetic
  operations; neither architecture file was modified.

### Limitations

- Streamlit is unavailable in this Windows ARM64 environment, so source hover,
  column width, and final card spacing still need a deployed visual check.
- Live model-assisted baselines remain nondeterministic and should not be used
  as calculation-only golden tests.

### Recommended next step

Deploy Part A-9 and visually verify the folders, composition notebook, exclusion,
and long-filename source interactions before changing another screen.

## 2026-07-29 — Part A-10 source evidence and durable-item correction

### Objective

Repair the reversed-matrix source-line regression on Lists and Personalize,
prevent repeated durable goods from defaulting to summed quantities, and make
all decision rationale appropriately cautious and parent-facing.

### Diagnosis before the fix

- BR-36 was still active and passing because the stored source was not numeric
  only. Live extraction produced evidence such as
  `4 | Regular composition books`.
- BR-42 then displayed only the segment before `|`, turning that complete
  stored evidence into the visible value `4`. The stored provenance remained
  complete; the display boundary was wrong.
- The A-7 test used hand-authored `4 Regular composition books`, called the
  intermediate row builder, and never called the screen renderer with the
  reversed matrix shape. It therefore proved its fixture rather than the
  deployed path.
- The A-5 end-to-end SKU fixture still uses distinct invented SKUs and does not
  reproduce the real same-SKU variant case. A-6 added production protection
  through `product_variant_id`, but that exact same-SKU path remains a coverage
  gap.
- The A-9 state test uses a real merge decision but a plain dictionary and the
  resolver directly. It proves the deterministic helper, not Streamlit widget
  remount behavior. The true Streamlit lifecycle test remains skipped on this
  ARM64 environment.

### Work completed

- Added BR-46 through BR-50 without changing model prompts, matching, approval,
  setup, or optimizer behavior.
- Made source display and identity comparison choose the descriptive matrix
  segment regardless of whether quantity appears before or after `|`; complete
  source evidence remains unchanged.
- Replaced the A-7 regression test with one that creates production
  Requirements, consolidates them, invokes the actual conflict-row renderer,
  and records the values sent to the screen.
- Added a reusable single-instance category for backpacks, headphones, pencil
  boxes, pencil pouches, pencil sharpeners, rulers, scissors, and water
  bottles. Repeated mentions preselect the largest source quantity, including
  when quantities agree, while keeping the summed option available.
- Rewrote quantity and product-identity rationale to describe implications
  rather than assert teacher intent.
- Made unresolved identity questions inline and rule-resolved identity controls
  consistently collapsed with their rationale inside the same expander.
- Moved completed Lists decision explanations into Personalize's collapsed
  detail. The main item card retains only outcome, quantity, and source lines;
  unresolved extraction checks remain visible.
- Added one shared parent-facing attribute formatter and removed raw boolean
  output from reconciliation messages, product-difference summaries, and
  variant labels.
- Widened the Source column while retaining BR-41's complete hover reference.

### Decisions made

- BR-20 amended by BR-47: equal repeated single-instance goods remain one
  default requirement but expose the summed quantity for explicit parent
  selection.
- BR-45 amended by BR-48: rationale remains visible only for the current
  preselection and now uses hedged deterministic wording.
- Binders, dividers, and folders remain additive because one student can need
  several simultaneously by subject, even though the objects themselves are
  durable.
- Watercolor paints remain additive because paint is consumed, but this
  classification is less certain than the clearly reusable categories and
  should be revisited with real-list evidence rather than guessed into the
  single-instance set.

### Live verification

- OpenAI `gpt-5.6-sol` identified the Machias structure in 10.58 seconds and
  extracted the selected Grade 5 plus Highly Capable pages in 113.23 seconds.
- Live source evidence reproduced the failing shape, including
  `1 | Backpack or book bag`, `4 | Regular composition books`,
  `2 | Pocket folder w/ fasteners`, and `3 | Glue sticks`.
- After the fix, backpack, pencils, scissors, glue sticks, and tissues were
  rule-resolved as the same product; composition notebooks and folders were
  rule-resolved as different products. All used the collapsed resolved control;
  no live card required an inline unresolved identity question.
- A controlled paired Maple run reused one OpenAI extraction containing 16
  requirements per child. At $150 the plan landed at $109.83 with three
  interrupts. At $85 the base plan remained $109.83 with four interrupts and
  the recommended plan landed at $69.24. Both had zero requirement-merge
  interrupts and match the A-9 paired baseline.
- A separate provider pass returned $110.04 at $150, further demonstrating
  live extraction/matching nondeterminism; it was not used as the paired
  regression comparison.

### Files changed

- Updated `agent/rules.py`, `agent/requirement_merge.py`, `app.py`,
  `tests/test_app.py`, and `tests/test_requirement_merge.py`.

### Testing performed

- Focused Lists/Personalize suite: 184 passed.
- `py -3.12-arm64 -m pytest -q`: 345 passed, 1 skipped.
- Static AST inspection found no arithmetic operation in `agent/extract.py`
  and no model-call match in `agent/optimize.py`; neither file was modified.

### Problems or limitations

- Streamlit is unavailable on Windows ARM64. The actual renderer is now covered
  with production objects and an output recorder, but final browser spacing,
  expander placement, and hover width still require deployed visual review.
- The A-5 same-SKU fixture and A-9 widget-remount coverage gaps were reported,
  not expanded in this Lists/Personalize-only revision.
- Live model-assisted baselines remain nondeterministic.

### Recommended next step

Deploy Part A-10 and visually verify the Machias backpack, folders,
composition-notebook, scissors, and glue-stick cards plus one reconciled
sharpening note in Personalize.

## 2026-07-29 — Part A-11 Personalize structure and conflict-card polish

### Objective

Restructure Personalize around one student summary, remove repeated source and
section mechanics, make every exclusion visibly zero its quantity, and disclose
the prototype's unsourced quantity limits without changing matching, approval,
or cart calculations.

### Work completed

- Raised rendered-page vision extraction from 120 to 180 seconds under BR-51.
- Added one deterministic per-student Personalize state used by both the top
  summary and each student's counts and decision-first item section. Each row
  includes an anchor and a student-scoped default-approval control; the global
  default approval remains.
- Removed the ignored-section expander from Personalize and changed Lists and
  Personalize scope wording from "read" to "extracted."
- Kept compact source lines on every item, moved resolved and routine source
  controls into More detail, and retained a main source control only for
  assumptions or uncertain extraction.
- Diagnosed duplicate Scotch Tape as repeated catalog-unavailable metadata, not
  purchasable requirements surviving merge. Deduplicated that display by
  document, page, and exact source line and removed the repeated item-name
  prefix.
- Amended BR-45 so an equal-quantity named-source alternative keeps the
  preselection rationale.
- Made conflict exclusion, already-owned, and incorrect-item removal update the
  visible quantity to zero. Reversing a Personalize exclusion restores the
  last positive quantity.
- Reworded package preference around whether extras are acceptable and hid it
  for backpacks, headphones, pencil boxes, pencil pouches, pencil sharpeners,
  rulers, scissors, and water bottles.
- Reworded all quantity-default rationales as app behavior. Non-durable
  rationales with a numeric working limit now include an information popover
  explaining that the figure is an app assumption, not published data.

### Decisions made

- BR-51 uses 180 seconds because the primary Machias document consumed 113.23
  seconds of the prior 120-second ceiling; three minutes leaves useful demo
  headroom without changing model capability.
- BR-52 through BR-58 keep Personalize display behavior deterministic and
  source-backed.
- The plausible annual maximum table remains in the prototype, but its values
  are explicitly unsourced working assumptions. Reviewing or replacing those
  values with defensible evidence remains an open item.
- Summary "Excluded" counts purchasable items outside the base cart, including
  already-owned, removed, optional, inapplicable conditional, school-provided,
  unstocked, and catalog-unavailable items. Teacher directions remain notes,
  not excluded products.

### Live verification

- OpenAI `gpt-5.6-sol` completed the final paired Maple extraction in 60.62
  seconds with 16 requirements per student and zero merge interrupts.
- The $150 run landed at $110.04 with three interrupts. Reusing the exact same
  extraction and cached match decisions at $85 kept the $110.04 required cart,
  produced four interrupts, and produced a $76.97 recommended plan.
- These differ from A-9/A-10's $109.83 and $69.24. A-11 changed no matching or
  calculation path; the difference is current model-assisted extraction and
  suitability variation. The retained evidence is insufficient to claim that
  either live cart is more correct.
- One earlier comparable attempt completed extraction but timed out during an
  OpenAI matching batch. A deterministic structured-match fallback on a second
  extraction also produced $110.04 and three interrupts at $150, with a $76.97
  $85 recommendation; it was kept separate from the final model-assisted run.

### Files changed

- Updated `agent/rules.py`, `app.py`, `tests/test_app.py`,
  `tests/test_extract.py`, and `JOURNAL.md`.

### Testing performed

- Focused Lists/Personalize, extraction, provider, and merge suite: 185 passed.
- `py -3.12-arm64 -m pytest -q`: 353 passed, 1 skipped.
- Production renderer tests use real `ExtractionEnvelope`, `Requirement`,
  `RequirementSource`, `SupplyItemReview`, and `ReviewFlagGroup` objects.
- Static AST inspection found no model-call candidates in
  `agent/optimize.py`. Apparent arithmetic candidates in `agent/extract.py`
  were type-union annotations and prompt-string assembly, not numeric or money
  arithmetic; no code was changed to silence that false positive.

### Problems or limitations

- Streamlit remains unavailable on Windows ARM64, so the anchor jump, summary
  column widths, popover placement, and compact card spacing require deployed
  browser review.
- The strict live baseline required multiple attempts because one model-assisted
  matching batch timed out. This remains a five-minute demo reliability risk
  outside the Lists/Personalize scope of A-11.
- The plausible annual maximum values have no external source and require
  review before any claim beyond this prototype.

### Recommended next step

Deploy Part A-11 and visually verify the per-student summary, anchor jumps,
student-scoped default approval, rationale information popover, and zeroed
quantity controls on both desktop and phone widths.

## 2026-07-29 — Part A-12 unstructured documents and section detection

### What changed

- Removed the structure schema's requirement that every document contain a
  selectable section. The structure prompt now explicitly returns no sections
  for one plain, ungraded list and does not promote table headers into choices.
- Added a deterministic Lists-boundary filter for table/column headers and the
  invented "Unlabeled supply list" placeholder.
- Added the three-way grade-scope rule: no named grades extracts the whole
  document; a matching grade keeps automatic selection; named grades with no
  match keep the BR-18 stop.
- Wired both grade-mismatch navigation choices to run as soon as the parent
  selects them. The upload path returns to Lists and identifies the student
  whose document should be replaced; the removal path returns to Your students.
- Added the exact 25-line tabular paste as a test fixture and exercised the
  production `_inspect_list_inputs`, `resolve_document_sections`,
  `_extract_list_inputs`, and navigation callback contracts with real schema
  objects.

### Diagnosis and decisions

- The "Quantity Item Notes" defect was cart-affecting structure detection, not
  display duplication. The prompt encouraged one section per top-level list,
  the schema rejected zero sections, and the retry demanded at least one
  section. Those constraints forced a plain table to acquire an invented
  selectable section.
- BR-59 distinguishes document grade scope. It amends BR-17 and BR-18 so their
  section question/stop behavior applies only when at least one grade is named.
- BR-60 makes layout headers and invented placeholder labels non-sections.
- BR-61 requires mismatch proceed controls to perform their named navigation
  immediately.

### Live verification

- Kelley GPT API `gpt-oss-20b` detected zero sections for the tabular paste in
  1.99 seconds. Whole-document extraction completed in 33.22 seconds.
- All 25 item lines were interpreted. Twelve became in-domain `Requirement`
  objects. Thirteen distinct source lines were retained as catalog-unavailable
  items; none became an extraction failure, skipped line, or uninterpreted
  line.
- A paired Kelley Maple run extracted 16 requirements per student with no
  failures and no requirement-merge interrupts. At $150 the cart landed at
  $110.04 with four interrupts. Reusing those extractions and 127 captured
  suitability decisions at $85 retained the $110.04 required cart and produced
  a $74.91 recommended plan with five interrupts.
- The $110.04 landed cost matches the final A-11 live cart, not the older
  $111.21 guard. The changed interrupt and recommended-plan figures are from
  a fresh Kelley suitability pass, not the A-12 section rules. A-12 changed no
  matching, gate, optimization, or money path.

### Testing and architecture

- Focused section, extraction, and app suite: 155 passed.
- `py -3.12-arm64 -m pytest -q`: 357 passed, 1 skipped.
- Static AST inspection found no model-call candidates in
  `agent/optimize.py`. The apparent `agent/extract.py` operator candidates are
  type-union annotations and prompt-string assembly, not numeric, quantity, or
  money arithmetic. No code was changed to silence those false positives.

### Limitation

- Streamlit is unavailable on this Windows ARM64 machine, so the immediate
  radio navigation and focused upload notice still require deployed visual
  confirmation.

## 2026-07-29 - Part A-13 unified grade scope and scoped list replacement

### What changed

- Added one deterministic grade-scope classification for the three BR-59
  cases and routed section-screen blocking, parent-screen routing, and
  automatic selection through that classification.
- Changed "Upload a different document" to remove only the affected student's
  document, section selection, and extraction. Other students' saved lists,
  section selections, and extractions are retained and reused.
- Added renderer-path tests that call the actual Lists section and working
  screen functions with production `ListInput`, `DocumentStructureEnvelope`,
  `DocumentSelection`, `ExtractionEnvelope`, and `Requirement` objects.

### Diagnosis and decisions

- BR-59 was already applied inside `resolve_document_sections`, and the
  working-screen router correctly treated an ungraded document as the whole
  list. The stale block lived in `_render_sections`, which independently
  treated a choice with zero selected sections as unresolved. This mattered
  when session state was already on the section screen.
- BR-62 makes `classify_document_grade_scope` the sole grade-scope authority
  and centralizes the three downstream decisions that consume it.
- BR-63 scopes document replacement to one student while retaining unaffected
  students' state.

### Split-consumer audit

- Grade interpretation is still duplicated between section resolution and
  post-extraction wrong-list warnings. This is the most likely grade-related
  divergence because the warning path has separate token and range parsing.
- Section selectability is derived both by the extraction display helper and
  by the primary-language section resolver. Malformed multilingual metadata
  could make the displayed candidates differ from resolvable candidates.
- Item identity is derived at schema correction, normalization, same-student
  merge, cross-student aggregation, and selected-SKU consolidation. These
  stages have different purposes, but merge identity versus normalized
  aggregation identity is the highest-risk overlap.
- Quantity semantics are interpreted at schema validation, review package
  status, normalization, merge defaults, review edits, and classroom
  multiplication. Package-count assumptions and merge-default UI mapping are
  the most likely areas to drift.
- Per-item exclusion quantity is applied by separate Personalize-row and
  conflict-card callbacks. Both currently use the same named zero constant,
  but they remain two mutation paths.
- No broader consolidation was attempted because Part A-13 requested an audit,
  not a refactor of those areas.

### Testing and architecture

- Focused section suite: 119 passed, 1 skipped.
- `py -3.12-arm64 -m pytest -q`: 360 passed, 1 skipped.
- Static AST inspection found no model calls in `agent/optimize.py`.
  Operator candidates in `agent/extract.py` are type unions and prompt-string
  assembly, not numeric, quantity, or money arithmetic. No code was modified
  for a static-check result.

## 2026-07-29 - Setup narration and pasted-list provenance

### Objective

Restore the original setup navigation controls, remove internal housekeeping
copy, simplify ungraded-list narration, and give pasted lists the same
page-linked source evidence as uploaded documents.

### Work completed

- Fully reverted the uncommitted step-route object, step-specific Continue
  button keys, and associated AppTest. The original immediately rendered
  buttons and navigation behavior are restored.
- Removed both unused-budget-draft cleanup messages. Cleanup still occurs only
  after the parent confirms a budget mode; it is no longer narrated.
- Rephrased entry removal, type change, and grade change consequences in terms
  of the parent's student, budget, list, and next action.
- Reduced BR-59 case (a) to "This list will be extracted" and show section
  guidance only when the section screen actually has a decision.
- Added BR-64 deterministic pasted-source pagination. The original string is
  retained exactly, split only at existing line boundaries, rendered without
  wrapping, and stored as session-only PNG pages.
- Routed requirements, catalog-unavailable items, and every existing source
  popover through the retained source pages and exact source-line page lookup.

### Diagnosis and decision

- The original Continue caption is selected by the renderer chosen from
  `intake_step` before the click. Its destination is a separate literal in
  that renderer after validation. Current caption/destination pairs agree,
  but they are not derived from one shared value.
- The reverted implementation did not add another explicit rerun. It changed
  each button's widget identity at the same layout position, which caused the
  entire control block to mount late in deployed testing.
- No second Continue-button fix was attempted. A future change should first
  reproduce the deployed lifecycle in x86 AppTest and should preserve the
  original immediately rendered controls.

### Files changed

- Updated `agent/pipeline.py`, `agent/rules.py`, `app.py`,
  `tests/test_app.py`, `tests/test_sections.py`,
  `tests/test_streamlit_lifecycle.py`, and `JOURNAL.md`.

### Testing and limitations

- Focused app, section, pipeline, and Streamlit-lifecycle suite:
  130 passed, 1 skipped.
- `py -3.12-arm64 -m pytest -q`: 361 passed, 1 skipped.
- The skipped module is the real Streamlit AppTest suite; Streamlit is
  intentionally unavailable on this Windows ARM64 machine.
- Pasted provenance is covered through the same production Lists builder,
  extraction stamper, and source-popover renderer used by the screen.
- No model call, matching, optimizer, approval, or money behavior changed.

### Recommended next step

Run the existing and new AppTests in the deployed x86 environment, then use
that lifecycle evidence before choosing another Continue-caption approach.

## 2026-07-29 - Setup notices and text-backed pasted-list provenance

### Objective

Finish the three outstanding Setup and Lists behaviors: meaningful budget-mode
consequences, quiet BR-59 case (a), and a viewable exact source for direct paste.

### Work completed

- Budget-mode cleanup now distinguishes an amount the parent edited from an
  untouched default or generated allocation. Untouched values are discarded
  silently. Entered amounts produce one plain-language consequence after the
  parent continues.
- BR-59 case (a) proceeds without narrating grade detection. The section-screen
  explanation renders only when at least one student has an actual section
  decision.
- Direct paste retains the exact original string, paginates only at existing
  line boundaries, and opens in the same source popover used by uploaded
  documents. The page body is text-backed and displayed without wrapping.
- Requirement and catalog-unavailable provenance is stamped with the retained
  document label and resolved source page before downstream screens use it.

### Decisions made

- Widget touch state is the boundary between a generated/default budget value
  and a parent-entered amount; internal draft creation is never narrated.
- Pasted evidence remains text rather than being converted to PDF or an image,
  preserving whitespace and characters without adding a dependency.
- BR-64 remains the deterministic rule for direct-paste source pagination.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine. The production
  AppTest module exists on disk and covers the real setup screen, but is skipped
  locally and must run in the deployed x86 environment.

### Files changed

- `agent/pipeline.py`
- `agent/rules.py`
- `app.py`
- `tests/test_app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Focused production-path suite: 131 passed, 1 skipped.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 362 passed, 1 skipped.
- Static architecture inspection found zero model-call candidates in
  `agent/optimize.py`. The reported `agent/extract.py` binary operators were
  type-union annotations, not arithmetic.

### Remaining work

- Run the Streamlit AppTests in the deployed x86 environment to verify the
  mounted-widget notice behavior visually.

### Recommended next step

Deploy the current changes and verify one untouched and one edited budget-mode
round trip, then open a pasted list's source popover on a later page.

## 2026-07-29 - Pasted source control reaches Lists section screen

### Objective

Trace and fix the deployed absence of a View source control for a pasted,
ungraded document on the Lists section screen.

### Work completed

- Confirmed direct paste already produced retained text pages during the
  production Lists ingestion path.
- Added whole-document source controls to the BR-59 no-grade card. The card
  now opens every retained pasted page through the common source popover.
- Changed direct-paste document labels to natural list names such as
  `Kevin's supply list`; uploaded documents continue to use their filenames.
- Routed both no-grade and sectioned student cards through one student/grade
  heading formatter.
- Exercised the actual section, Personalize item, conflict-table, and
  unavailable-item renderers with production `ListInput`, requirement,
  extraction, and merge objects.

### Diagnosis and decisions

- The defect was not ingestion or source-page generation. A plain pasted list
  correctly had zero detected sections. The BR-59 no-grade display branch
  stopped after its caption and never invoked the source renderer.
- Uploaded PDFs usually followed the separate detected-section branch, which
  already invoked `_render_section_source_links`; this made the defect appear
  input-type-specific.
- The same two display branches independently formatted headings, producing a
  hyphen in the no-grade branch and a middle dot in the sectioned branch.

### Files changed

- `app.py`
- `tests/test_app.py`
- `tests/test_sections.py`
- `JOURNAL.md`

### Testing performed

- Focused Lists and provenance suite: 123 passed, 1 skipped.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 364 passed, 1 skipped.
- Static architecture inspection found no model-call candidates in
  `agent/optimize.py`; `agent/extract.py` contains no numeric arithmetic.

### Problems or limitations

- Streamlit remains unavailable on this Windows ARM64 machine, so deployed
  visual confirmation must occur after deployment. The tests execute the
  production render functions and inspect their emitted popovers and exact
  text-page bodies.

### Remaining work

- Deploy and visually open the new whole-document View source popover.

### Recommended next step

On the deployed Lists screen, use one pasted ungraded list alongside a document
that requires section selection and confirm the pasted card opens page 1.

## 2026-07-29 - Setup navigation commits in button callbacks

### Objective

Remove the transient old Continue caption between Budget and Shopping
preferences without changing button keys, layout, money behavior, or adding an
extra rerun.

### Work completed

- Moved all three forward Setup transitions and both backward transitions into
  button callbacks, which Streamlit executes before its normal rerun.
- Kept the navigation buttons unkeyed and in their existing columns.
- Defined each button caption and destination in one Setup transition entry.
- Moved exit validation into the corresponding forward callback. Invalid
  Students, Budget, or Shopping preferences input leaves the current step
  active and records the field messages for the next render.
- Added a real Streamlit AppTest covering all five transitions and invalid
  cancellation, plus an ARM-runnable production-renderer test proving both
  Budget buttons mount before callback validation.

### Diagnosis and decisions

- Streamlit widget identity includes the label, so the new caption did not
  literally inherit the old button's backend identity.
- The visible lag came from two reruns: the click rerun first rendered the old
  Budget step, then script-body navigation changed the step and explicitly
  requested another rerun. Reusing the same unkeyed visual slot made that
  intermediate caption visible.
- Callback navigation commits the destination before the one normal rerun and
  avoids both the old intermediate frame and the delayed keyed-widget remount.

### Files changed

- `app.py`
- `tests/test_app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Focused Setup suite: 101 passed, 1 skipped.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 365 passed, 1 skipped.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so the real AppTest
  module remains skipped locally. Its test executes the production app in the
  deployed x86 environment.
- The ARM-runnable screen test verifies immediate button construction,
  unchanged lack of explicit widget keys, callback validation cancellation,
  and the absence of an explicit rerun.

### Recommended next step

Deploy and click Budget to Shopping preferences once while watching the button
row; the Shopping-preferences screen should paint directly with “Continue to
the lists.”

## 2026-07-29 - Lists rationale in parent language

### Objective

Replace internal merge rationale with concise parent-facing explanations while
leaving requirement preselection logic unchanged.

### Work completed

- Replaced the deterministic quantity, identity, and parent-override rationale
  templates in `agent/rules.py` with the approved wording.
- Amended BR-55 so plausible annual maximums remain internal BR-40 inputs and
  are no longer shown as figures or described as working limits.
- Removed the threshold information icon and its popover from the Lists
  conflict card.
- Removed the redundant processing caption inside “More detail · same product
  or different products.”
- Used each requirement's actual source section and stated value in the
  different-product rationale.
- Expanded abbreviated source section names to the unique full label from the
  parent-confirmed document selection in quantity options.
- Added a production-renderer test covering all six rationale outcomes, the
  absence of the removed disclosures, and full section labels.

### Decisions made

- BR-40 and BR-47 calculations and thresholds were not changed.
- The plausible annual maximum table remains unsourced prototype data. It
  should eventually be grounded in real district list data before use beyond
  this demonstration.

### Files changed

- `agent/rules.py`
- `agent/requirement_merge.py`
- `app.py`
- `tests/test_app.py`
- `tests/test_requirement_merge.py`
- `JOURNAL.md`

### Testing performed

- Focused Lists and merge suite: 140 passed.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 366 passed, 1 skipped in
  3.28 seconds.

### Problems or limitations

- Streamlit remains unavailable on this Windows ARM64 machine, so the updated
  copy and removed popover still require deployed visual confirmation.

### Recommended next step

Deploy the Lists conflict card and verify the full section labels and concise
rationale at desktop and phone widths.

## 2026-07-29 - Personalize screen vertical navigation and density

### Objective

Replace the long Personalize page with a summary and per-student vertical
navigation while keeping all counts and decisions on the existing BR-52 state.

### Work completed

- Added a left-side Summary/student tab strip with decision-count badges only
  for students who still need a choice.
- Rebuilt Summary around the remaining decision count, existing default
  controls, one per-student count table, and item-name jump controls.
- Reordered each student view so decisions come first, settled cart items use
  one compact line, unavailable items share one collapsed section and one
  document source control, and missing items remain student-scoped.
- Routed item jumps through one callback that stores both the destination
  student tab and a stable item scroll target.
- Applied the BR-46 display transform to unavailable, uninterpreted, skipped,
  and teacher-note source text while retaining exact source evidence in the
  source popover.
- Reworded source scope and skipped-content labels, and omitted page wording
  for a one-page typed list.
- Added BR-65 plus a deterministic extraction safeguard so an explicit
  “Three-Ring Binder with Dividers” line retains both purchasable items when a
  model omits one component.

### Decisions made

- The compound-line safeguard does not make another model call. A component
  restored deterministically is marked below full confidence so the parent can
  verify it.
- Settled cart rows retain editing controls behind “More detail,” but do not
  repeat source controls.
- Exact source popovers continue to show the unchanged audit line, including
  original delimiters; ordinary parent-facing item labels do not.

### Files changed

- `agent/rules.py`
- `agent/extract.py`
- `app.py`
- `tests/test_extract.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused extraction, review, and app suite: 162 passed.
- Full suite before the final typed-list wording assertion: 368 passed, 1
  skipped.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so the responsive
  visual layout still needs confirmation in the deployed environment.

### Recommended next step

Deploy the Personalize screen and visually confirm the left navigation with
ten students at desktop and phone widths.

## 2026-07-29 - Deterministic brand and item recognition

### Objective

Make audited brand-only and known item-synonym lines resolve reproducibly from
their source wording without depending on a model-proposed category or brand.

### Work completed

- Added BR-66's deterministic brand table, including common plural and
  punctuation variants, with canonical brand spelling and implied item type.
- Added BR-67's item-synonym table for single-subject notebooks and loose
  notebook paper rulings, including graph paper.
- Added a production-boundary recovery pass for recognized source lines omitted
  entirely by model output.
- Changed schema validation so deterministic source recognition overrides a
  missing or conflicting model category and cleans malformed known-brand hints.
- Added BR-68 source-derived none, preferred, and required brand strength.
- Added BR-69 review routing for strict no-substitute wording that names no
  brand.
- Added BR-70 reconciliation so a recognized purchasable requirement removes a
  spurious unavailable record for the same item and source while preserving a
  genuinely different unavailable component.
- Narrowed graph-paper recognition so a graph-paper composition notebook
  remains a composition notebook with a graph ruling.

### Decisions made

- Graph paper uses the existing `notebook_paper` canonical item with
  `ruling="graph"`. The seeded catalog has no exact graph-paper offer.
- Preferred brands remain presentation-only in this block. `brand_hint` was
  deliberately not added to `UnitNeed`, aggregation, matching, or optimization.
- All configured brand-to-item mappings were explicitly supplied by the
  requested audit; none were guessed.

### Files changed

- `agent/rules.py`
- `agent/schema.py`
- `agent/extract.py`
- `agent/review.py`
- `tests/test_extract.py`
- `tests/test_review.py`
- `JOURNAL.md`

### Testing performed

- Focused extraction, review, normalization, and matching suite: 113 passed.
- Focused extraction, review, and requirement-merge regression suite after
  narrowing graph-paper recognition: 124 passed.
- Kelley GPT API `gpt-oss-20b` live audit: the same 15 lines produced identical
  canonical items and brand states in two final-code runs.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 398 passed, 1 skipped in
  2.96 seconds.

### Problems or limitations

- Preferred brands still do not affect matching because `brand_hint` is not
  carried into `UnitNeed`; this was explicitly deferred.
- Loose graph paper is representable, but the seeded catalog does not contain
  an exact graph-paper offer.
- Streamlit remains unavailable on this Windows ARM64 machine, so its existing
  real-AppTest skip remains.

### Recommended next step

Decide the separate matching policy for preferred brands before carrying
`brand_hint` into aggregation or offer ranking.

## 2026-07-29 - Setup budget defaults scale by covered students

### Objective

Replace the flat Setup budget starting value with an exact per-student value
that accounts for classroom size without overwriting a parent's edits.

### Work completed

- Added BR-71's $75-per-covered-student starting value as integer cents.
- Updated the production Budget screen so a combined starting value uses all
  covered students and each individual starting value uses its own entry count.
- Kept untouched starting values synchronized with roster and classroom-size
  changes.
- Preserved parent-entered values, including values carried across budget-mode
  switches.
- Added production-renderer coverage for one student, two students, a
  10-student classroom, a mixed session, and recalculation before versus after
  a parent edit.
- Added a real Streamlit lifecycle test for classroom-size changes; it remains
  part of the existing x86-only test module.

### Decisions made

- A displayed starting value remains application-controlled until its widget
  change callback records a parent edit. After that, roster changes do not
  overwrite it.
- BR-33 was not changed. Shared classroom supplies avoid multiplication only
  when extraction marks them `shared`; unspecified scope still uses the
  conservative per-student multiplier.

### Files changed

- `agent/rules.py`
- `app.py`
- `tests/test_app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Focused app and aggregation suite: 110 passed, 1 skipped.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 400 passed, 1 skipped in
  3.04 seconds.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 machine, so its real
  lifecycle module remains skipped locally and runs in the deployed x86
  environment.
- BR-33 depends on extraction assigning `supply_scope="shared"` correctly;
  unspecified classroom items still scale by class size.

### Recommended next step

Visually verify a classroom entry in the deployed app, including changing its
size before and after editing the budget.

## 2026-07-29 - Product nouns take precedence over brand-implied items

### Objective

Prevent a recognized brand from replacing an explicitly named product with
the brand table's usual product category.

### Work completed

- Added BR-72's product-noun precedence rule.
- Reworked deterministic source recognition so the most specific noun or
  synonym wins before the brand-implied fallback.
- Retained brand-only recognition, including Expo markers as the established
  dry-erase shorthand.
- Recognized liquid glue as an understood but out-of-catalog product so it is
  shown as unavailable instead of converted to glue sticks.
- Allowed a source containing only understood unavailable items to complete
  extraction rather than being misreported as an empty extraction.
- Removed the graph-paper-specific composition-notebook guard; general
  longest-phrase selection now preserves composition books and notebooks.
- Added production-extraction coverage for brand/product conflicts, liquid
  glue, and graph-paper composition notebooks.

### Decisions made

- Brand spelling and preferred/required strength still come from the
  deterministic brand table even when a conflicting product noun wins.
- `Expo markers` is retained as a complete recognized brand phrase, while
  explicit wording such as `Expo eraser` or `Expo dry erase markers` resolves
  from the remaining product noun.
- Catalog-unavailable records do not carry a numeric confidence field. A
  corrected liquid-glue Requirement is reduced to 0.69 before being converted
  into the unavailable record, and the final envelope requires review.

### Files changed

- `agent/rules.py`
- `agent/extract.py`
- `tests/test_extract.py`
- `JOURNAL.md`

### Testing performed

- Focused extraction and normalization suite: 102 passed.
- Focused extraction, requirement-merge, and normalization regression suite:
  139 passed.
- Kelley GPT API `gpt-oss-20b` live verification: two final-code runs produced
  identical canonical items and brand strengths for all 21 requested lines.
  Model confidence differed between runs without changing deterministic item
  recognition.
- Final full suite: `py -3.12-arm64 -m pytest -q` -> 414 passed, 1 skipped
  in 3.07 seconds.

### Problems or limitations

- Model confidence remained nondeterministic across the two live runs. The
  deterministic identity result was stable.
- Liquid glue has no canonical catalog category or offer, so it remains
  unavailable by design.

### Recommended next step

Review whether other known out-of-catalog school-supply nouns should be
recognized explicitly so they remain visible even when a model misclassifies
them into an available category.

## 2026-07-29 — Single-entry budget choices

### Goal

Remove the redundant distinction between combined and per-entry budgets when
the session contains exactly one student or classroom, without losing a
parent-entered amount when the entry count changes.

### Work completed

- The production Budget screen now presents one entry-specific budget choice
  plus `No set budget` when the session has exactly one entry.
- Added plain possessive labels, including names ending in `s`, and neutral
  wording when the entry has no label.
- Kept the existing three budget choices for sessions with two or more entries.
- Resolved the available option set and durable selected mode together so a
  stale multi-entry mode cannot remain selected in a one-entry session.
- Preserved a combined amount when expanding from one entry to several.
- When a per-entry session collapses to one entry, moved the remaining entry's
  amount into the equivalent single budget and preserved its edited status.
- Added production-renderer tests for labels, defaults, and both entry-count
  transitions.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused setup suite:
  `py -3.12-arm64 -m pytest -q tests/test_app.py tests/test_streamlit_lifecycle.py`
  -> 109 passed, 1 skipped.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 416 passed, 1 skipped in
  3.07 seconds.

### Problems or limitations

- The real Streamlit lifecycle test module remains skipped locally because
  Streamlit is unavailable on this Windows ARM64 machine. The added tests call
  the same `_render_budget_step` function used by the screen.

## 2026-07-29 — Personalize navigation and complete Summary

### Objective

Remove the Streamlit widget-state crash when moving between Personalize views
and replace the count-only Summary with a compact, complete review.

### Work completed

- Separated the durable Personalize selection from the radio widget's state.
  Direct radio changes and student/item jump callbacks now update only the
  non-widget selection.
- Hid the navigation control label while retaining an accessible label.
- Rebuilt the Summary in this order: overall decision status, approve-all
  defaults, source documents, every item, and per-student counts and controls.
- Added one Summary source popover per student list, including exact retained
  text for pasted lists and rendered pages for uploaded PDFs.
- Rendered every BR-52 item with one of the four requested statuses and a short
  reason for pending decisions.
- Made item rows and student names navigate to their production student view.
- Added stable anchors for settled, excluded, conditional, and unavailable
  items; excluded or unavailable sections open when a Summary jump targets
  them.
- Included both current and legacy catalog-unavailable records in BR-52's
  shared per-student exclusion set.

### Decisions made

- The durable view key is `personalize_selected_view`; the radio alone owns
  `personalize_view_control`.
- Existing `personalize_active_tab` values are migrated once and removed.
- Source links appear once near the top of Summary rather than once per item.
- Per-student approve controls remain visible but disabled when that student
  has no remaining default decision.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused Personalize and lifecycle suite:
  `py -3.12-arm64 -m pytest -q tests/test_app.py tests/test_streamlit_lifecycle.py`
  -> 109 passed, 1 skipped.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 416 passed, 1 skipped in
  3.23 seconds.
- The production `_render_review` path was driven through Summary, a student
  view, back to Summary, an item jump, and back to Summary while the test state
  rejected assignments to widget-owned keys.
- The production Summary opened exact pasted text and rendered page 1 from a
  real PDF fixture.

### Problems or limitations

- Streamlit is not installed locally on this Windows ARM64 machine, so visual
  inspection remains a deployed-environment check. The lifecycle regression
  test calls the production screen renderer and enforces the widget ownership
  rule that caused the deployed crash.

### Recommended next step

Deploy this Personalize-only change and visually verify table density and
source-popover sizing with two 20-plus-item lists.

## 2026-07-29 - Personalize decisions, statuses, and navigation state

### Objective

Make every pending Personalize card actionable without opening secondary
details, separate parent exclusions from unavailable items, and keep the
navigation indicator synchronized with item jumps.

### Work completed

- Added a visible decision and its production control before the
  acknowledgement on every flagged item card.
- Added accept, edit, and remove choices for uncertain readings, with the exact
  source line beside the interpreted item.
- Added direct quantity, package-size, item, brand, color, size, material, and
  other-detail controls for their corresponding issues.
- Reworded Summary statuses as short parent actions.
- Split unavailable items from parent-excluded items in BR-52's per-student
  item sets and counts.
- Omitted the repeated Student column for one-student sessions while retaining
  it for multi-student sessions.
- Synchronized the durable Personalize selection and displayed navigation
  choice through a revisioned widget identity that is never written by the
  application.
- Moved the collapsed unavailable section between Decisions needed and In your
  cart.
- Hid the Personalize navigation label and added a visible production border
  to the Lists paste field.

### Files changed

- `agent/rules.py`
- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused Personalize suite:
  `py -3.12-arm64 -m pytest -q tests/test_app.py tests/test_review.py -x`
  -> 129 passed in 1.58 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 417 passed, 1 skipped in
  3.54 seconds.
- The production `_render_review` path was exercised with session state that
  rejects application writes to widget-owned keys.
- The decision-card test exercised every current decision issue through the
  production student renderer and verified each control appears before its
  acknowledgement.

### Problems or limitations

- Streamlit remains unavailable on this Windows ARM64 machine, so visual
  inspection of spacing and the textarea border remains a deployed-environment
  check. The emitted production CSS and production renderer behavior are
  covered by tests.

## 2026-07-29 - Personalize button state and Summary actions

### Objective

Prevent button-state assignment failures on the Personalize screen and make
the Summary table actionable without mixing unavailable items into the cart
rows.

### Work completed

- Audited every Personalize button and moved all durable navigation,
  confirmation, and jump state to non-widget keys.
- Gave Summary navigation buttons visit-scoped action keys so an old button
  identity is never reused after a view transition.
- Replaced direct writes to student acknowledgement-widget keys with one
  durable `personalize_confirmed_group_ids` set.
- Made Summary per-item approvals and student-card acknowledgements update that
  same durable confirmation set.
- Moved approve-all directly above the Status heading.
- Renamed the item table to `The Supply List` and split Quantity from Item.
- Moved unavailable items into a red-bordered block after decisions and before
  handled cart rows on both Summary and student views.
- Strengthened the production-renderer test state to reject button-key
  assignments both before and after button registration.

### Decisions made

- Conditional questions with no selected branch do not receive an
  accept-default checkbox because no safe default exists; their item link
  continues to open the actual choice.
- Existing acknowledgement values under legacy checkbox keys are read once
  into the durable confirmation set for session continuity.
- The checked-in pre-change source did not assign the reported Summary
  item-button key. The new visit-scoped key avoids reuse of any stale deployed
  key while preserving the separate durable jump state.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused Personalize suite:
  `py -3.12-arm64 -m pytest -q tests/test_app.py tests/test_review.py -x`
  -> 129 passed in 1.45 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 417 passed, 1 skipped in
  3.32 seconds.
- The production `_render_review` path verified Summary navigation buttons,
  per-item confirmation, count updates, red unavailable-block ordering, and
  student-card confirmation with button keys treated as read-only.

### Problems or limitations

- The current source did not reproduce a programmatic write to the reported
  item-button key, so the exact deployed origin could not be proven locally.
- Streamlit is unavailable on this Windows ARM64 machine. The strict test
  double models read-only button keys but not Streamlit's full widget cleanup,
  frontend identity reconciliation, or automatic callback/rerun timing.

### Recommended next step

Deploy the Personalize-only change and confirm that Summary item jumps,
per-item approvals, and both unavailable blocks render correctly in the hosted
Streamlit runtime.

## 2026-07-29 - Personalize final pass

### Objective

Make parent edits authoritative everywhere on Personalize while retaining the
original list request and simplifying each unresolved AI recommendation to one
accept-or-edit decision.

### Work completed

- Diagnosed the stale-label defect: detail widgets returned current values,
  while the student label and Summary rendered the prior durable review model
  until the bottom of the rerun.
- Added one Personalize resolution boundary that commits current item and
  quantity values before student and Summary content is derived.
- Retained an immutable session-scoped snapshot of each list-requested item and
  quantity, displayed only when the parent changes either value.
- Reordered the Supply List table to Item, Status, Quantity, with Student first
  only for multi-student sessions, and removed package counts from Summary
  quantity text.
- Replaced decision-specific control collections with two choices: accept the
  AI recommendation or edit the item/quantity, committed by a
  `Send selection to cart` action.
- Moved approve-all below the pending rows, renamed acceptance controls, and
  persisted whether an AI recommendation or parent edit resolved each item.
- Kept unavailable items in their red action block and renamed the separate,
  collapsed excluded-item section to `Not being purchased`.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused Personalize tests:
  `py -3.12-arm64 -m pytest -q tests/test_app.py -k "personalize or review_understanding"`
  -> 12 passed, 99 deselected.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 418 passed, 1 skipped in
  3.38 seconds.
- The production `_render_review` path was exercised with the strict
  session-state double for item and quantity edits, original-value display,
  decision commits, Summary acceptance, durable AI marks, and clearing those
  marks after a parent edit.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 environment, so final visual
  alignment and wrapping still require inspection after deployment. No local
  Streamlit run was attempted.

## 2026-07-29 - Budget choice display order

### Objective

Place the per-student or per-classroom budget choice before the combined-budget
choice without changing budget behavior.

### Work completed

- Reordered the multi-entry Budget radio options to show per-entry budget,
  combined budget, then no set budget.
- Kept the combined budget as the existing default selection and preserved all
  amount seeding, state mapping, and interpretation logic.
- Updated the production Budget-screen tests to assert the new visual order and
  the unchanged selected mode.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Budget-screen tests: `py -3.12-arm64 -m pytest -q tests/test_app.py -k
  "budget_screen"` -> 5 passed, 106 deselected.

### Problems or limitations

- Streamlit is not installed on this Windows ARM64 environment, so the radio
  order was verified through the production screen renderer rather than a local
  visual run.

## 2026-07-29 - First Budget visit selection

### Objective

Select the per-student or per-classroom budget mode on the first multi-entry
transition from Students to Budget, without changing later saved choices.

### Work completed

- Applied the initial per-entry selection in the production
  Students-to-Budget callback only when Budget has never been reached and the
  session contains more than one entry.
- Preserved the parent's selected budget mode on every later backward,
  forward, or banner-navigation visit.
- Added callback-level and deployed-runtime lifecycle coverage for the initial
  selection and later preservation.

### Decisions made

- The global budget-mode default remains unchanged. The UX preference is
  intentionally scoped to the first successful multi-entry transition only.
- A one-entry session continues using its entry-specific budget label because
  combined and per-entry modes are equivalent there.

### Files changed

- `app.py`
- `tests/test_app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Focused tests: `py -3.12-arm64 -m pytest -q tests/test_app.py -k
  "budget_screen or first_budget_visit"` -> 6 passed, 106 deselected.

### Problems or limitations

- The AppTest lifecycle assertion is collected but skipped locally because
  Streamlit is intentionally unavailable on Windows ARM64; it will run in the
  deployed x86 environment.

## 2026-07-29 - Parent-facing total-cost terminology

### Objective

Present the full amount including tax and fulfillment fees as "total cost"
throughout the interface and current documentation, while retaining the
existing internal `landed_cost` identifiers and every calculation unchanged.

### Work completed

- Replaced parent-facing "landed cost" wording in the setup, review, approval,
  budget-planning, summary, per-store, per-student, donation, checkout, export,
  warning, help, and decision-log copy.
- Renamed the shopping preference to "Lowest total cost" and changed marginal
  wording such as "adds ... landed" to "adds ... to total".
- Updated `BRD.md`, `README.md`, `PROJECT.md`, and `RUNBOOK.md`. BR-03 now says
  that any figure labelled "total cost" includes tax and fees, while an item
  subtotal may appear only when explicitly labelled and is never the total
  cost.
- Kept all internal `landed_cost` fields, keys, variables, and calculation
  paths unchanged. Added the requested explanatory comment in
  `agent/rules.py`.
- Updated only tests that assert display copy; numeric expectations and
  internal field-name assertions were not changed.

### Files changed

- `app.py`
- `agent/approval_options.py`
- `agent/budget_plans.py`
- `agent/gate.py`
- `agent/pipeline.py`
- `agent/rules.py`
- `BRD.md`
- `README.md`
- `PROJECT.md`
- `RUNBOOK.md`
- `tests/test_app.py`
- `tests/test_approval_options.py`
- `JOURNAL.md`

### Testing performed

- Focused display and pipeline tests:
  `py -3.12-arm64 -m pytest -q tests/test_app.py
  tests/test_approval_options.py tests/test_pipeline.py tests/test_gate.py -x`
  -> 152 passed in 1.98 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.05 seconds.
- An AST scan found no parent-facing Python string containing "landed".
- A repository-wide case-insensitive search found 236 matching lines in 17
  files. They are internal identifiers and calculation-oriented developer
  tests/docstrings, plus historical entries in this journal; current
  specifications and user documentation contain none.

### Maple Street regression run

- Provider: OpenAI, model `gpt-5.6-sol`.
- Both extractions completed without failure. The $85 run reused the exact
  extractions from the $150 run.
- The current live result was $109.83 with 3 interrupts at $150. At $85, the
  unchanged required cart was $109.83 and the recommended plan was $69.24
  with 4 interrupts.
- These do not reproduce the historical $111.21 and $71.07 reference figures.
  The rename changed no computed expression or internal numeric assertion; the
  live difference is model-dependent extraction/matching drift already present
  in the current pipeline, not a total-cost copy change. The historical figures
  must not be replaced silently with the new live values.

### Problems or limitations

- The two model-dependent Maple Street references are not stable under a fresh
  current-model run, so they cannot serve as deterministic regression tests
  without freezing confirmed extractions and suitability decisions.
- Streamlit is not installed locally on Windows ARM64, so no local Streamlit
  run was attempted.

## 2026-07-29 - Per-entry budget help

### Objective

Give every per-student and per-classroom budget input the same help-popover
treatment as the combined-budget input, with copy scoped to that entry.

### Work completed

- Moved the combined-budget help sentence into a named copy constant and added
  the parallel per-entry sentence beside it.
- Routed both combined and per-entry amount fields through one shared
  `_render_budget_amount_input` component, so Streamlit creates the same help
  icon for both modes without duplicated widget markup.
- Extended production Budget-screen tests to confirm every rendered amount
  field receives the correct help copy.
- Updated the intake copy audit that previously expected the combined sentence
  to remain inline in `_render_budget_step`.

### Decisions made

- The per-entry copy mirrors the combined sentence and changes only its scope:
  it names one student or classroom rather than the total across the session.
- No budget value, allocation, rounding, validation, state, or business-rule
  behavior was changed.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused Budget-screen tests:
  `py -3.12-arm64 -m pytest -q tests/test_app.py -k
  "budget_step_renders_one_field or budget_screen_scales_untouched or
  intake_uses_guided_student_language"` -> 3 passed, 109 deselected in
  1.21 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.55 seconds.

### Problems or limitations

- Streamlit is not installed locally on Windows ARM64, so the help icons were
  verified through the production renderer's `help` arguments rather than a
  local visual run.

### Remaining work

- None for this scoped copy/UI change.

### Recommended next step

- Confirm the two popovers appear side by side as intended in the deployed
  Streamlit application.

## 2026-07-29 - Single per-entry budget help icon

### Objective

Keep the per-entry budget guidance available without repeating the same help
icon beside every student or classroom amount, and make the dollar-sign example
match accepted input.

### Work completed

- Kept the combined-budget help icon unchanged.
- Passed per-entry help text only to the first rendered student or classroom
  amount; every later amount receives no help value and therefore no icon.
- Changed both paired help sentences from `85.50` to `$85.50`.
- Escaped the dollar sign only at the Streamlit display boundary so the parent
  sees a literal dollar sign rather than Markdown math formatting.
- Updated production Budget-screen tests to assert one per-entry help value
  followed by `None` for later inputs.

### Decisions made

- No parsing change or new business rule was needed. `money_to_cents` already
  accepts a single leading dollar sign and correctly grouped thousands
  separators.
- Budget calculations, allocation, rounding, validation, and thresholds remain
  unchanged.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Direct production-parser verification:
  `$85.50 -> 8550`, `85.50 -> 8550`, and `$1,085.50 -> 108550`.
- Focused tests: 4 passed, 108 deselected in 1.44 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.18 seconds.

### Problems or limitations

- Streamlit is not installed locally on Windows ARM64, so icon placement was
  verified through the production renderer's exact `help` values rather than a
  local visual run.

### Remaining work

- None for this scoped follow-up.

### Recommended next step

- Confirm in the deployed app that only the first per-entry amount has a help
  icon and that both popovers display `$85.50` literally.

## 2026-07-30 - Section column in duplicate evidence

### Objective

Add a parent-visible Section column to the Lists duplicate-resolution evidence
table without creating a second section-resolution path.

### Work completed

- Added Section between “What the list says” and Source in every duplicate
  evidence row.
- Introduced `resolved_merge_source_sections` as the single display resolver
  used by both the evidence table and the existing “Quantity from …” radio
  labels.
- Passed each student’s already-resolved selected-section labels into the
  evidence renderer from the same screen state used by the quantity controls.
- Left an unresolved section cell empty rather than falling back to a document,
  pseudo-section, placeholder, or internal value.
- Preserved the existing source popover and page link-out path unchanged.
- Set the four column widths to `[0.7, 3.2, 1.7, 2.4]`, keeping “What the list
  says” as the widest column.

### Decisions made

- No new provenance field was added. `RequirementSource.section_name` already
  supplies both rows and radio choices; the change only centralizes its
  parent-visible resolution.
- Existing quantity radio labels remain unchanged as requested.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused production-renderer tests:
  `py -3.12-arm64 -m pytest -q tests/test_app.py -k
  "conflict_rows or lists_merge_screen or pasted_source_controls"` ->
  3 passed, 109 deselected in 1.33 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.27 seconds.

### Problems or limitations

- Streamlit is not installed locally on Windows ARM64, so four-column wrapping
  was verified structurally through the production renderer rather than by
  launching the interface.

### Remaining work

- None for this scoped table change.

### Recommended next step

- Inspect the deployed table at desktop and phone widths and decide separately
  whether the now-partly-redundant “Quantity from …” radio labels should be
  shortened.

## 2026-07-30 - Concise source labels in duplicate evidence

### Objective

Remove the repeated “View source” prefix from source controls rendered under
the duplicate evidence table’s Source header while preserving every standalone
source label and the existing popover contents.

### Work completed

- Added an `under_source_header` context parameter to the shared
  `_render_source_reference` component.
- Used that parameter only in `_render_merge_source_rows`; its buttons now read
  as document and page references without the redundant prefix.
- Left all eight standalone production call sites on the existing full
  “View source · …” label path.
- Widened the Source column from 2.4 to 2.8 and narrowed Section from 1.7 to
  1.5. Quantity remains 0.7 and “What the list says” remains the widest column
  at 3.2.
- Kept BR-41’s 30-character document-name cap. It remains useful for unusually
  long filenames, preserves the extension, and leaves the full filename in the
  unchanged hover text. The 29-character Machias filename is not shortened.

### Decisions made

- No alternate source component or call-site string replacement was created.
  The shared component owns both label forms.
- Source resolution, page resolution, cached provenance, and popover content
  remain unchanged.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused source and evidence tests:
  `py -3.12-arm64 -m pytest -q tests/test_app.py -k
  "conflict_rows or source_button_filename or pasted_list_screen_builds or
  pasted_source_controls"` -> 4 passed, 108 deselected in 1.71 seconds.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.17 seconds.

### Problems or limitations

- Streamlit is not installed locally on Windows ARM64, so physical button
  clipping was not visually measurable. The production-renderer test verifies
  the shorter exact label and wider Source allocation.

### Remaining work

- None for this scoped copy and layout change.

### Recommended next step

- Confirm the Machias document and page number remain fully visible in the
  deployed table at the demonstration viewport.

## 2026-07-30 - Duplicate decision rationale and result placement

### Objective

Keep the same/different-product explanation visible on the duplicate-resolution
card and replace it with a truthful result when the parent changes the
preselected answer.

### Work completed

- Traced the identity decision through consolidation, normalization,
  aggregation, matching, and review before changing its copy.
- Added one shared rationale-or-result renderer and used it for both quantity
  rationale display and product-identity status display.
- Moved the product-identity status above the collapsed decision control.
- Renamed that control to “Change · same product or different products.”
- Replaced the inaccurate surviving-description claim with the source-backed
  effect the code actually applies.
- Extended the production Lists renderer test to verify ordering and both
  override directions.

### Files changed

- `app.py`
- `agent/rules.py`
- `tests/test_app.py`
- `tests/test_requirement_merge.py`
- `JOURNAL.md`

### Testing performed

- Focused renderer and merge tests: 2 passed.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.19 seconds.

### Problems or limitations

- The merge retains the first source-backed variant’s product constraints, but
  there is no explicit parent-selectable surviving-description field.

### Remaining work

- If desired in a later scope, show the exact retained product attributes in
  the result line instead of only naming their source section.

## 2026-07-30 - Parent-facing inference language sweep

### Objective

Make rationale, result, and explanation copy distinguish the app’s inferences
from source evidence, parent choices, and deterministic calculations.

### Work completed

- Hedged product-identity, quantity-use, grade-match, reconciliation, catalog
  equivalence, substitution, and selected-match claims at their source
  templates.
- Kept source quotations, parent choices, quantities, costs, taxes, fees,
  document locations, and explicit assumption labels direct.
- Updated exact-copy tests for the merge and Personalize production paths.

### Decisions made

- Used one plain hedge per inferred line rather than adding a general
  disclaimer.
- Left “AI read,” “AI assumed,” and “AI recommended” wording unchanged because
  it already identifies the statement as an interpretation rather than fact.
- Left school-provided-item wording direct because it paraphrases an explicit
  source-list section.

### Files changed

- `agent/rules.py`
- `agent/gate.py`
- `agent/pipeline.py`
- `app.py`
- `tests/test_app.py`
- `tests/test_requirement_merge.py`
- `JOURNAL.md`

### Testing performed

- Focused merge, app, gate, and pipeline tests: 171 passed.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 419 passed, 1 skipped in
  3.61 seconds.

### Problems or limitations

- Streamlit is unavailable locally on this Windows ARM64 environment, so the
  copy was verified through production render functions and tests rather than
  a locally launched interface.

### Remaining work

- None for this copy-only sweep.

### Recommended next step

- Read the changed lines together in the deployed app to confirm the repeated
  “we believe,” “looks like,” and “appears” phrasing feels balanced in context.

## 2026-07-30 — Personalize pack-count and source wording fixes

### Decisions made

- Kept BR-23 unchanged. A missing numeric package count now triggers review only
  for canonical items whose package contents are count-sensitive.
- Kept the full cited page in the source popover and relabeled the exact line as
  the locator within that page.
- Added an explicit session-only input kind to retained list inputs so pasted
  lists and uploaded documents can be described accurately.
- Deferred the optional-item intent feature pending approval of its state,
  plan-resolution, visibility, and BR-73 design.

### Files changed

- `agent/review.py`
- `agent/pipeline.py`
- `app.py`
- `tests/test_review.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused review and app tests: 132 passed.
- Full suite: `py -3.12-arm64 -m pytest -q` -> 420 passed, 1 skipped in
  3.20 seconds.

### Problems or limitations

- Streamlit is unavailable locally on this Windows ARM64 environment, so the
  rendering behavior was verified through the production render functions and
  tests rather than by launching the application.

### Remaining work

- Optional-item choices remain unchanged until the proposed deferred-intent rule
  and resolution behavior are approved.

## 2026-07-30 — Personalize layout and durable disclosure state

### Objective

Restructure Personalize around one Summary/student navigation dimension, put
outstanding decisions first, reduce routine item weight, and preserve each
item's disclosure and edit state across Streamlit reruns.

### Work completed

- Replaced the duplicate inventory Summary with one routing card per student or
  classroom, compact counts, source access, and scoped recommendation actions.
- Ordered each student view as decisions, optional items, cart items, then
  items left out; sections with no items are not rendered.
- Added one source disclosure near the top of each student view and one
  aggregate source disclosure on Summary.
- Replaced the decision checkbox with explicit recommendation and edit buttons.
- Added keyed in-cart disclosures with Tier 1 purchase controls and Tier 2
  item-detail controls.
- Raised the Streamlit minimum to 1.60 for state-tracked expanders and added an
  x86 GitHub Actions job that runs the full suite, including AppTest.

### Named finding — fourth defined-but-unconsumed mechanism

`SupplyItemReview.notes` was the fourth mechanism found to be defined but
unconsumed, after BR-34, BR-32's ambiguous-descriptor list, and `brand_hint`.
The Personalize form collected a Parent note and displayed it on later reruns,
but `confirmed_requirements()` never copied it into a requirement. The note was
therefore silently dropped at that boundary and could not affect matching,
planning, or the shopping plan. The field and control were removed rather than
continuing to collect text the application did not use.

### Decisions made

- Optional items remain left out and display no choice controls; a deferred
  include-if-it-fits intent remains out of scope until its rule is proposed and
  approved.
- In-cart counts remain post-merge requirement counts. They are not package or
  SKU line counts because those do not exist until planning.
- `Other required details` remains because it flows into requirement
  attributes and attribute-sensitive matching.
- The Item selector remains as a Tier 2 correction control; source provenance
  remains attached when its canonical category changes.
- Zero-item sections are hidden because an empty heading adds navigation noise
  without giving the parent an action.

### Testing performed

- Focused production-render tests: 131 passed; the Streamlit AppTest module was
  skipped on Windows ARM64.
- Full local suite: 419 passed, 1 skipped.
- The first x86 Actions run exposed stale single-entry budget-mode values in
  existing lifecycle tests. Those fixtures were corrected to use two entries
  when testing the multi-entry mode switch.

### Problems or limitations

- The new Personalize expander lifecycle test cannot execute on the local
  Windows ARM64 environment and must be verified by the x86 workflow.
- Existing `use_container_width` parameters are deprecated in Streamlit 1.60
  but remain supported. Replacing them is a separate compatibility cleanup.
- The default expander style still has more visual weight than the new
  `type="compact"` style. Compact may suit routine in-cart rows, but it was not
  enabled without explicit approval.

### Remaining work

- Propose the optional-item deferred-intent behavior before assigning or
  implementing BR-73.

## 2026-07-30 — Four production-shaped AppTest mismatches exposed by x86

### Finding

Of the 12 AppTests that had never executed on the Windows ARM64 development
machine, four were wrong in the same specific way: their fixture or rerun route
constructed a UI state that production does not produce. None of these defects
in the tests was visible until the x86 runner existed.

The four instances were:

1. `test_preferences_do_not_narrate_unused_budget_state`
2. `test_preferences_explain_discarded_entered_individual_budgets`
3. `test_preferences_explain_discarded_entered_combined_budget`
4. `test_section_statement_and_submitted_scope_use_same_live_state`

The first three built one-entry sessions and then selected multi-entry budget
options that the production Budget screen does not offer for one entry. The
fourth used an inline AppTest script that called `_render_sections()`
unconditionally on every rerun. Production routes by
`st.session_state["screen"]` and stops calling that renderer after it advances
the session to `working`; the test instead called the old screen again and
created a rerun loop that production does not have.

### Commit history and timeout decision

- `03a9093` increased only the section AppTest harness timeout from Streamlit's
  3-second default to 15 seconds. This was an attempted workaround, not a
  root-cause fix, and its x86 run still failed.
- `bf2e958` corrected the harness route to match production. That routing
  change, rather than the timeout increase, ended the rerun loop.
- The timeout override has now been removed. The section AppTest again uses
  Streamlit's 3-second default so the corrected route is tested without the
  failed workaround.

### Process lesson

An AppTest must reproduce both the controls production makes available for the
current session shape and the production screen router. Future AppTest fixtures
and wrappers should be checked against both before being treated as
production-path coverage.

## 2026-07-30 — Scroll once when a Working episode begins

### Objective

Bring each new Working-screen episode into view once without pinning the parent
to the top during progress reruns, and make progress changes available to screen
readers.

### Work completed

- Inventoried the production progress UI: document-structure inspection, list
  extraction, and shopping-plan building are the only animated status regions.
  Matching, optimization, budget checking, and approval checking are narrated
  within the plan-building status rather than separate spinners.
- Added an incrementing Working-episode identifier, an active-episode key, and
  an episode-specific completed-scroll key in Streamlit session state.
- Used Streamlit 1.60's non-iframe `st.html` JavaScript support to request one
  parent-page scroll on the first progress render in each episode. Browser-side
  failures are caught and leave the app running without scrolling.
- Added a visually hidden polite ARIA status region for the initial and updated
  progress messages.
- Cleared the active and completed-scroll episode keys whenever the production
  router renders a screen other than `working`; the counter remains so the next
  episode receives a new identity.

### Testing and limitation

- Added an x86 AppTest that enters the real `main()` router, confirms the same
  episode and scroll marker survive a Working rerun, confirms both guards clear
  after leaving, and confirms a second Working entry receives a new episode and
  scroll marker.
- AppTest cannot execute the browser JavaScript or observe scroll position. The
  automated test covers only the session-state once-per-episode guard; the
  physical page movement requires deployed-browser verification.
- Updated two existing Working-screen recorders with Streamlit 1.60's `html`
  surface so they continue to exercise the production renderer.

### Files changed

- `app.py`
- `tests/test_streamlit_lifecycle.py`
- `tests/test_sections.py`
- `JOURNAL.md`

### Remaining work

- Verify in the deployed app that the first animated Working status scrolls to
  the top, later progress reruns do not pull the page back, and a later
  extraction episode scrolls once again.

## 2026-07-30 — Verify duplicate-screen claims against source evidence

### Objective

Stop the duplicate-resolution screen from claiming identical source wording is
different, and stop presenting equal quantities as contrasting values.

### Audit finding

The production screen had three explanations that were more specific than
their guards:

- Its introduction said source lines used different wording without comparing
  them.
- Its same-product rationale always said the lines were worded differently,
  although the identity rule had not compared the parent-visible source text.
- Its ambiguous-description heading claimed one description used one
  potentially meaningful word, while the rule only established that the
  residual description-token sets differed.

The equal-quantity header used verified source values, but phrased two equal
values as a contrast. Quantity rationale arithmetic and outcomes, the
different-product source details, parent override results, and item exclusion
results were confirmed to be guarded by the state they describe.

### Work completed

- Compared the same parent-visible item descriptions used in the evidence
  table after trimming surrounding whitespace and folding case. Punctuation,
  word differences, word order, and internal spacing remain meaningful
  differences.
- Exact matches now say: `Both lines match exactly, so we've treated them as
  the same product.`
- Different descriptions retain the existing hedged same-product rationale.
- Equal two-source quantities now say: `Both parts of the list ask for N.`
- Neutralized the screen introduction and ambiguous-description heading so
  neither asserts an observation the code did not make.
- Added a production-screen test using the real Backpack evidence from the
  5th and Highly Capable Class sections.

### Files changed

- `agent/rules.py`
- `agent/requirement_merge.py`
- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing and remaining work

- Focused merge and app tests: 149 passed.
- Full ARM64 suite: 420 passed, 1 x86-only module skipped.
- Run the x86 workflow before treating the change as complete.
- The same/different control remains unchanged. Identical source descriptions
  may justify de-emphasizing it in a later, separately approved UI pass.

## 2026-07-30 — Stale derived review state masked parent decisions

### Objective

Trace and prevent duplicate-resolution choices from being hidden by an older
Personalize result, then cover every affected choice path.

### Distinct defect class

This was not another defined-but-unconsumed mechanism. The duplicate-resolution
screen correctly stored quantity, same/different-product, and exclusion choices;
the deterministic merge correctly consumed all three; and the resulting
extraction envelopes were correct. Personalize then served a stale cached copy
of `review_items` derived from an earlier merge result.

The defect was live in the deployed app while 419 local tests passed. It was
found by manual click-through when an item explicitly excluded during duplicate
resolution reappeared in Personalize, not by the automated suite.

This class should be tracked separately from BR-34, BR-32's descriptor list,
`brand_hint`, and Parent note. Those mechanisms had no downstream consumer.
Here, the consumers were correct and a stale derived view masked their output.

### Work completed

- Cleared source-derived Personalize state after fresh extraction, section
  changes, and duplicate-resolution submission.
- Added production-screen regressions proving that exclusion, a selected
  quantity, and a same/different-product answer reach newly built Personalize
  rows rather than being masked by stale rows.

### Design finding and remaining work

The current invalidation points fix the deployed defect but remain enumerated.
A stronger follow-up is to store a deterministic fingerprint of the finalized
`extracted_lists` envelopes beside `review_items` and rebuild source-derived
rows whenever that fingerprint differs. This would make staleness detection
follow the actual consumed source rather than relying on every future writer to
remember an invalidation call. Parent-added rows should remain separate from
that source-derived cache.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Focused production duplicate-resolution regressions: 3 passed.

### Recommended next step

Review and separately approve replacing enumerated Personalize cache resets
with source-fingerprint validation.

## 2026-07-30 — Personalize source cache made staleness-aware

### Objective

Replace path-by-path invalidation of source-derived Personalize rows with one
deterministic comparison against the finalized extraction envelopes.

### Work completed

- Added a stable SHA-256 fingerprint over the child-keyed, finalized
  `ExtractionEnvelope` payloads.
- Stored the fingerprint beside `review_items` and made both production entry
  paths into Personalize rebuild source-derived rows whenever it changes.
- Removed the dedicated reset helper and its section, extraction, and
  duplicate-resolution calls, as well as older direct source-row clears in
  list replacement paths.
- Kept parent-added rows outside the source-derived cache. They now survive a
  source rebuild; only removing their student removes those independent rows.
- Cleared widget values tied to superseded source rows so mounted controls
  cannot reapply an older item or quantity after a rebuild.

### Decisions made

- The finalized envelopes are the fingerprint input because they already
  contain the resolved section and duplicate decisions that determine
  Personalize. Hashing every upstream draft separately would duplicate the
  merge contract.
- A fingerprint match preserves in-progress parent edits. A mismatch resets
  only source-derived review decisions and originals, then rebuilds from the
  current envelopes.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- Added regressions for grade-driven re-extraction, automatic section
  selection, and parent-added-item survival across a source rebuild.
- Full ARM64 suite: 426 passed, 1 x86-only module skipped.

### Remaining work

- The x86 AppTest count must be confirmed by the next workflow run; no push
  was made as part of this local change.

## 2026-07-30 — Personalize AppTest fixture aligned with its source

### Objective

Correct the x86-only keyed-expander test without weakening the extraction
fingerprint invariant.

### Work completed

- Replaced an impossible empty `ExtractionEnvelope` plus hand-injected review
  rows with two real `Requirement` objects and review rows produced by
  `organize_extractions`.
- Mounted the Personalize screen once before setting expander state, matching
  the real lifecycle in which those widgets exist before a parent opens them.
- Audited all 13 AppTests for the same envelope/review mismatch. This was the
  only AppTest that constructs that relationship; the other 12 exercise setup,
  section, or progress state without source-derived review rows.

### Files changed

- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing and remaining work

- ARM64 cannot execute this Streamlit AppTest module.
- The x86 workflow run is required before keyed-expander independence is
  considered verified against a production-shaped session.

## 2026-07-30 — AppTest asserted an invented output identity

### Distinct production-shape variant

The earlier eight production-shape defects supplied inputs the application
could not produce. This ninth variant supplied real requirements but asserted
against widget-key strings invented by the test instead of reading the widgets
the application rendered. The assertions could pass while being disconnected
from the actual expanders and controls.

### Work completed

- Added shared settled-row key helpers and used them in the production
  Personalize renderer.
- Rewrote the lifecycle test to locate both rows and their controls from the
  rendered element tree.
- The test now opens row A, changes its quantity, opens row B, changes row B's
  quantity, and verifies both open states and values remain independent.
- No widget key string is written literally in the test.

### Files changed

- `app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing and remaining work

- ARM64 cannot execute the AppTest behavior.
- The x86 workflow result determines whether keyed-expander independence
  actually holds; a failure will be reported rather than worked around.

## 2026-07-30 — Personalize disclosures were never independent

### Finding

The production-shaped behavioral AppTest proved that settled item disclosures
did not stay open independently. Editing a quantity changed the expander label,
and Streamlit 1.60 includes that label in the stateful expander's internal
identity. The row was therefore remounted with its default closed state. The
quantity and other controls used separate keys and survived; this defect affected
open state only.

This behavior had passed its test across several rounds while never being true.
It surfaced only after the test stopped inventing literal widget-key strings and
instead derived row identities from the same production helpers used by the
screen. All 13 AppTests are now production-shaped. Four of the first 12 had not
been: they exercised UI states production could not create.

### Resolution

The first attempted correction passed the expander widget value back as its
initial open value. The x86 AppTest remained red because that widget-owned value
is itself tied to the remounted identity.

Each settled row now mirrors its open state into a separate non-widget key and
uses that durable value when Streamlit rebuilds an expander identity. Opening or
editing one row neither opens nor closes a sibling row. No item value or merge
behavior was changed.

### Verification boundary

The behavioral test is intentionally unchanged: it opens row A, edits it, opens
row B, edits it, and requires both rows to stay open with independent values.
ARM64 cannot execute this AppTest; the x86 workflow is the verification path.

## 2026-07-30 — Personalize fingerprints scoped per student

### Finding

The first source-aware cache used one fingerprint for every finalized extraction
envelope in the session. A change to one student's envelope rebuilt every
source-derived row, which could silently erase quantity, ownership, or other
Personalize edits already made for an unaffected student.

### Resolution

- Store one finalized-envelope fingerprint per student.
- Reuse the existing source-derived row object and widget state for every
  unchanged student.
- Rebuild rows only for changed students and for members of a deduplicated
  cross-student decision touched by that change.
- Reconsider the affected shared decision while retaining unrelated confirmed
  and parent-edited groups.
- Keep parent-added items outside source refreshes.

The screen still calls the same cache-refresh function; no parallel invalidation
path was added. Parent-facing notification copy for a choice invalidated by its
own changed source remains intentionally unimplemented pending approval.

### Regression coverage

- A quantity and ownership edit for student A survives a replacement extraction
  for student B, including the mounted row widget values.
- A shared ambiguity involving A and B is reconsidered when B changes, while an
  unrelated edited ambiguity for A remains accepted and unchanged.

## 2026-07-30 — Mutable labels are part of Streamlit widget identity

### Finding

Streamlit 1.60 does not treat a supplied key as the complete identity for every
component. Stateful expanders and popovers include their label in the internal
identity. If that label contains mutable data, changing the data remounts the
component and can silently reset its tracked open state even though its explicit
key did not change.

This is a Streamlit widget-identity finding, separate from the
production-shaped-test series. Conventional inputs and buttons in this app use
their explicit key as the main identity, so changing their displayed label does
not reset their value. The audit did identify two additional stateful source
expanders whose labels include mutable list counts; their possible open-state
reset remains an unmodified exposure pending a separate decision.

### Verification boundary

The audit inspected every widget call in `app.py`, including widgets rendered
through columns and containers, and checked Streamlit 1.60's identity settings
for buttons, inputs, expanders, and popovers. No audited widget was changed as
part of the inventory.

## 2026-07-30 — Changed list sources now invalidate choices visibly

### Objective

Tell a parent when a genuine source-row change makes an earlier Personalize
choice no longer applicable.

### Work completed

- Compare refreshed source-derived rows with their stored original rows.
- Preserve edits on unchanged rows, including rows for the same student whose
  other list content changed.
- Record a notice only when the changed row had a confirmed or edited parent
  choice.
- Show the notice at the top of Personalize, before the ordinary screen
  guidance and decision content.

### Parent-facing wording

`The source line for {item} on {student}'s list changed, so your earlier
choice no longer applies. Please review it again.`

This copy contains no hedge because both the source change and invalidated
choice are deterministic state comparisons, not an inference.

## 2026-07-30 — A targeted regression passed before it proved the defect

### Testing-series finding

The duplicate-choice carry-forward regression originally targeted the right
production behavior and still passed before the correction. Its assertion
proved only that the expected row existed somewhere after navigation; it did
not prove that stale pre-merge rows were absent or that the parent's resolved
choice was the row Personalize actually used. Strengthening the same test to
assert the complete rendered result made it fail correctly on x86 run
`30580086902`.

This differs from the earlier impossible-fixture cases. The input and route
were production-shaped, but the assertion was too weak to distinguish a fresh
derived result from a stale one. A green targeted test was therefore false
reassurance until its negative assertion was added.

### Open correctness boundary

The duplicate-resolution completion marker means the parent saw the evidence
and submitted that screen. It does not mean the parent separately confirmed
the extracted quantity or wording. Personalize currently uses that marker to
suppress the generic low-confidence reading question, so a product-identity
answer can silence a transcription question the parent did not answer. This
remains unchanged pending a separate rules decision.

## 2026-07-30 — Personalize Summary made reviewable in place

### Objective

Make the Personalize Summary useful for checking sources, resolving visible
decisions, and revisiting included or optional items without leaving Summary.

### Work completed

- Replaced the student-count cards with three responsive lanes: decisions
  needed, optional items, and items in the cart.
- Put each item name on a keyboard- and touch-accessible popover containing the
  same production review controls used in the student view.
- Restored the bulk recommendation action only inside the decisions lane,
  after the recommendations it applies to are visible.
- Added one source card per student. Each card shows the sections read and
  opens every selected document page rather than defaulting to page 1.
- Kept unavailable items in their own red-bordered action block and retained a
  separate disclosure for items deliberately left out.
- Made optional items reversible through the same settled-row controls used by
  already-owned and do-not-buy items.
- Moved optional items below the add-an-item panel in each student view and
  removed the suggestion that the app might have read a missing item
  incorrectly.

### Verification boundary

ARM64 exercises the production render function with production-shaped source
envelopes. The new optional-item lifecycle and Streamlit popover state require
the x86 AppTest workflow and are not considered verified until that run passes.

The first x86 run selected a same-labelled checkbox from the wrong rendered
row, so the test was corrected to scope the control through the Tissues
disclosure. The next run proved a real one-rerun lag: the optional value was
saved, but section grouping had already used the earlier value. Optional widget
state is now resolved before the single BR-52 section model is built, so the
item moves into the cart on the same interaction.

The follow-up fixture also said `1 box of tissues` while constructing a
Requirement with unit `each`. It was corrected to the production extraction
shape (`box`) rather than weakening the expected cart transition. That exposed
the remaining production cause: the pre-section widget resolver consumed item
and quantity edits but not optional, already-owned, or do-not-buy status. Those
three mounted values are now resolved through the same function before BR-52
builds any section.

### Deferred decision

School-provided items remain display-only. A parent override should be a
specific action such as `Add this to my cart instead`, preserve the school's
source line, and record that the parent chose to buy an item the list said
would be provided. That behavior was proposed but not implemented in this
pass.

## 2026-07-30 — Duplicate review confirmation made field-specific

### Finding

The earlier `parent_reviewed_duplicate_sources` marker proved only that the
parent submitted the duplicate-resolution screen. Personalize treated it as
confirmation of the entire source reading and removed every low-confidence
question, including quantities the parent never selected.

### Resolution

- Replaced the broad marker with independent product-identity and quantity
  confirmations.
- A same/different answer confirms only product identity.
- A quantity is confirmed only when the parent actively changes a quick
  choice, custom quantity, or individual variant quantity.
- Untouched prefilled quantities do not receive a confirmation marker.
- Personalize now scopes any remaining low-confidence review to identity,
  quantity, or other details instead of suppressing the whole source line.

### Regression coverage

- A parent-selected merged quantity removes quantity uncertainty while
  retaining unresolved identity/detail review.
- A different-products answer leaves both untouched variant quantities
  reviewable.

### Architecture

The markers and review classification are deterministic. No model call,
matching behavior, price, or optimizer calculation changed.

## 2026-07-30 — School-provided items are no longer a one-way status

### Finding

School-provided requirements were preserved as source evidence but forced to
remain outside the cart. The parent could correct already-owned, optional, and
do-not-buy statuses, yet could not act when the school-provided statement did
not match their situation.

### Resolution

- Added an explicit `Add this to my cart instead` action to a school-provided
  row.
- The action changes only cart eligibility. It retains the exact source line,
  document, section, page, and consolidated source references.
- The requirement carries a deterministic parent-choice marker into plan
  building, and the append-only decision log records the response with the
  parent as actor.
- The shopping-plan source summary states that the parent added the item even
  though the list said the school would provide it.

### Verification boundary

The full ARM64 suite passes, but Streamlit is unavailable there. The production
button callback, immediate row regrouping, provenance preservation, and
decision recording are covered by the x86 AppTest workflow and are not treated
as verified until that workflow passes.

The first x86 fixture used `1 box of crayons` without a package count. Production
correctly retained its separate missing-pack-count review after the parent chose
to buy the item; the purchase choice must not confirm an extraction assumption.
The fixture was changed to the production-valid explicit quantity `24 crayons`
so the lifecycle test isolates the school-provided override. The corrected x86
workflow passed in run 30584416544 with the production Streamlit callback.

### Architecture

No model call, matching behavior, price, optimizer calculation, or business
threshold changed.

## 2026-07-30 — Successful forward actions return the next task to the top

### Objective

When a parent successfully uses the bottom-right primary action, begin the
next task at the top of the page, including transitions between Setup sections.

### Work completed

- Added a session-scoped, numbered scroll request for successful forward
  transitions that do not enter the Working screen.
- Students-to-Budget, Budget-to-Shopping-preferences, and
  Shopping-preferences-to-Lists now queue one request only after validation
  succeeds.
- Approval-to-Summary uses the same request.
- Section-resolution choices that deliberately return to Lists or Students
  also use it.
- Existing Lists, section extraction, duplicate resolution, and Personalize
  actions retain the one-time Working-screen scroll rather than triggering a
  second scroll.
- Consolidated both paths on the same native Streamlit 1.60 `st.html`
  enhancement, with reduced-motion handling and failure isolation.

### State and clearing

`next_task_scroll_counter` identifies each successful transition,
`next_task_scroll_pending` holds the one request awaiting the next render, and
`next_task_scroll_completed` records the consumed episode. The pending key is
removed on that next render, so ordinary reruns cannot pin the page to the top.

### Testing and limitations

The ARM64 suite passed with 432 tests and one Streamlit test skipped. The x86
AppTest follows the production Setup controls and proves that invalid
transitions create no request, successful transitions consume exactly one, and
Back navigation creates none. AppTest cannot observe browser scroll position
or execute that assertion; the real movement still requires deployed-browser
verification.

The first x86 run failed before reaching those assertions because AppTest's
state wrapper does not implement `Mapping.get`, unlike the application-facing
session-state proxy. The test now reads AppTest state through its supported
keyed interface with a missing-key fallback; no production behavior or
assertion was relaxed.

### Architecture

No extraction, matching, pricing, optimizer, gate, or business-threshold
behavior changed.

## 2026-07-31 — Gate proof and Maple variance reconciliation

### Objective

Prove the human-approval boundary still operates after the clean frozen Maple
cart fell from two interrupts to zero, and choose a legitimate one-decision
demo path without reviving BR-08 or weakening another rule.

### Approval-gate proof

Production-shaped frozen-fixture gate contexts now exercise all six active
FR-26 branches: budget exceeded, major substitution, brand-lock break,
preference-dependent attribute choice, low confidence, and required item
unavailable. Each gate branch produces exactly its named interrupt. A seventh
test proves the former non-returnable condition remains intentionally inactive
under retired BR-08, including for the $35.98 non-returnable headphones.

### Named finding — fifth defined-but-unconsumed mechanism

The `brand_lock_break` approval path is the fifth mechanism found to be defined
but unconsumed, after BR-34's closest-package preference, BR-32's empty
ambiguous-descriptor list, `brand_hint`, and Parent note. `match_offers()`
filters every offer whose brand differs from a locked brand before substitution
classification. The pipeline therefore reports a required locked-brand item as
unavailable when its exact brand is absent; it cannot currently emit
`brand_lock_break`. The frozen near-variant proves the gate consumer still
handles such evidence, while a production-path test records that removing all
Ticonderoga stock produces `required_unavailable` instead.

This is also the second unconsumed brand mechanism. A preferred `brand_hint` is
dropped before `UnitNeed` and has no effect on matching, while a required
`brand_lock` acts only as a hard filter and can never become the parent question
specified by FR-26. Brand handling therefore filters required brands but does
not currently express either preferred-brand ranking or approval of a
locked-brand alternative.

Future correction must reconcile FR-17 with FR-26: keep wrong-brand offers out
of automatic optimization, but retain suitable ones as approval-only
alternatives when no exact locked-brand offer is available. This pass documents
the gap and adds its regression test; it does not loosen the brand filter,
change matching, or make the gate reachable by new behavior.

The smallest operational demo variation is a stockout of
`VD-GLU-VB-006`, the exact large Value Basics glue-stick package. Replanning
selects the standard-size Cloud Choice package and produces one
`major_substitution` interrupt. This demonstrates the approval boundary using
an understandable inventory change rather than a manufactured threshold.

### Variance finding

The normalized frozen fixture now reproduces the earlier A-9/A-10 outcomes:
a $109.83 required cart and a $69.24 recommended $85 plan. The $0.21 gap from
the later $110.04 frozen cart was not model nondeterminism: `wide-ruled` and
`wide ruled` froze as different attribute identities, split one notebook-paper
requirement into two package decisions, and added 20 item cents plus one tax
cent. A variance previously attributed wholly to model-assisted extraction or
matching therefore included a deterministic normalization defect.

The historical $111.21/$71.07 pair remains unexplained because no confirmed
extraction and suitability evidence was retained for that run. Provider runs
with different requirement counts, match decisions, recommended plans, or
interrupt counts also remain model-dependent unless they are replayed from the
current frozen boundary. The normalization correction explains the specific
$110.04-to-$109.83 difference; it does not retroactively explain every older
live-run difference.

### Architecture

No gate condition, BR threshold, matching decision, optimization behavior, or
money calculation changed. This pass adds production-shaped gate evidence and
records the corrected causal account.

## 2026-07-31 — Shopping plan organized for checkout and shopping

### Objective

Make the final plan answer two parent questions in order: what the complete
order costs, then what to buy at each store.

### Work completed

- Lead with Total cost, Items, and Stores, followed by the exact item
  subtotal, per-store-rounded tax, and fulfillment fees.
- Name pickup or delivery thresholds when they make a fee free.
- Render one store card with its own total, fulfillment method, item count,
  item subtotal, tax, fee status, and a shortened shopping checklist.
- Keep supporting interpretation, attribution, substitutions, assumptions,
  and the decision log available as collapsed detail below the store lists.
- Keep unresolved approvals visible in a dedicated card immediately before
  simulated checkout, using the existing approval screen for the actual
  decision.
- Mark parent-originated item, quantity, school-provided, and approval choices
  on the affected shopping lines.

### Widget identity and checklist boundary

Every stateful shopping-plan control derives its mounted key from one stable
semantic key plus the current visit revision. Mutable store totals, item
counts, product names, and prices remain display copy and never participate in
widget identity. Shopping ticks are copied into their own durable session map;
they do not modify the immutable optimization result, candidate map, totals,
quantities, or checkout data.

### Verification boundary

The ARM64 suite verifies the durable checklist map and that ticking or clearing
it leaves the optimization result unchanged. The x86 Streamlit AppTest verifies
the real rendered checkbox survives reruns, clears on request, and leaves the
approved plan and total unchanged.

### Architecture

This is a display and session-only shopping aid. No extraction, matching,
pricing, tax, allocation, optimizer, gate, or BR threshold behavior changed.

## 2026-07-31 — Attribute identity normalization and BR-08 retirement

### Diagnosis

Equivalent ruling values reached aggregation as both `wide-ruled` and
`wide ruled`, so BR-13 froze them as different identities and the optimizer
made separate package decisions. Pencil-box size was also represented as
`approx. 8 inches` by extraction but as numeric `length_inches=8` in the
catalog; the matcher retained `approx.` as a comparison token and incorrectly
classified the exact eight-inch offer as an attribute change.

The same prose-versus-number boundary can occur for binder capacity, ruler and
scissor length, water-bottle volume, sanitizer volume, and play-dough weight.
Their catalog keys now participate in the same normalized size comparison.

### Resolution

- Normalize attribute identity text before aggregation: case-fold; treat
  punctuation and hyphens as separators; collapse whitespace; remove
  approximation words; and canonicalize inch and ounce spellings. Exact source
  lines remain unchanged for provenance.
- Compare the catalog's numeric length, capacity, and ounce fields against the
  normalized source dimension.
- Retire BR-08. The legacy `is_returnable` field remains loadable but has no
  matching, optimization, or approval effect.
- Amend BR-02 to state the already-implemented tax boundary explicitly: round
  each store order half-up before combining store totals.

### Frozen Maple impact

The corrected BR-13 merge combines notebook paper and composition notebooks
across the two confirmed Maple envelopes. The required cart changes from
$110.04 to $109.83: item subtotal falls by 20 cents and tax by one cent. At a
$150 budget, both former interrupts disappear: the pencil-box size interrupt
was a false mismatch and the headphones interrupt was retired with BR-08, so
the actual count is zero rather than the anticipated one. At an $85 budget,
only the budget interrupt remains and the exact recommended bundle is $69.24.

### Architecture

Attribute normalization and approval classification remain deterministic. No
model call was added, and no money, package, store-assignment, or tax algorithm
changed.

## 2026-07-31 — Frozen cart boundary and deterministic re-plan corrections

### Reproducible cart boundary

The Maple regression fixture now freezes both confirmed extraction envelopes
and every suitability decision used by matching. It records the human
correction that the Grade 2 composition notebook says “NOT spiral bound.” The
retained fixture produces a $110.04 required cart with two interrupts at a
$150 budget, and a $76.97 recommended plan at an $85 budget. The historical
$111.21/three-interrupt and $71.07 figures predate a frozen extraction and
matching boundary and are retained as retired, unreproducible guards.

### Custom-store crash

The 14 failures shared one cause: exact-match pruning could leave every need
individually matched while no joint assignment fit a one-store cap. Supply
Cloud had suitable alternatives for the complete cart, but those alternatives
had been removed before optimization. Custom feasibility now widens to all
already-judged suitable candidates within each permitted store scope only when
the preferred exact set is incomplete. All 14 full Maple cases select Supply
Cloud at $150.89. The 180-choice domain is covered separately so the regression
does not become a multi-minute performance benchmark.

### Completed second trips

`OptimizationResult.unfulfilled_gap_items` is now the single gate-facing truth
for missing items. A minimum second trip closes the primary-plan gap, so the
single-stop $117.49 Maple plan no longer produces the false claim that its
headphones are unavailable.

### Stockout state and preservation

The stockout action formerly received the original `PipelineResult` even when
the screen displayed a budget- or approval-adjusted optimization. It now takes
the displayed optimization, carries parent omissions and forced products into
the re-plan, reopens only a choice whose selected SKU stocked out, and retains
unrelated approval outcomes, budget actions, and optional selections. Its
notice names the stocked-out product, replacement, total-cost movement, and a
store threshold when a fulfillment fee changes.

The allocation algorithm still performs a full re-solve. A future minimal-
change strategy should pin unaffected line allocations and free only the
stocked-out requirement, widening constraints only when no replacement is
feasible. That strategy can cost more than the global optimum; the parent
should be shown that premium before it is adopted. It was deliberately not
implemented in this pass pending review.

### Verification

Windows ARM64: 454 passed, 1 skipped. The skipped test is the x86 Streamlit
AppTest coverage exercised by GitHub Actions.

## 2026-07-30 — Personalize removal stays visible and duplicate exclusions survive

### Diagnosis

The student navigation labels embedded a mutable decision count. Removing a
decision changed the selected radio option's rendered label during the same
rerun, creating a browser reconciliation risk even though the durable selected
student ID remained correct in AppTest.

The duplicate-resolution exclusion had a separate data-loss defect. Its
checkbox reached deterministic merge code, but that code used `continue` to
discard the entire requirement group. Personalize therefore had no row it
could classify as removed. Unrelated model-produced `Blank selected ... cell`
matrix diagnostics remained in `skipped_lines` and were then presented under
the misleading parent-facing heading "List lines not added to the cart."

### Resolution

- Made Personalize navigation option labels stable student/classroom names;
  decision counts remain visible in each entry's content and Summary.
- Preserve an excluded duplicate group with all contributing source evidence
  and a deterministic parent-removal marker.
- Convert that marker into a deleted review row, so it appears under "Removed
  from cart" but `confirmed_requirements()` cannot send it to the cart.
- Retain blank-matrix diagnostics internally while filtering them from
  parent-facing cart-exclusion copy.

### Verification

The ARM64 suite passed with 442 tests and one Streamlit AppTest skip. The x86
AppTest run is required to verify real widget reconciliation after the
navigation-label change.

### Architecture

No model call, extraction prompt, matching rule, price, money path, optimizer,
approval gate, or BR threshold changed.

## 2026-07-30 — Optional items remain visibly conditional

### Objective

Make optional-list status clear during Personalize and ensure optional items
enter the effective shopping plan only when the exact result satisfies both
the budget and the parent's shopping preferences.

### Work completed

- Renamed the Personalize group to "Optional — left out of cart" and placed it
  immediately above the broader out-of-cart group.
- Added an Out of cart count to each Personalize Summary entry. It combines
  parent-removed items, already-owned items, and items unavailable from the
  permitted stores while keeping optional and school-provided items out of
  that count.
- Amended BR-05 so exact re-optimization must remain within budget and satisfy
  the active store, radius, and fulfillment constraints before an optional
  item is applied.
- Added deterministic feasible-default selection for optional items.
- Kept an over-budget or preference-infeasible attempted selection outside the
  effective cart and added a plain-language reason.
- Generalized final-plan copy from donations to optional items because the
  proposal already contains both optional and donation requirements.

### Decisions and limitations

BR-05's existing ninety-percent eligibility threshold remains unchanged.
Feasible optional defaults are considered in stable source order; this is a
deterministic inclusion policy, not a new optimization objective for ranking
optional wishes.

### Files changed

- `BRD.md`
- `agent/addons.py`
- `agent/rules.py`
- `app.py`
- `tests/test_addons.py`
- `tests/test_app.py`

### Testing

The Windows ARM64 suite passed with 444 tests and one Streamlit AppTest skip.
New fixed-cost coverage verifies an optional item stays out when it would raise
an $80 required cart above a $100 budget and when pickup-only preferences
exclude its delivery-only store.

### Remaining work and recommended next step

Run the x86 GitHub Actions suite to exercise the four-column Streamlit Summary
and optional widget lifecycle with the production Streamlit runtime.

### Architecture

No model calls were added. All optional-item feasibility, budget comparison,
matching reuse, and re-optimization remain deterministic and use integer
cents. Extraction, the approval gate, and required-item optimization behavior
were not changed.

## 2026-07-30 — Named products and decision controls stay aligned

### Defects

- BR-67 deterministically equated loose graph paper with notebook paper even
  though the seeded catalog contains only wide-ruled notebook paper.
- Literal source attributes such as `college-ruled` could be added correctly
  by deterministic parsing and still force a low-confidence review because
  every schema repair shared one confidence flag.
- The compact Personalize action always edited item identity and order
  quantity, even when the card said the uncertain field was items per package,
  brand requirements, or other required details.
- BR-65 compound lines produced every requirement but each card presented its
  row in isolation, making the companion requirement easy to miss.

### Resolution

- Loose graph paper follows the existing liquid-glue safety pattern: it is
  recognized by name and shown as unavailable rather than mapped to a
  different stocked product.
- BR-11's threshold is unchanged. Literal attributes parsed from the exact
  source line no longer lower confidence by themselves; wrong identity,
  quantity, units, and unsupported invented details still do.
- Personalize derives its primary edit fields from the issue it names.
  Package-count decisions edit items per package, and order-quantity labels
  explicitly name items, packages, boxes, or reams.
- Every review state for a deterministically split compound line receives
  companion-item context derived from the same retained source identity.

### Verification boundary

The graph-paper and source-attribute tests exercise production extraction
objects. The package editor is covered by an x86 AppTest that uses the actual
Personalize render path; Streamlit remains unavailable on ARM64.

### Architecture

No new model call, pricing path, matching rule, optimizer calculation,
approval condition, or numeric business threshold was added.

## 2026-07-30 — N-source duplicate-screen audit and Personalize Summary polish

### N-source audit

The duplicate merge groups every distinct source for one student's normalized
item; it is not limited to a pair. Evidence rows, source-specific quantity
choices, and variant quantities iterate over all sources. The parent decision
model is nevertheless binary: all source lines are treated as either one
product or separate products. It cannot represent an N-source partition such
as two matching descriptions plus one different product.

Several parent-facing paths are also pair-shaped. Unequal-quantity introductory
copy reads only the first two quantities, combined-quantity and rationale copy
says "both," the identity expander says "one product or two," and the
different-product rationale takes only the first two source/value pairs. The
source-choice map can also collapse truly identical labels. These limits were
reported but deliberately not changed in this pass.

### Work completed

- Folded each student's source-page control into that student's Summary box.
- Replaced the run-on count sentence with aligned columns ordered In cart,
  Needs a decision, Optional.
- Made each student's decision expander closed on initial Summary render.
- Renamed the excluded-items area to "Left out of cart," added student
  attribution, and gave each item a bordered, high-weight summary row.
- Reused one full variant-name formatter for editable quantities and partial
  exclusion messages, so copy names "lined composition notebooks" rather than
  only "lined."

### Architecture

No merge behavior, quantity selection, extraction, matching, pricing,
optimizer, gate, or business threshold changed.

## 2026-07-30 — Uploaded TXT source previews reuse BR-64

### Objective

Make uploaded plain-text lists viewable through the same source popovers as
pasted text, and make unavailable-preview copy truthful about its source.

### Diagnosis

The upload builder retained TXT as raw bytes without `source_page_texts`, so
the shared source renderer never entered BR-64's text-backed branch. When no
real evidence line was available, two callers supplied the filename as
`source_line`; the shared popover then labeled that filename as a cited line.

### Work completed

- Added one validated-upload builder that routes TXT through the existing
  BR-64 pasted-text builder, then retains its uploaded-input identity and
  filename.
- Reused that builder for individual and shared uploads.
- Made the shared popover distinguish a genuine cited line from a document-name
  fallback.
- Replaced the generic DOCX placeholder with format-specific guidance to open
  the original or upload PDF/TXT for an in-app preview.
- Added production-shaped tests for individual TXT upload retention, text-page
  rendering, genuine cited-line copy, and the DOCX fallback.

### Format audit

PDF source pages render as images; JPG/JPEG and PNG render their retained
images; TXT now renders exact retained text pages. DOCX remains the only
accepted format without an in-app preview and now says so explicitly. A
structurally corrupt PDF can still raise during page rendering after passing
the lightweight upload signature check.

### Architecture

No new model call, extraction interpretation, matching behavior, money path,
optimizer calculation, approval condition, or business threshold changed.

## 2026-07-30 — Page-top navigation respects browser zoom

### Objective

Make the one-time forward-navigation scroll reliably reveal the Ready, Set,
School title even when a parent reviews the app at a non-default browser zoom.

### Diagnosis

The shared script rendered before the title, so two animation frames were only
a timing assumption. It also selected the first of two possible Streamlit
containers, which could be a non-scrolling wrapper while the actual scrolling
ancestor remained unchanged.

### Work completed

- Added a stable `rss-app-title` target to the visible application title.
- Rendered the one-time navigation script after the title exists.
- Replaced the first-match container choice with all known Streamlit scroll
  containers plus dynamically detected scrollable ancestors of the title.
- Kept an unconditional `scrollIntoView` call for the title and retained the
  document/window resets as fallbacks.
- Preserved the numbered session-state episode guard. No retry timer or
  repeated rerun scroll was added, so the parent can scroll normally after the
  initial transition.

### Verification boundary

The tests verify the transition guard, render ordering, stable title target,
and generated browser script. AppTest cannot execute the browser JavaScript or
observe a real scroll position at different zoom levels, so deployed-browser
verification remains required.

### Architecture

No extraction, matching, pricing, optimizer, gate, or business-threshold
behavior changed.

## 2026-07-31 — Classroom list quantity interpretation is parent-confirmed

### Diagnosis

Classroom entries carried a student count, and deterministic aggregation already
multiplied requirements unless extraction labeled an item as shared. The Lists
flow never asked the parent whether a classroom list stated per-student amounts
or whole-class totals. Auto-selected grade sections and documents without grade
headings could also bypass the section screen entirely.

### Resolution

- Amended BR-33 so every classroom list requires one explicit parent choice on
  the section-selection screen: quantities for each student, or totals for the
  whole classroom.
- Made the choice mandatory with no preselected answer, including for ungraded
  lists and automatically matched grade sections.
- Stored the answer per classroom entry and applied it deterministically to the
  extracted requirements before normalization and aggregation.
- Per-student quantities multiply by the classroom count; whole-class totals
  remain exactly as written.
- Replacing or removing a classroom list removes only that list's saved
  interpretation.
- Added a deterministic guard so an unspecified classroom scope cannot enter
  quantity aggregation when the classroom count is greater than one.

### Verification boundary

The ARM64 suite covers the extraction-to-aggregation result and the deterministic
guard. The required Streamlit radio lifecycle is covered by a production-shaped
AppTest that runs only on the x86 GitHub Actions runner.

### Architecture

The model still only reads the list. The parent supplies the classroom scope,
and deterministic code applies the student-count multiplication. No model call,
matching behavior, money path, optimizer behavior, gate condition, or pricing
rule changed.

## 2026-07-30 — Duplicate exclusion uses one authoritative quantity state

### Defect

The duplicate-resolution screen represented exclusion twice: a whole-item
checkbox produced a transient excluded-decision set, while per-variant
quantities were submitted through a separate map that discarded untouched
zeroes. As a result, a zeroed variant missing from that map fell back to its
original quantity and returned to the cart. This was the third live failure in
carrying a duplicate-resolution exclusion into Personalize.

### Resolution

- The displayed quantities are now authoritative for multi-variant inclusion:
  all zero excludes the item, while any positive quantity includes only those
  positive variants.
- The checkbox writes those quantities, and a quantity edit derives the
  checkbox state from the same values.
- Submission carries every displayed quantity, including zero, so the merge
  layer cannot restore an omitted variant from its default.
- Quantity inclusion remains separate from review confirmation: only a
  quantity the parent actually edits receives the parent-confirmed marker.
- The Personalize Summary again leads with compact per-student counts and
  displays only unresolved decisions inline; optional and in-cart items remain
  available in each student's view.

### Verification boundary

The ARM64 suite passes with the Streamlit lifecycle module skipped. Two x86
AppTests exercise the real checkbox callback, submission, and Personalize
rebuild; their result must come from the GitHub Actions runner because
Streamlit is unavailable on this ARM64 machine.

### Architecture

No model call, matching behavior, money path, optimizer calculation, approval
condition, or business threshold changed.

## 2026-07-30 — Forward navigation reaches the visible application title

### Objective

Make every successful bottom-right Continue transition return to the true top
of the Streamlit page so the Ready, Set, School title is visible.

### Finding

The existing one-time transition request was working, but its browser
enhancement scrolled the window rather than Streamlit's nested main application
container. Smooth scrolling could therefore leave the title above the visible
viewport even though the next task moved into view.

### Work completed

- Kept the existing numbered, once-per-transition session-state guard.
- Updated the shared browser enhancement to target Streamlit's main scrolling
  container, the document scrolling element, and the host window.
- Made the navigation jump immediate and applied it after two animation frames
  so the new screen layout is present before scrolling.
- Retained failure isolation: if browser scripting is blocked, navigation still
  completes and only the optional scrolling enhancement is lost.

### Testing and limitation

The ARM64 suite passes. A source-level regression verifies that the shared
enhancement targets Streamlit's main container and the application title.
AppTest cannot execute browser JavaScript or observe the real scroll position,
so the final visual behavior still requires deployed-browser confirmation.

### Architecture

No extraction, matching, pricing, optimizer, gate, or business-threshold
behavior changed.

## 2026-07-30 — Personalize actions and not-in-cart meaning

### Objective

Make the Personalize decision actions explicit and keep “already owned” distinct
from a parent's choice to remove an item from the cart.

### Work completed

- Renamed the recommendation actions consistently in the student view and
  Summary.
- Split each decision card into two two-button rows: interpretation actions
  first, purchase-status actions second.
- Added an explicit “Remove item from cart” action that records deletion without
  setting the already-owned flag.
- Grouped excluded items by reason in both Personalize views so “Already owned”
  and “Removed from cart” are separate lists under “Left out of cart.”
- Added production-render-path coverage for the labels, grouping, callback
  state, and the x86 Streamlit remove interaction.

### Decisions made

Optional items, school-provided items, conditional branches, and unavailable
items keep their current positions and behavior in this pass. A complete
taxonomy was reported for later consolidation, but only the two requested
parent-choice groups were changed.

### Problems or limitations

Catalog-unavailable and unstocked items remain feasibility limits rather than
reversible cart choices. The x86-only AppTest is required to verify Streamlit's
real button lifecycle.

### Files changed

- `app.py`
- `tests/test_app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Focused Personalize tests on Windows ARM64.
- Full suite on Windows ARM64.
- GitHub Actions x86 result to be recorded in the delivery report.

### Remaining work

The broader taxonomy proposal can be applied later if the parent-facing
placement of optional, school-provided, conditional, and unavailable items is
approved.

### Recommended next step

Review the two-row decision-card layout and the separate Already owned and
Removed from cart groups in the deployed x86 build.

## 2026-07-30 — Personalize stage label

Renamed the third journey tab from “Personalize” to “Personalize your cart.”
Only the visible stage label and its navigation-copy assertions changed; the
Personalize workflow, calculations, matching, and approval behavior did not.

## 2026-07-30 — Typed-entry language and source view

### Objective

Present text a parent typed or pasted as their own entry, without leaking the
internal document/page abstraction used to retain item provenance.

### Work completed

- Chose the parent-facing label “What you typed” for every retained typed-entry
  control.
- Kept deterministic BR-64 pagination internally, while rendering the exact
  complete entry once with no filename, page number, or citation header.
- Routed the Lists section preview, duplicate evidence, unavailable-item
  evidence, student Personalize view, and Personalize Summary through the same
  typed-entry-aware source renderer.
- Kept real filenames and page numbers for uploaded files, while replacing
  source-system vocabulary with “View file,” “From the list,” and “File.”
- Removed remaining typed-entry copy that called the entry a document, a source,
  or a paginated file in the Lists workflow and failure messages.

### Audit finding

The old renderer correctly reused BR-64's text-backed pages, but exposed that
internal pagination in every label and rendered only one internal page at a
time. The same shared renderer also emitted “Cited line” and “Source document”
inside popovers. The retained data model remains useful for provenance; only
its parent-facing presentation was wrong.

### Architecture

The language model and deterministic calculation boundaries are unchanged.
No extraction prompt, matching behavior, money path, optimizer, gate, or
business threshold changed.

### x86 verification follow-up

The first x86 run exposed one AppTest assertion that still expected the former
“extract items” section copy. The production screen already rendered “read
items”; the test was updated to assert that live wording, and the remaining
section heading was changed from “What we will extract” to “What we'll read.”

## 2026-07-30 — Personalize buttons inherit one visit scope

### Defect

The unresolved-warning “Open student” button reused an explicit key after its
view had been left and re-entered. Streamlit can retain that unmounted key as
ordinary session state, but buttons reject any application-visible value under
their key when remounted. Earlier corrections manually added the view revision
to selected decision buttons and therefore left every unlisted button exposed.

### Resolution

- Wrap the production Personalize renderer in one transparent view scope.
- Automatically prefix every button key, including buttons rendered through
  columns and nested helpers, with the current Personalize visit revision.
- Require every Personalize button to supply a stable semantic action key.
- Remove manually assembled revision fragments from individual buttons.
- Cover all current actions, including student navigation, bulk and per-item
  recommendations, editing, ownership, removal, school-provided overrides,
  parent-added items, unresolved navigation, and bottom navigation.

### Testing finding

The first real-render AppTest completed before the fix because AppTest removed
the orphaned value when the button unmounted, unlike the deployed session that
retained it. The strengthened test asserts the required rendered identity
change across the same view round trip. It failed before the fix on x86 run
`30596417144`, proving the unscoped identity independently of whether AppTest
happens to preserve the orphan.

### Architecture

No item interpretation, matching, money path, optimizer, or approval-gate
behavior changed.

## 2026-07-30 — Personalize and submission share one decision truth

### Defect

The Personalize counts treated both accepted AI recommendations and submitted
parent edits as completed, while submission confirmed only the AI-accepted
set. A parent-edited row therefore disappeared from the decision screen and
returned as pending at the boundary to plan building.

Review groups also used positional IDs such as `review-flag-1`. Removing an
earlier group renumbered every later group, allowing an acknowledgment for one
item to attach to a different untouched item. The untouched row remained in
`review_items`; only the screen's derived group filtering hid it.

### Resolution

- Derive each review-group ID from its stable source review-row membership
  instead of its position.
- Preserve separate durable outcome sets for accepted recommendations and
  parent edits.
- Derive their union once as the completed-decision set.
- Use that exact set for both Personalize counts/rendering and submission's
  `review_status` confirmation.

### Failing-before evidence

- x86 run `30596898242` showed that removing the first flagged item hid the
  untouched second item because its positional group ID shifted.
- x86 run `30597037538` showed that a submitted parent edit disappeared from
  the screen but was still treated as pending at submission.

The first post-fix x86 run (`30597282371`) retained the removed pencils row and
correctly named only sticky notes at the gate. One assertion had concatenated
both regions and mistaken the retained removal record for a gate blocker; it
was narrowed to the gate's exact rendered line.

### Architecture

The change is deterministic review-state identity and consumption only. No
model call, matching, money path, optimizer, gate condition, or BR threshold
changed.

## 2026-07-30 — Personalize decision actions remain visible after reruns

### Objective

Make recommendation approval and item-or-quantity editing visibly take effect
without making a parent reopen a collapsed Summary decision panel.

### Diagnosis

The action callbacks were not navigating to Summary and were not losing their
state. A production-shaped x86 AppTest confirmed that both the approval set and
the selected student or classroom were updated correctly. The apparent failure
was the unkeyed Summary decision expander: every action causes a Streamlit
rerun, the expander returned to its hard-coded collapsed state, and the editor
or remaining decision was hidden. The already-owned action looked different
because it also created a visible row in the separate out-of-cart block.

### Work completed

- Gave each student's or classroom's Summary decision disclosure a stable key
  and durable open state.
- Reused the same open-state mechanism as the in-cart item disclosures.
- Kept the decision disclosure open after approving one recommendation or
  opening the item editor, while leaving it collapsed on first arrival.
- Added production-shaped x86 coverage for student and classroom approval,
  editing and submission, already-owned, removal, and entry-scoped bulk
  approval.
- Retained the existing coverage for optional-item restoration,
  school-provided overrides, package-count edits, in-cart quantity changes,
  out-of-cart restoration, parent-added items, and unresolved-plan blocking.

### Verification boundary

The Windows ARM64 suite exercises deterministic and recorder-based behavior but
skips Streamlit AppTest because Streamlit is not installed on that platform.
The open-state and real callback lifecycle require the GitHub Actions x86 run.

### Architecture

No extraction, matching, pricing, optimizer, gate, or business-threshold
behavior changed.
## 2026-07-31 — Matching timeout recovery and operational timing

### Objective

Prevent a live semantic-matching timeout from stranding a parent after
Personalize, preserve completed work for retry, and leave enough timing evidence
to diagnose the next service failure.

### Diagnosis and decisions

- The deployed cart failed with `APITimeoutError` after matching 19 of 26 item
  types. Matching still used the general 30-second request ceiling even though
  the frozen Maple capture required 19.808 seconds.
- This is the third operation found running close to an operational ceiling:
  text extraction previously reached the 60-second boundary, and Machias vision
  extraction took 113.23 seconds against its former 120-second limit.
- Added BR-74: semantic matching now receives a 90-second request ceiling. This
  is about 4.5 times the frozen observed duration and remains below the
  three-minute rendered-page vision allowance.
- Verified that deterministic structured matching over the frozen confirmed
  Maple envelopes preserves the $109.83 zero-interrupt baseline. Stocking out
  `VD-GLU-VB-006` still produces $109.18 and one major-substitution approval.
- The existing offline demo switch is not a model-reading fallback: it replaces
  structure detection and extraction as well as matching. Its built-in two-list
  cart is $69.49, and the glue-stick stockout does not trigger an approval.
- Proposed, but did not implement, a timed-out-batch fallback: retain successful
  model batches, use deterministic structured matching only for the failed
  batch, and route those needs to grouped low-confidence review.

### Work completed

- Applied the matching-specific timeout to every structured suitability request.
- Logged elapsed wall time, the configured limit, need count, and candidate count
  for every matching batch on success and failure.
- Logged whole-cart elapsed time and confirmed-input counts on success and
  failure, with the active traceback on failure.
- Added exception logging to the broad structure and extraction handlers that
  preserve partial work.
- Replaced the dead-end failure state with plain-language recovery text and a
  `Try again` action. Retry reuses the confirmed extraction envelopes and parent
  Personalize decisions; it does not repeat reading or review.
- Removed the duplicated combining narration and made the opening and subsequent
  matching progress totals come from the same grouped-needs count.

### Files changed

- `agent/rules.py`
- `agent/match.py`
- `agent/pipeline.py`
- `agent/telemetry.py`
- `app.py`
- `tests/test_performance.py`
- `tests/test_app.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Focused matching, pipeline, app, frozen Maple, and provider tests: 176 passed.
- Full Windows ARM64 suite: 469 passed, 1 skipped.
- The skipped module is the real Streamlit AppTest suite; its new retry test runs
  on the x86 GitHub Actions runner.

### Problems or limitations

- Transport fallback for a timed-out matching batch remains unimplemented pending
  approval. A transport timeout can still stop the current build, but the parent
  can now retry without losing completed setup or review work.
- Offline demo mode cannot simultaneously show model-assisted reading and provide
  deterministic matching-only reliability; those concerns are currently coupled.

### Recommended next step

Review and approve or reject the timed-out-batch deterministic fallback before
changing matching or gate behavior.

## 2026-07-31 — Production-shaped retry AppTest setup

### Finding and correction

- The first x86 run for cart retry failed at the required three-second AppTest
  ceiling. The inline test rebuilt the entire frozen Maple plan on every
  Streamlit rerun and then rendered Summary; production caches a completed plan
  instead of recreating the fixture during widget interaction.
- Corrected the AppTest setup to construct its deterministic completed result
  once in session state and to preserve the production `result` and `screen`
  transitions across reruns. The timeout remains three seconds.
- The next x86 run exposed that `setdefault("screen", "working")` could not
  override `_initialize_state()`'s first-screen default. The test now enters
  Working exactly once under an initialization marker, then leaves subsequent
  navigation entirely to production.

### Testing performed

- First x86 evidence: run `30658498286`, one AppTest timeout failure.
- Second x86 evidence: run `30658924071`, the test remained on Intake and never
  invoked the cart attempt.
- Full Windows ARM64 suite after the fixture correction: 469 passed, 1 skipped.

## 2026-07-31 — Deferred matching-batch recovery and recording path

### Recording-path clarification

- The exact frozen Maple results — $109.83 with zero interrupts and $109.18
  with one major-substitution approval after stocking out `VD-GLU-VB-006` —
  use frozen confirmed extraction envelopes plus `StructuredSuitabilityJudge`
  in the test harness.
- The deployed application has no mode that combines live model-assisted
  extraction with deterministic matching only.
- The debug-only offline demo switch is not that mode: it replaces document
  structure detection and extraction as well as matching. It therefore does
  not demonstrate the language model reading a real list and does not preserve
  the frozen Maple numbers.
- A recording that needs model-assisted reading must use the live provider path,
  now protected by BR-74's 90-second matching-request ceiling.

### Deferred future work — matching transport fallback

- No fallback behavior was implemented in this pass.
- Recommended design: retain every successfully completed semantic-matching
  batch; if one batch times out or has a connection failure, run the existing
  deterministic structured suitability judge only for that failed batch; mark
  the affected needs as fallback-derived; and route those affected needs to one
  grouped low-confidence review rather than silently accepting them or calling
  them unavailable.
- Retry should resume from the saved confirmed requirements, parent decisions,
  and successful matching batches. It should not repeat extraction, review, or
  already-completed matching work.
- The live failure screen had reported progress at 19 of 26 item types across
  four concurrent matching batches. Because completed matching results were not
  persisted, retry discarded that completed work and restarted matching from
  the confirmed requirements.

### Files changed

- `JOURNAL.md`

### Testing performed

- Documentation-only clarification; no application behavior changed and no test
  suite was run for this entry.

## 2026-07-31 — Shopping-decision boundary and approval context

### Objective

Keep the post-cart decision screen limited to choices about what to buy, make
its prices understandable before Summary, and simplify unavailable-item handling
for the prototype.

### Decisions made

- Retired `required_unavailable` as an FR-26 interrupt. A required item outside
  the selected store and fulfillment scope remains an explicit incomplete-cart
  gap under “Items to buy elsewhere,” but the parent is no longer asked to
  change permitted stores or re-plan from the decision screen.
- Moved low-confidence extraction out of the gate. Personalize already has the
  source line, confidence-derived issue, and correction controls; only
  low-confidence catalog matching remains a post-cart decision.
- The five defined gate conditions are now budget exceeded, major substitution,
  brand-lock break, attribute choice, and low-confidence catalog match. Four are
  reachable through production today because FR-17 filters brand-lock-breaking
  candidates before the gate can see them.

### Work completed

- Removed unavailable-item and extraction-interpretation interrupt generation.
- Kept required gaps visible and incomplete without offering a decision.
- Added current-plan context to Decisions to review: total cost, item count,
  store count, and a separate items-to-buy-elsewhere block.
- Catalog options now display their exact selected line price rather than a
  cart delta. A source-it-yourself option says plainly that no product will be
  purchased in this cart.
- Low-confidence match decisions now expose their blocked catalog candidates
  and exact prices instead of generic correction-only options.
- Added Personalize-style card actions. Approving selects the recommendation;
  changing returns to the source-backed Personalize item; already-owned uses
  the existing Personalize transition and rebuilds from confirmed rows.
- Pending decisions retain bordered-card weight; resolved decisions render as
  quiet rows.

### Source-text finding

- The checked-in evidence contains `1 box | Ziploc quart gallon sized`. The
  contradictory `quart gallon` wording is therefore present in the stored
  source evidence. The spelling `zided` does not occur in the repository and
  could not be verified from the deployed session state.

### Files changed

- `BRD.md`
- `agent/gate.py`
- `agent/pipeline.py`
- `agent/approval_options.py`
- `app.py`
- `tests/test_gate.py`
- `tests/test_pipeline.py`
- `tests/test_maple_cart.py`
- `tests/test_approval_options.py`
- `tests/test_security.py`
- `JOURNAL.md`

### Testing performed

- Focused gate, pipeline, frozen Maple, approval presentation, app, and security
  tests passed during implementation.
- Full Windows ARM64 suite: 470 passed, 1 skipped. The skipped module is the
  real Streamlit AppTest suite and runs on the x86 GitHub Actions workflow.

### Remaining limitation

- The brand-lock-break interrupt branch remains unreachable through production
  matching and is unchanged in this pass.

## 2026-07-31 — Cart-decision controls and attribute vocabulary

### Objective

Keep the post-match screen limited to stocked-product choices and prevent safe
source/catalog synonyms from creating false substitution decisions.

### Work completed

- Removed Personalize actions from shopping-decision cards. Each active
  product card now presents the list request, stocked choices with actual
  prices, a source-it-myself choice, and one explicit `Approve selection`
  action. Budget-plan controls remain separate.
- Required each visible product selection to be approved before the batched
  continue action can apply it.
- Amended BR-13's deterministic attribute normalization with field-specific
  safe synonyms. Fine-tip wording now matches catalog `fine`; pencil-top and
  cap erasers now share `cap`; existing ruling aliases were centralized; and
  safe tip and material vocabulary was audited and canonicalized without
  merging genuinely different products.
- Made every shopping-decision title and recommendation branch on the actual
  interrupt kind. Matching reasons can explain the decision but can no longer
  rename a major substitution as an attribute choice.
- Kept the gate conservative when only one mismatching stocked product exists.
  The parent still chooses between buying it and sourcing it independently;
  the card no longer implies that several attribute variants are available.

### Attribute-vocabulary audit

- Ruling: `wide-ruled`, `wide ruled`, and `wide ruling` map to `wide`; the
  equivalent college-ruled forms map to `college`.
- Tip: `fine tip` and `fine point` map to `fine`; ultra-fine and chisel forms
  are canonicalized within their own distinct values; blunt and rounded tips
  map to `blunt`.
- Eraser style: pencil-top, pencil-cap, cap-eraser, and arrowhead-cap wording
  map to catalog style `cap`. Block and kneaded erasers remain different.
- Material: `poly` and `polypropylene` map to catalog material `plastic`.
- Size measurements and approximation words were already canonicalized;
  numeric tab counts and sharpening booleans were already typed and needed no
  synonym rule.

### Named finding — sixth defined-but-unconsumed mechanism

The parent-facing `item_fulfillment_preference` behind “Are extra items
acceptable?” is collected on `Requirement`, retained on the Personalize row,
and then dropped when aggregation constructs `UnitNeed`. Neither matching nor
optimization can read it. It is the sixth mechanism found defined but
unconsumed, and the second parent preference lost at the Requirement-to-
`UnitNeed` seam after `brand_hint`.

Two parent preferences dying at the same boundary is a structural seam, not
two isolated UI defects. Future work should define an explicit set of parent
matching and package preferences carried by `UnitNeed`, then make every
consumer declare which fields it uses. This pass records the finding only;
package-selection behavior remains deferred.

### Files changed

- `BRD.md`
- `agent/rules.py`
- `agent/schema.py`
- `agent/normalize.py`
- `agent/match.py`
- `app.py`
- `tests/test_aggregate.py`
- `tests/test_normalize.py`
- `tests/test_match.py`
- `tests/test_gate.py`
- `tests/test_approval_options.py`
- `tests/test_streamlit_lifecycle.py`
- `JOURNAL.md`

### Testing performed

- Exact synonym matches create no gate interrupt.
- Genuine fine-versus-chisel and cap-versus-block changes still create their
  respective major-substitution and attribute-choice interrupts.
- The production cart-decision renderer has an x86 AppTest covering the single
  approval action and the absence of Personalize controls.
- Full Windows ARM64 suite: 475 passed, 1 skipped. The skipped AppTest module
  runs in the x86 GitHub Actions workflow.

### Remaining work

- `item_fulfillment_preference` remains intentionally unconsumed pending an
  optimizer-scoped design.
- Brand-lock-break remains unreachable through production matching.

### Recommended next step

Rebuild the Kevin session after deployment and confirm that only its genuine
low-confidence catalog-match decision remains.

## 2026-07-31 — Verify classroom scaling and remove scope jargon

### Objective

- Diagnose a live report that a classroom list marked per student retained its
  source quantities, prove whether BR-33 reached cart arithmetic, and remove
  internal `individual supply` / `shared supply` wording from Personalize.

### Work completed

- Traced classroom size from setup into `PipelineSession.student_counts` and
  the parent scope choice from extraction stamping through confirmed
  requirements.
- Confirmed BR-33 is consumed in deterministic aggregation: package contents
  are normalized first, then per-student quantities are multiplied by the
  classroom count; whole-class quantities are not multiplied.
- Added a production-path regression using the same cached-extraction pipeline
  entry point as the working screen. For a 20-student classroom, 1 four-count
  glue-stick pack, 10 pencils, and 2 three-count sticky-note packs per student
  become cart needs of 80, 200, and 120 units.
- Removed `individual supply` and `shared supply` suffixes from Personalize item
  names and its Summary item labels. The underlying scope data and calculation
  remain unchanged.

### Decisions made

- No quantity logic changed because the final cart already scaled correctly.
  The misleading 1 / 10 / 2 display was the Personalize source-reading view,
  not the aggregated shopping-plan quantity.
- This is not a seventh defined-but-unconsumed mechanism: `supply_scope` is read
  by `aggregate_requirements`. The scope is not retained on `UnitNeed` after
  multiplication, so a future plain-language explanation would require adding
  calculation provenance rather than moving or repeating the multiplication.
- BR-33 was not amended.

### Problems or limitations

- The requested arithmetic regression could not honestly be made to fail
  before the fix because the production cart already contained the multiplied
  quantities. The parent-copy regression did fail first on the leaked scope
  suffix and passed after its removal.
- The final plan does not yet explain a scaled line as, for example, `10 for
  each of 20 students = 200 needed`; that wording was requested as a proposal,
  not an implementation in this pass.

### Files changed

- `app.py`
- `tests/test_app.py`
- `JOURNAL.md`

### Testing performed

- `py -3.12-arm64 -m pytest -q tests/test_app.py -k "classroom_per_student_scope_reaches_the_production_cart or personalize_item_names_do_not_expose_supply_scope_codes"`
  - Before copy fix: cart regression passed; scope-copy regression failed.
  - After copy fix: both passed.
- `py -3.12-arm64 -m pytest -q`
  - `477 passed, 1 skipped in 13.97s`.

### Remaining work

- If approved later, retain enough BR-33 provenance after aggregation to show
  the class-size multiplication once on the shopping plan without repeating an
  internal scope label on every Personalize item.

### Recommended next step

- Verify the same classroom session in the deployed x86 app and confirm that
  the shopping-plan line shows the scaled `needed` quantity while Personalize
  no longer shows the internal scope suffix.

## 2026-07-31 — Individual budgets no longer pool across entries

### What changed

- Traced the individual-budget path from setup through optimization and the
  approval gate. Setup retained each allocation but also summed them into
  `budget_total`; the gate consulted only the summed total, so one entry's
  unused allocation could silently hide another entry's overage.
- Added one deterministic per-entry cost and overage calculation in
  `agent/optimize.py`. The initial plan and catalog-change replan now pass the
  selected budget mode and allocations to the same gate consumer.
- Added an E-22 approval whenever any individual allocation is exceeded,
  including the affected entries and exact overages. Authorizing the increase
  raises only those entries; other allocations remain unchanged.
- Removed the pooled `Budget remaining` presentation from individual-budget
  summaries and exports. Each entry now reports its own amount left or over.
- Simplified the shopping-plan screen: removed catalog-field diagnostics and
  checklist reset copy, made supporting detail collapsed, made fulfillment
  explicit on every store card, and separated the checkmark, product, student,
  and price columns.

### Defect finding

- This was another split-consumer budget defect: per-entry allocations were
  used for cost attribution but not by the approval boundary. The existing
  regression asserted a cart that exceeded the sum of all allocations, so it
  exercised only the combined condition and could not catch a masked
  individual overage.
- The separate deployed cart-build crash reported in the same pass was not
  diagnosable from the request because no exception or Streamlit log was
  included. It remains explicitly unresolved rather than being attributed to
  the budget defect without evidence.
- The first x86 run exposed another production-shape fixture gap: the shopping
  plan AppTest omitted the required `budget_mode` value even though setup
  always writes it before production can reach the summary. The fixture was
  corrected to represent combined-budget intake; the application contract was
  not weakened to accept the impossible state.

### Testing performed

- Added a production pipeline regression where one entry is over, another is
  under, and the cart is below the summed allocations. It failed before the
  fix with zero interrupts and passes afterward with `budget_exceeded`.
- Added coverage that a parent-authorized individual increase changes only the
  over-budget allocation and clears the shortfall.
- `py -3.12-arm64 -m pytest -q`
  - `479 passed, 1 skipped in 16.23s`.

### Remaining work

- Obtain the deployed crash traceback or Streamlit log tail and reproduce that
  exact cart-build failure before changing its handler or timeout behavior.

## 2026-07-31 â€” Personalize now shows classroom totals

### What changed

- Traced BR-33 from the mandatory classroom choice through extraction and the
  cart. The selected `individual` scope was stored correctly and aggregation
  multiplied it correctly, but Personalize formatted the raw per-student
  `SupplyItemReview.required_quantity` before that aggregation boundary.
- Personalize now derives its displayed quantity from the same saved classroom
  count and scope. A five-student list with 1 pack of glue sticks, 10 pencils,
  and 2 packs of sticky notes displays 5 packs, 50 pencils, and 10 packs.
- Stored review quantities remain per student so aggregation still multiplies
  exactly once. When a classroom row is opened, its editor says `Quantity for
  each student` and names the resulting class total.

### Defect finding

- The prior end-to-end BR-33 test proved only that the final cart scaled. It did
  not render Personalize, so it could not detect that the parent-facing review
  showed unscaled values even while the later cart math was correct.

### Testing performed

- Added an ARM64 regression against the exact five-student example and verified
  that display formatting does not mutate the stored quantities.
- Added an x86 AppTest that renders the production Personalize screen, checks
  all three class totals, and verifies the quantity editor remains per student.
- `py -3.12-arm64 -m pytest -q`
  - `480 passed, 1 skipped in 14.55s`.

### Remaining work

- The new real-render AppTest requires the x86 GitHub Actions runner because
  Streamlit AppTest is unavailable in the local ARM64 environment.

### x86 follow-up

- The first x86 run rejected the new fixture before the screen rendered because
  it supplied a nonexistent `Requirement.brand` field. Production stores that
  source-derived value in `brand_hint`; the fixture now uses the real schema
  field rather than weakening validation.
- The second x86 run showed that glue sticks and sticky notes correctly render
  as decision-card headings, while pencils render as a settled-row expander.
  The browser test now reads each item from the production surface where it is
  actually displayed instead of assuming every item is an expander.
