import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from PIL import Image
import json

# --- 1. SETUP ---
st.set_page_config(page_title="Order Flag Scanner", layout="centered", page_icon="🚩")

API_KEY = st.secrets["GEMINI_API_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

genai.configure(api_key=API_KEY, transport="rest")
model = genai.GenerativeModel('gemini-3-flash-preview')
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. DATA HANDLERS ---
def get_data():
    df = conn.read(ttl="0")
    # Convert everything to clean strings to avoid search errors
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    return df

def update_cloud(new_df):
    existing_df = get_data()
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    # Use FullOrder as the unique ID to prevent duplicates
    final_df = combined.drop_duplicates(subset=['FullOrder'], keep='last')
    conn.update(data=final_df)

# --- 3. MODE: COWORKER (SEARCH) ---
def coworker_mode():
    st.title("🔍 Order Lookup")
    st.write("Enter the last 4 digits of the order number.")

    query = st.text_input("Search Order:", placeholder="e.g. 0351")

    if query:
        df = get_data()
        if not df.empty:
            # Search the FullOrder column for the digits entered
            results = df[df['FullOrder'].str.contains(query.strip(), na=False)]

            if not results.empty:
                for _, row in results.iterrows():
                    with st.container(border=True):
                        st.markdown(f"### 🚩 {row['Color']} Flag — #{row['FlagNumber']}")
                        st.write(f"**Truck/Inbound:** {row['TruckID']}")
                        st.caption(f"Full Order ID: {row['FullOrder']}")
            else:
                st.warning(f"No match found for '{query}'.")

# --- 4. MODE: DEV (ADMIN) ---
def dev_mode():
    st.title("⚙️ Admin Dashboard")

    # Password Protection
    if "auth" not in st.session_state: st.session_state.auth = False
    if not st.session_state.auth:
        pw = st.text_input("Password", type="password")
        if st.button("Login") and pw == ADMIN_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        return

    st.subheader("📤 Scan New Sheets")
    files = st.file_uploader("Upload photos", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if files and st.button("🚀 Analyze & Sync"):
        new_rows = []
        with st.spinner("AI Mapping Data..."):
            for f in files:
                img = Image.open(f)
                prompt = """
                Extract the table into JSON format using these keys:
                - 'FullOrder': The long order ID.
                - 'FlagNumber': The small number (usually 1-50).
                - 'TruckID': The inbound code (starts with I or T).
                - 'Color': The color name.
                """
                res = model.generate_content([prompt, img])
                raw_json = res.text.strip().replace('```json', '').replace('```', '')
                new_rows.extend(json.loads(raw_json))

            if new_rows:
                update_cloud(pd.DataFrame(new_rows))
                st.success("Cloud Updated!")
                st.balloons()

    st.divider()

    # --- DATA VIEW & CLEAR SECTION ---
    st.subheader("📋 Live Database")
    df = get_data()
    st.dataframe(df, use_container_width=True)

    # The Clear All Button
    st.write("---")
    st.warning("⚠️ **Danger Zone**")
    if st.button("🗑️ Clear All Spreadsheet Data"):
        # This creates an empty table with your headers
        empty_df = pd.DataFrame(columns=["FullOrder", "FlagNumber", "TruckID", "Color"])
        # This overwrites the Google Sheet with the empty table
        conn.update(data=empty_df)
        st.success("Spreadsheet has been wiped clean!")
        st.rerun()

# --- 5. NAVIGATION ---
pg = st.navigation([
    st.Page(coworker_mode, title="Lookup", icon="🔍"),
    st.Page(dev_mode, title="Admin", icon="🔒")
])
pg.run()