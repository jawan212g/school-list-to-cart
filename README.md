# Ready, Set, School

**One list in. One cart out. One trip.**

Ready, Set, School turns school supply lists into an optimized multi-store shopping
plan, with a human approval gate for the decisions a parent should actually make.

**Team 6 — BUKD-X500 Agentic AI Systems**
Ian Demroff · Sarah Fritschy · Jawan Goodspeed · Marwa Gujarathi · Abhishek Singh

## What Ready, Set, School does

Upload or paste one supply list per student. Set a budget and shopping preferences. PDF pages
are rendered as images so the reading step can preserve tables and multi-column
layouts. For district-wide documents, the parent first chooses the grade, teacher, or
named section to read. The app then proposes a cart from a simulated four-store
catalog and asks the parent to check the exact source lines and resolve flagged
decisions.

A language model reads and interprets list content. Deterministic Python code handles
quantities, package choices, prices, tax, fees, and totals. The reading can be wrong;
the calculated catalog arithmetic is exact for the confirmed interpretation and
seeded data.

## Important

The product catalog is **simulated**. Stores are fictional. Prices, stock, and fees are
representative rather than live, so cost figures are directional and cannot be read as
real retailer quotes. Checkout is simulated; no payment information is ever collected.

## Specification

`BRD.md` is the specification of record. Requirements are numbered FR-##, business rules
BR-##, and edge cases E-##.

## Running locally

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# add your API key to .streamlit\secrets.toml
streamlit run app.py
```

The default configuration uses OpenAI with `OPENAI_API_KEY` and the app's existing
text-and-vision model. To use an OpenAI-compatible provider such as IU's Kelley GPT
API, configure `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_TEXT_MODEL` in Streamlit
secrets or environment variables. Configure `LLM_VISION_MODEL` only when that
endpoint has a verified image-capable model; otherwise the app rejects PDF, JPG, and
PNG lists with a clear message. Streamlit secrets take precedence over environment
variables.

## Tests

```
pytest -q
```
