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

# --- Keep DataFrame in session state ---
if uploaded_file is not None:
    if "df" not in st.session_state:
        if uploaded_file.name.endswith(".csv"):
            st.session_state.df = pd.read_csv(uploaded_file)
        else:
            st.session_state.df = pd.read_excel(uploaded_file)

    df = st.session_state.df

    st.write("### Current Data")
    st.dataframe(df)

    user_prompt = st.text_area(
        "Describe the cleaning changes you want (e.g., 'Remove characters after comma in column Name')"
    )

    if st.button("Apply Changes") and user_prompt:
        try:
            # --- Updated AI prompt ---
            prompt_text = f"""
            You are a safe and reliable Python data cleaning assistant.

            IMPORTANT:
            - You are working with an existing pandas DataFrame called `df` that is already loaded in memory.
            - You MUST modify `df` **in place** — do NOT reassign it with new data from scratch.
            - Do NOT read files or create new DataFrames unless explicitly told.
            - Do NOT drop all data or reset the index unless explicitly told.
            - Always check if a column exists before modifying or dropping it.
            - Handle NaN values safely to avoid errors.
            - Always convert to string before applying string operations:
              df['col'] = df['col'].astype(str).apply(lambda x: <logic> if pd.notna(x) else x)
            - Never call .upper(), .lower(), .split() directly on a Series — always use .str or .apply as above.
            - Do not change numeric, percentage, or time formats unless explicitly instructed.
            - When parsing dates, always use:
              pd.to_datetime(df['col'].astype(str).str.strip(), errors='coerce')
            - Avoid hardcoding example values — make your logic general.
            - Return ONLY Python code that modifies `df` in place, without explanations or markdown.

            Here are the first 10 rows of the current data:
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
            raw_code = raw_code.replace("```python", "").replace("```", "").strip()

            # Keep only lines that look like Python code
            python_lines = []
            for line in raw_code.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if re.match(r"^[A-Za-z_][A-Za-z0-9_\[\]'\"]*\s*=.*", stripped) or \
                   re.match(r"^(df|pd|if|for|from|import|with)\b", stripped):
                    python_lines.append(line)

            clean_code = textwrap.dedent("\n".join(python_lines)).strip()

            # --- Auto-fixes ---
            clean_code = re.sub(
                r"pd\.to_datetime\(([^,]+),\s*format=.*?\)",
                r"pd.to_datetime(\1.astype(str).str.strip(), errors='coerce')",
                clean_code
            )
            clean_code = re.sub(
                r"df\['(\w+)'\]\.upper\(\)",
                r"df['\1'].astype(str).str.upper()",
                clean_code
            )
            clean_code = re.sub(
                r"df\['(\w+)'\]\.split\('([^']+)'\)\[0\]",
                r"df['\1'].astype(str).apply(lambda x: x.split('\2')[0] if pd.notna(x) and len(x.split('\2'))>0 else x)",
                clean_code
            )
            clean_code = re.sub(
                r"df\['(\w+)'\]\.str\.split\('([^']+)'\)\[0\]",
                r"df['\1'].astype(str).apply(lambda x: x.split('\2')[0] if pd.notna(x) and len(x.split('\2'))>0 else x)",
                clean_code
            )

            def safe_split(match):
                col = match.group(1)
                sep = match.group(2)
                idx = int(match.group(3))
                return f"df['{col}'].astype(str).apply(lambda x: x.split('{sep}')[{idx}] if pd.notna(x) and len(x.split('{sep}'))>{idx} else x)"

            clean_code = re.sub(
                r"df\['(\w+)'\]\.split\('([^']+)'\)\[(\d+)\]",
                safe_split,
                clean_code
            )
            clean_code = re.sub(
                r"df\['(\w+)'\]\.str\.split\('([^']+)'\)\[(\d+)\]",
                safe_split,
                clean_code
            )

            # Show generated code for review
            st.write("### Generated Code")
            st.code(clean_code, language="python")

            # --- Execute with friendly error handling ---
            try:
                exec(clean_code, {"df": df, "pd": pd, "pd_notna": pd.notna})
                st.session_state.df = df
                st.success("Changes applied successfully!")
            except Exception as e:
                error_message = str(e).lower()

                if "can only use .str accessor" in error_message:
                    user_friendly = (
                        "Your instruction is trying to use a text operation "
                        "on a column that is not plain text. "
                        "You may need to first convert it to text before making this change."
                    )
                elif "keyerror" in error_message:
                    user_friendly = (
                        "You mentioned a column name that doesn't exist in the data. "
                        "Please check the exact name and try again."
                    )
                elif "valueerror" in error_message:
                    user_friendly = (
                        "Your change doesn't match the data format. "
                        "Please adjust your instructions."
                    )
                else:
                    user_friendly = (
                        "Something went wrong while applying your change. "
                        "Please review your instructions and try again."
                    )

                st.error(user_friendly)
                st.info("No changes have been made. Please correct your prompt and try again.")
                st.code(clean_code, language="python")
                st.stop()

            # Show updated dataframe
            st.write("### Updated Data")
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
            st.error(f"Unexpected problem: {e}")
