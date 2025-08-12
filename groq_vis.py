import os
import re
import textwrap
import pandas as pd
import streamlit as st
from groq import Groq

# --- API Key Handling ---
if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    st.error("GROQ API key not found. Please set it in Streamlit secrets (Cloud) or .env (local).")
    st.stop()

# Initialize Groq client
client = Groq(api_key=api_key)

# --- Streamlit UI ---
st.title("Excel Data Cleaner with AI Prompts (Groq Version)")

uploaded_file = st.file_uploader("Upload Excel/CSV file", type=["xlsx", "csv"])

if uploaded_file is not None:
    # Read uploaded file
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write("### Original Data")
    st.dataframe(df)

    user_prompt = st.text_area(
        "Describe the cleaning changes you want (e.g., 'Remove characters after comma in column Name')"
    )

    if st.button("Apply Changes") and user_prompt:
        try:
            # --- Inject safety instructions into the prompt ---
            prompt_text = f"""
            You are a safe and reliable data cleaning assistant.
            Work ONLY with pandas code that modifies `df` in place.

            SAFETY RULES:
            - Always check if a column exists before modifying or dropping it.
            - Handle NaN values safely to avoid errors.
            - When applying string operations, convert to string first (e.g., astype(str)) but only for the specific column you modify.
            - Do not change number, percentage, or time formats unless explicitly instructed.
            - When parsing dates, always use:
              pd.to_datetime(df['col'].astype(str).str.strip(), errors='coerce')
              (Do NOT hardcode a format unless explicitly given by the user)
            - Avoid hardcoding sample values; generalize the solution.
            - Return ONLY Python code that modifies `df` in place. No explanations.
            - Do not include unnecessary indentation at the start of code lines unless required by Python syntax.

            Here is the first 10 rows of data:
            {df.head(10).to_csv(index=False)}

            User instruction:
            {user_prompt}
            """

            # Send request to Groq
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0
            )

            raw_code = response.choices[0].message.content

            # --- Sanitize AI output ---
            raw_code = raw_code.replace("```python", "").replace("```", "").strip()

            # Keep only valid Python lines
            python_lines = []
            for line in raw_code.splitlines():
                if re.match(r'^\s*(df|pd|import|from)\b', line):
                    python_lines.append(line)

            # Normalize indentation
            clean_code = textwrap.dedent("\n".join(python_lines)).strip()

            # --- Auto-fix risky date parsing ---
            clean_code = re.sub(
                r"pd\.to_datetime\(([^,]+),\s*format=.*?\)",
                r"pd.to_datetime(\1.astype(str).str.strip(), errors='coerce')",
                clean_code
            )

            # Show generated code for review
            st.write("### Generated Code")
            st.code(clean_code, language="python")

            # --- Pre-execution safeguard for AI code ---
            try:
                exec(clean_code, {"df": df, "pd": pd, "pd_notna": pd.notna})
            except Exception as e:
                st.error(f"Error executing AI code: {e}")
                st.code(clean_code, language="python")
                st.stop()

            # Show cleaned data
            st.write("### Cleaned Data")
            st.dataframe(df)

            # Download button
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Cleaned CSV",
                data=csv,
                file_name="cleaned_data.csv",
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"Error: {e}")
