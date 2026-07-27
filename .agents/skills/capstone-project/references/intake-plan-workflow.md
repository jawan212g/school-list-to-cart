# Supply-List Intake and Plan-Building Workflow

Preserve this end-to-end workflow when developing or improving intake, extraction, review, matching, optimization, or approval behavior.

## Required stages

Keep these four stages visible and in this order:

1. `Upload and organize my list`
2. `Review extracted items`
3. `Build my shopping plan`
4. `Approve final plan`

Never skip the review stage, including when extraction confidence is high.

## End-to-end flow

1. Accept an uploaded supported file or manually pasted supply-list text.
2. Extract readable text from the source.
3. Use the language model to interpret the text and propose structured school-supply items.
4. Use deterministic code to validate and normalize quantities, units, package sizes, and item attributes.
5. Identify duplicate, ambiguous, incomplete, and low-confidence items.
6. Let the user review and edit the structured list.
7. Send only user-confirmed items to shopping-plan generation.
8. Use deterministic code to evaluate permitted product matches and cart combinations.
9. Apply the user's budget, shopping mode, pickup radius, fulfillment preference, tax rate, retailer preferences, and brand-substitution preferences.
10. Present an explainable recommended shopping plan.
11. Require the user to review and approve the final plan.
12. Perform no live purchase or irreversible action without explicit human approval.

## Supported inputs

Support:

- `.txt`: read text directly.
- `.docx`: extract paragraphs, bullet points, and tables.
- `.jpg`, `.jpeg`, and `.png`: extract visible list content with an image-capable process.
- Manual text entry: process text entered directly by the user.
- `.pdf`: retain the existing BRD-required PDF intake path unless the user explicitly removes it from scope.

Reject unsupported formats with a clear message. Do not claim successful processing unless readable content was extracted.

## Structured supply-item schema

Capture these fields when available:

- `item_name`
- `required_quantity`
- `unit`
- `package_size`
- `brand`
- `brand_required`
- `size`
- `color`
- `material`
- `required_attributes`
- `optional`
- `notes`
- `source_text`
- `confidence`
- `review_status`

Allow the model to propose these fields. Validate numeric values and all shopping-impacting constraints in deterministic code.

## List-cleaning rules

- Separate individual items into individual records.
- Preserve the original source text.
- Combine only clear duplicates.
- Do not combine items with different mandatory attributes.
- Distinguish required attributes from preferences.
- Flag missing quantities.
- Flag ambiguous descriptions.
- Flag uncertain brand, color, size, or package requirements.
- Do not fabricate missing requirements.
- Require user review for low-confidence items.

## Human review controls

Allow the user to:

- approve an extracted item;
- edit the item name;
- edit the quantity;
- edit required attributes;
- delete an incorrect item;
- add a missing item;
- mark an item as already owned;
- mark an item as optional;
- require an exact brand; and
- allow equivalent products.

Do not allow `Build My Plan` to use unresolved required items unless the user explicitly approves proceeding.

## Plan inputs

Build the plan from:

- confirmed supply items;
- budget;
- shopping mode;
- pickup radius;
- fulfillment preference;
- tax rate;
- preferred or excluded retailers; and
- brand-substitution preferences.

## Plan outputs

Display:

- items fulfilled;
- missing items;
- product subtotal;
- taxes;
- fees;
- estimated total;
- budget remaining or budget exceeded;
- number of stores;
- pickup and delivery requirements;
- substitutions;
- items requiring additional review;
- an explanation of the selected plan; and
- a comparison with relevant alternatives.

Perform all arithmetic and optimization in deterministic code.
