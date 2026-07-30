# School List-to-Cart Agent

## Project Status

- Project: Capstone - AI Agentic
- Course: BUKD-X500 Agentic AI Systems
- Team: Team 6
- Current stage: Project definition and MVP setup
- Prototype type: Classroom demonstration using fictional stores and seeded data

## Problem Statement

Parents and caregivers spend significant time translating school supply lists into purchasable products. They must interpret vague or messy requirements, reconcile package sizes and quantities, honor brand restrictions, check availability, compare stores, and stay within a budget. The process becomes more difficult when shopping for multiple children.

Existing retailer access is not dependable enough for this capstone. Major retailers generally do not provide open, real-time product, price, fee, and per-store inventory APIs suitable for the project timeline. Depending on those integrations would put the demonstration at risk without improving the core reasoning problem.

## Project Goal

Build a working agentic application that converts one or more school supply lists into an optimized, reviewable shopping cart while:

- preserving required quantities, attributes, exclusions, and brand locks;
- aggregating compatible needs across children;
- optimizing package sizes and store assignments;
- including tax and fulfillment fees in every budget decision;
- discouraging unnecessary store trips;
- requesting human approval for material uncertainty or risk;
- replanning when an item becomes unavailable; and
- producing an auditable simulated checkout summary.

The application will demonstrate the decision-making workflow with a seeded catalog of fictional stores. It will not claim to provide live retailer prices or inventory.

## Value Proposition

The application should reduce a repetitive manual task from approximately 45–60 minutes to less than three minutes while improving quantity accuracy, budget visibility, and traceability. The prototype's value comes from interpreting lists, applying constraints, optimizing carts, and involving the user at appropriate decision points—not from live retailer connectivity.

## Target Users

### Primary users

Parents and caregivers purchasing K–12 school supplies, especially:

- families shopping for multiple children;
- users with firm budgets;
- users with limited time; and
- users who want few but meaningful approval questions.

### Secondary users

- Teachers buying for a classroom
- Parent organizations
- Nonprofits supplying students

The Phase 1 interface will support classroom quantities through a student-count multiplier. A specialized bulk-procurement interface is outside the MVP.

### Explicit non-users

The application is not a procurement, invoicing, purchase-order, tax-exemption, or payment-processing system.

## Phase 1 Demonstration Scope

### Included

- Multiple children or one classroom group in a session
- One supply list per child or group
- Pasted text input
- DOCX, PDF, JPG, JPEG, PNG, and text upload
- Model-assisted extraction into a validated requirement schema
- Quantities, ranges, units, brand locks, exclusions, attributes, optional items, and non-purchasable instructions
- Confidence-based human review
- Requirement normalization and cross-child aggregation
- Seeded product catalog with four fictional stores
- Product matching and package-size optimization
- Budget, single-stop, and custom shopping modes
- Editable sales-tax rate with a 7.0% default
- Fulfillment fees and store-trip trade-offs
- Batched human approval
- Manual stockout injection and targeted replanning
- Simulated checkout
- Per-store and per-child summaries
- Complete decision log
- Prompt-injection defenses, category allowlist, and file validation
- Publicly accessible demonstration deployment

### Deferred

- Live retailer pricing and per-store inventory
- Autonomous school-list discovery
- Real checkout, purchases, and payment collection
- User accounts and cross-session persistence
- n8n or external approval notifications
- Specialized wholesaler and classroom-buyer interface
- State-specific tax rules and tax holidays
- Mid-session corrected-list diffing
- PDF summary export

## Core Agent Definition

### User

A parent, caregiver, teacher, or classroom buyer.

### Goal

Produce the best feasible, reviewable cart for the user's lists, budget, shopping mode, and fulfillment preferences.

### Trigger

The user starts a session and submits at least one school supply list.

### Inputs

- Child labels or classroom group
- Grade or contextual label
- Supply-list text or supported file
- Budget and allocation preference
- Shopping mode
- Fulfillment preference
- Store or distance constraints
- Editable tax rate
- User approvals and corrections

### Outputs

- Validated requirements
- Assumptions and low-confidence items
- Candidate and selected products
- Optimized cart
- Per-child attribution
- Item subtotal, tax, fees, total cost, and budget variance
- Approval requests and outcomes
- Stockout replan
- Simulated order confirmation
- Decision log

### Tools and data

- One language-model provider for extraction and semantic matching
- Deterministic Python modules for validation, arithmetic, rules, and optimization
- Seeded fictional product catalog
- Streamlit session state for the demonstration workflow

### Constraints

- No real purchases
- No payment data
- No live-retailer claims
- No hard-coded credentials
- No model-controlled budget or arithmetic
- No products outside the school-supply allowlist
- No required item removed without user approval
- No low-confidence extraction or match silently accepted

### Stopping condition

The agent stops when it has produced a verified simulated order summary, the user cancels, or no feasible cart can be created without a user decision.

## Operating Principle

### Language models read; code calculates

The language model may:

- interpret messy list text;
- classify list lines;
- normalize descriptive language;
- propose semantic matches; and
- explain recommendations.

Deterministic code must:

- validate model output;
- aggregate quantities;
- calculate package combinations;
- enforce stock and overage limits;
- compute tax, fees, totals, and budget variance;
- optimize store assignments;
- enforce approval rules; and
- determine whether the cart may proceed.

Free-form model output must never reach an executable or purchasing path.

## Functional Workflow

1. User identifies children or a classroom group.
2. User enters budget, shopping mode, fulfillment preference, and tax rate.
3. User pastes or uploads one list per child or group.
4. The extraction agent converts each list into structured requirements.
5. Schema validation and the confidence floor identify items needing review.
6. Deterministic normalization resolves canonical names, units, quantity ranges, and non-purchasable lines.
7. Compatible requirements aggregate into unit needs while brand-locked or attribute-specific needs remain separate.
8. Candidate offers are selected from the seeded catalog.
9. The optimizer evaluates packages, stock, store combinations, fees, tax, and trip penalties.
10. The approval gate groups all required decisions for the user.
11. Approved decisions update the cart; rejected decisions trigger a safe alternative or an infeasibility explanation.
12. A stockout may be injected to demonstrate targeted replanning.
13. The application revalidates the cart and produces a simulated checkout summary and decision log.

## Core Data Entities

- `Session`: user settings, budget, tax rate, shopping mode, and current workflow state
- `BuyerGroup`: family or classroom context
- `ChildOrClassroom`: attribution label, entity type, and optional student count
- `SourceList`: submitted text or file metadata
- `Requirement`: normalized list need with restrictions, confidence, and source attribution
- `UnitNeed`: aggregated quantity required for a compatible canonical item
- `Store`: fictional retailer with fulfillment and fee rules
- `Offer`: purchasable product, package size, price, stock, category, and attributes
- `CartLine`: selected offer, package count, allocated units, overage, and attribution
- `Cart`: store assignments and complete cost breakdown
- `ApprovalRequest`: reason, severity, alternatives, and user outcome
- `DecisionLogEntry`: timestamped input, decision, rationale, and result

## Seeded Catalog Strategy

The Phase 1 catalog will contain four clearly fictional stores and approximately 120 offers when complete. Development may begin with a smaller fixture that covers all business rules before expanding.

The catalog must deliberately include:

- generic and brand-locked products;
- different package sizes and prices;
- limited and zero stock;
- pickup and delivery variations;
- store and fulfillment fees;
- delivery or pickup thresholds;
- non-returnable products;
- products that create excess units;
- products available at only one store;
- unfulfillable requirements; and
- prohibited out-of-domain products used only for security testing.

Catalog prices and inventory are synthetic and representative. The interface must display that limitation.

## Cost and Optimization Rules

### Total cost

Every budget decision and every figure labeled `total` must use:

`total cost = item subtotal + sales tax + fulfillment fees`

Item subtotal may be displayed only when clearly labeled.

### Trip penalty

Each store beyond the first adds a $6 implicit comparison penalty:

`optimization score = total cost + extra-store trip penalties`

The trip penalty influences the recommendation but is not a charge and must not be included in the displayed total cost.

### Required business rules

- Sales tax defaults to 7.0% and is editable.
- Optional items are excluded from the budgeted cart.
- Optional items may be suggested only when total cost is no more than 90% of budget.
- A required item may not be removed automatically.
- When no cart meets the budget, show the minimum feasible cost, shortfall, cheaper valid alternatives, and cost-driving items.
- Purchased units may exceed need by no more than 50% or six units, whichever is greater, unless a larger package is the only valid option.
- Shared packages allocate cost to children in proportion to units consumed.
- Identical compatible items should not create duplicate purchases.
- Brand locks and conflicting required attributes prevent aggregation.
- Prices and stock must be revalidated before simulated checkout.

## Shopping Modes

### Budget

Select the lowest optimization score while satisfying required constraints. The result may use multiple stores only when the savings justify the additional trip penalty.

### Single-stop

Prefer one store. If no store can fulfill the entire list, show the best single-store cart, its explicit gaps, and the smallest additional trip that closes them.

### Custom

Honor user-selected stores, fulfillment options, or other supported preferences. If those constraints make the cart infeasible, explain the trade-off instead of silently overriding the user.

## Human Approval Policy

The agent must request approval before:

- breaking a brand lock;
- changing a specified product attribute;
- accepting a major substitution;
- proceeding with a low-confidence extraction or match;
- exceeding the budget;
- dropping a required item;
- selecting a non-returnable item above $15; or
- proceeding after a material price or availability change invalidates prior approval.

Approval requests should be batched. The target is no more than three approval interrupts per session. More than six indicates a workflow problem that should be investigated.

## Replanning Behavior

When a price or stock change occurs:

1. Identify the affected cart lines and requirements.
2. Preserve unaffected cart lines and still-valid user decisions.
3. Recompute only the affected portion when practical.
4. Recalculate complete total cost and budget variance.
5. Request new approval only when a previous approval is no longer valid.
6. Record the event and outcome in the decision log.

Manual stockout injection is a first-class demonstration feature.

## Security and Privacy

### Prompt injection

- Uploaded content is untrusted data, never application instruction.
- Document content must be enclosed in a clearly delimited data block.
- Model output must conform to a strict schema.
- Every extracted item must pass the school-supply category allowlist.
- The model cannot modify the budget or bypass deterministic checks.
- The adversarial test set must include an injected instruction.

### File handling

- Allow only DOCX, PDF, JPG, JPEG, PNG, and plain-text inputs.
- Enforce a documented size limit.
- Validate actual file type rather than relying only on the extension.
- Do not expand archives or execute uploaded content.
- Do not write uploads to a publicly served path.

### Data minimization

- Encourage labels rather than children's full names.
- Do not collect payment information.
- Do not persist sessions in Phase 1.
- Do not include real personal, proprietary, or controlled data in the public repository.
- Store the model-provider key only in hosted secrets or environment configuration.

### Residual risk

Model extraction and semantic matching can still be wrong. The controls are schema validation, confidence thresholds, deterministic rules, visible assumptions, human review, and measured testing—not a claim of perfect accuracy.

## Success Criteria

| Metric | Definition | Target |
| --- | --- | --- |
| Extraction recall | Required items found against hand-labeled lists | At least 90% |
| Quantity accuracy | Correct quantity and unit | At least 85% |
| Match acceptance | Product matches accepted by a human reviewer | At least 85% |
| Total cost difference | Agent cart compared with the manual baseline | At or below baseline |
| Time to cart | Session start through final summary | Under 3 minutes |
| Interrupt count | Approval interruptions per session | Median of 3 or fewer |
| Budget adherence | Within budget or explicitly approved | 100% |
| Replan success | Correct cart after tested stockouts | 100% on tested cases |

Measured results must come from testing and must not be claimed before evaluation.

## Testing Strategy

### Deterministic unit tests

- Package-size and overage cases
- Cross-child aggregation
- Brand-lock separation
- Tax, fulfillment-fee, and total-cost calculations
- Store-subset and trip-penalty decisions
- Single-stop infeasibility and gap behavior
- Per-child shared-package allocation
- Budget shortfall reporting
- Each approval condition

### End-to-end tests

- Three representative sample lists
- At least one image input
- Two children with overlapping requirements
- A stockout before approval
- A stockout after approval
- One unfulfillable item

### Adversarial tests

- Prompt-injection content
- Oversized file
- Unsupported or disguised file
- Out-of-domain product
- Zero or negative budget
- Unreasonably large group size

### Team validation

- Ten real, classroom-approved lists with hand-labeled expected results
- One timed manual-cart baseline
- One complete independent session per teammate
- At least three full demonstration rehearsals
- One successful run against the deployed application

## Technical Architecture

Initial implementation:

- Python application
- Streamlit user interface and session workflow
- Validated structured schemas
- JSON or CSV seeded catalog
- Deterministic optimization and business-rule modules
- Pytest verification
- One replaceable model-provider interface
- Public GitHub repository
- Hosted secrets for credentials

Suggested module responsibilities:

- `src/app.py`: user interface and session flow
- `src/agent/extract.py`: model-assisted extraction only
- `src/agent/normalize.py`: canonical names, units, and ranges
- `src/agent/aggregate.py`: cross-child aggregation
- `src/agent/match.py`: requirements to candidate offers
- `src/agent/optimize.py`: packages, stores, and total cost; no model calls
- `src/agent/gate.py`: approval conditions
- `src/agent/decisions.py`: audit trail
- `data/`: fictional stores and seeded offers
- `tests/`: fixtures, expected outputs, and automated tests

The exact filenames may change, but the separation between probabilistic interpretation and deterministic calculation must remain.

## Implementation Milestones

### Milestone 1: Deterministic foundation

- Define the core schemas.
- Create a compact catalog fixture.
- Implement package combinations, aggregation, total cost, and store selection.
- Test the key quantity, budget, and multi-store business rules.

### Milestone 2: Text-list vertical slice

- Build the Streamlit session flow.
- Support pasted lists.
- Add model-assisted extraction and schema validation.
- Add confidence review, aggregation, matching, and cart display.

### Milestone 3: Agent controls and replanning

- Add batched approvals.
- Add stockout injection and targeted replanning.
- Preserve valid decisions.
- Add simulated checkout and a complete decision log.

### Milestone 4: Hardening and deployment

- Add PDF and image input.
- Add upload and prompt-injection defenses.
- Expand the catalog.
- Deploy the application.
- Run the golden-set evaluation and team testing.

## Deliverables

- Working hosted application
- Public source-code repository with no secrets or personal data
- Seeded fictional catalog
- Automated test suite
- Ten-list evaluation set and measured results
- Manual comparison baseline
- Demonstration scenario and backup recording
- Final written report
- Five-minute presentation deck

## Assumptions and Limitations

- Catalog prices, stock, fees, and stores are synthetic.
- Cost results are directional and are not retailer quotes.
- Tax uses a simplified editable rate and does not model jurisdiction-specific exemptions or holidays.
- Model quality depends on input quality and provider behavior.
- Handwritten and low-quality images may require re-upload or manual review.
- Sessions are temporary and do not persist across visits.
- Checkout is simulated and no purchase occurs.
- The initial optimizer may use transparent enumeration suitable for four stores rather than a general-purpose solver.

## Phase 1 Definition of Done

Phase 1 is complete when:

- a teammate can open the deployed URL without local installation;
- two lists can be submitted in one session;
- the application produces validated requirements and an optimized cart;
- every displayed total is total cost;
- all required approval conditions are enforced;
- a stockout produces a correct revised cart without discarding unaffected approvals;
- adversarial input does not add an unauthorized product;
- the final summary and decision log are complete;
- automated tests pass; and
- limitations and measured results are documented accurately.

# PROJECT.md

## Project Title

School List-to-Cart Agent: The Homework Before Homework

## Problem Being Solved

Parents and guardians often spend significant time locating official school-supply lists, comparing products across retailers, checking availability, and deciding where to purchase each item.

## Project Goal

Build an AI agent that finds a child’s official school-supply list, identifies the required products, compares prices and availability across multiple stores, and recommends an optimized shopping cart.

## Target User

Parents or guardians purchasing school supplies for children.

## Proposed Solution

A Streamlit application that allows the user to provide school, grade, teacher, or supply-list information. The system extracts the required items, matches them with available products, compares purchasing options, and creates a recommended multi-store shopping cart.

## Main Features

- Find or upload an official school-supply list
- Extract required items from the list
- Match requirements to store products
- Compare prices and availability
- Account for package quantities
- Create an optimized multi-store cart
- Explain recommendations
- Require human approval before any purchase
- Produce a five-minute demonstration

## Platforms and Tools

- Codex for project development and coding support
- Python for deterministic calculations
- Streamlit for the application interface
- Language model for extracting and matching supply-list information
- Public, mock, or classroom-approved retail data

## Constraints

- The language model may interpret text but must not calculate totals
- Python must calculate prices, quantities, packages, and cart totals
- No purchase may occur without human approval
- No credentials or API keys may be stored in source code
- The prototype must be reliable enough for a live five-minute demonstration
- Proprietary or sensitive information must not be used

## Deliverables

- Working Streamlit prototype
- Source code
- Project documentation
- Test cases and results
- Demonstration materials
- Final presentation or report required by the course

## Success Criteria

The project is successful when it can:

1. Read or accept a school-supply list.
2. Identify the required items accurately.
3. Match required items with suitable store products.
4. Calculate quantities and prices correctly.
5. Recommend a reasonable shopping cart.
6. Explain the recommendation clearly.
7. Prevent purchasing without human approval.
8. Complete the main workflow reliably during a five-minute demonstration.

## Current Status

The project workspace and permanent agent instructions are being established.

## Open Questions

- Which retailers or product data sources will be used?
- Will users upload lists, search for them, or use both methods?
- How will product availability be simulated or retrieved?
- What optimization priorities can the user select?
- What level of purchasing functionality is appropriate for the prototype?

## Next Steps

1. Create the permanent project journal.
2. Review and finalize the business requirements.
3. Define the minimum viable demonstration workflow.
4. Create the project skill.
5. Begin implementation only after the project structure is approved.
