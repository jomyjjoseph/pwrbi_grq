import os
import pandas as pd
import streamlit as st
from groq import Groq

# --- API Key Handling ---
# First try from Streamlit Cloud secrets
if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    # Fallback for local development
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

    # Cleaning instructions
    user_prompt = st.text_area(
        "Describe the cleaning changes you want (e.g., 'Remove characters after comma in column Name')"
    )

    if st.button("Apply Changes") and user_prompt:
        try:
            # Prepare AI prompt
            prompt_text = f"""
            You are a data cleaning assistant.
            I have the following data (first 10 rows shown below):
            {df.head(10).to_csv(index=False)}

            Instruction from user:
            {user_prompt}

            Explain in plain English how to modify the DataFrame in pandas code,
            and only return Python code that modifies `df` in place.
            """

            # Send request to Groq
            response = client.chat.completions.create(
                model="llama3-8b-8192",  # Free LLaMA 3 model
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0
            )

            raw_code = response.choices[0].message.content

            # --- Sanitize AI output ---
            clean_code = raw_code.replace("```python", "").replace("```", "").strip()
            clean_code = "\n".join(line for line in clean_code.splitlines() if line.strip())

            # Show generated code for review
            st.write("### Generated Code")
            st.code(clean_code, language="python")

            # Execute the generated code safely
            try:
                exec(clean_code, {"df": df, "pd": pd})
            except Exception as e:
                st.error(f"Error executing AI code: {e}")
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
