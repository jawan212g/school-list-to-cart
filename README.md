# Ready, Set, School

**One list in. One cart out. One trip.**

Ready, Set, School turns school supply lists into an optimized multi-store shopping
plan, with a human approval gate for the decisions a parent should actually make.

**Team 6 — BUKD-X500 Agentic AI Systems**
Ian Demroff · Sarah Fritschy · Jawan Goodspeed · Marwa Gujarathi · Abhishek Singh

## What Ready, Set, School does

Upload or paste one supply list per child. Set a budget and a shopping mode. The agent
extracts the requirements, aggregates them across children, matches them to products,
builds the cheapest compliant cart across a simulated four-store catalog, and stops to
ask you whenever a decision falls outside its limits.

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
endpoint has a verified image-capable model; otherwise the app rejects JPG and PNG
lists with a clear message. Streamlit secrets take precedence over environment
variables.

## Tests

```
pytest -q
```
