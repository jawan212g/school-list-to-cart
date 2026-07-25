"""School List-to-Cart Agent — placeholder.

This file exists so the app can be deployed before the build starts.
Block 2 onward replaces it. See BRD.md.
"""

import streamlit as st

st.set_page_config(page_title="School List-to-Cart Agent", page_icon="📝")

st.title("School List-to-Cart Agent")
st.caption("Team 6 — BUKD-X500 Agentic AI Systems")

st.info("Deployment placeholder. The application is under construction.")

st.markdown(
    """
    **What this will do**

    Upload or paste one supply list per child, set a budget, and the agent will
    extract the requirements, aggregate them across children, match them to products,
    build the cheapest compliant cart across a simulated four-store catalog, and stop
    to ask you whenever a decision falls outside its limits.

    The catalog is simulated and the stores are fictional. Checkout is simulated and
    no payment information is ever collected.
    """
)

with st.expander("Deployment check"):
    st.write("If you can read this, the app is deployed and serving.")
    key_present = "OPENAI_API_KEY" in st.secrets
    st.write(f"API key configured: {key_present}")
