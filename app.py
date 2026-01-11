import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from PIL import Image
import json

# --- 1. MOBILE-FIRST UI SETUP ---
st.set_page_config(page_title="Order Lookup", layout="centered", page_icon="🔍")

st.markdown("""
    <style>
    /* Make the input box GIGANTIC and easy to tap */
    .stTextInput input {
        font-size: 50px !important;
        height: 100px !important;
        text-align: center !important;
        font-family: monospace;
    }
    /* Style the labels */
    .stMarkdown h3 { text-align: center; padding-bottom: 0; }
    /* Make the "Clear" button big and red */
    div.stButton > button {
        height: 60px !important;
        width: 100% !important;
        background-color: #ff4b4b !important;
        color: white !important;
        font-weight: bold !important;
        font-size: 20px !important;
    }
    #MainMenu, footer, header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-1.5-flash')
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    df = conn.read(ttl="0")
    if df.empty:
        return pd.DataFrame(columns=["FullOrder", "FlagNumber", "TruckID", "Color"])
    # Standardize all data to text to prevent search crashes
    return df.astype(str).apply(lambda x: x.str.replace(r'\.0$', '', regex=True).str.strip())

# --- 3. COWORKER MODE (THE FAST SEARCH) ---
def coworker_mode():
    df = get_data()
    
    st.markdown("### 🔍 TAP BOX TO START")
    
    # We use a standard text input. On mobile, this opens the native keypad.
    # We search the LAST 4 digits of the 'FullOrder' column.
    search_query = st.text_input("Search", label_visibility="collapsed", max_chars=4, placeholder="0000")

    if search_query:
        # SEARCH LOGIC: Find rows where 'FullOrder' ends with the typed digits
        result = df[df['FullOrder'].str.endswith(search_query)]
        
        if not result.empty:
            row = result.iloc[0]
            st.markdown(f"""
                <div style="background-color: {row['Color'].lower()}; padding: 40px; border-radius: 20px; text-align: center; border: 6px solid black; margin: 20px 0;">
                    <h1 style="color: white; font-size: 60px; text-shadow: 2px 2px 4px #000; margin: 0;">{row['Color'].upper()}</h1>
                    <h2 style="color: white; margin: 0;">Flag #{row['FlagNumber']}</h2>
                    <p style="color: white; margin: 0; font-size: 20px; opacity: 0.9;">Truck: {row['TruckID']}</p>
                </div>
            """, unsafe_allow_html=True)
        else:
            if len(search_query) == 4:
                st.error("❌ Order not found in today's list.")

    st.write("---")
    if st.button("RESET / CLEAR BOX"):
        st.rerun()

# --- 4. ADMIN MODE ---
def dev_mode():
    st.title("⚙️ Admin")
    if "auth" not in st.session_state: st.session_state.auth = False
    if not st.session_state.auth:
        pw = st.text_input("Password", type="password")
        if st.button("Login") and pw == ADMIN_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        return

    files = st.file_uploader("Upload photos", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    if files and st.button("🚀 Analyze & Sync"):
        new_rows = []
        with st.spinner("AI Reading..."):
            for f in files:
                img = Image.open(f)
                res = model.generate_content(["Extract table to JSON: keys 'FullOrder', 'FlagNumber', 'TruckID', 'Color'.", img])
                raw_json = res.text.strip().replace('```json', '').replace('```', '')
                new_rows.extend(json.loads(raw_json))
            if new_rows:
                existing_df = get_data()
                combined = pd.concat([existing_df, pd.DataFrame(new_rows)], ignore_index=True)
                conn.update(data=combined.drop_duplicates(subset=['FullOrder'], keep='last'))
                st.success("Sync Complete!")
                st.balloons()

    if st.button("🗑️ Clear All Data"):
        conn.update(data=pd.DataFrame(columns=["FullOrder", "FlagNumber", "TruckID", "Color"]))
        st.rerun()

# --- 5. NAVIGATION ---
pg = st.navigation([
    st.Page(coworker_mode, title="Lookup", icon="🔍"),
    st.Page(dev_mode, title="Admin", icon="🔒")
])
pg.run()
