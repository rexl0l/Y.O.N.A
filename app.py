import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from PIL import Image
import json

# --- 1. SETTINGS & CSS (MUST BE FIRST) ---
st.set_page_config(page_title="Order Scanner", layout="centered", page_icon="🦥")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    div.stButton > button {
        height: 80px !important;
        font-size: 24px !important;
        font-weight: bold !important;
        border-radius: 15px !important;
    }
    #MainMenu, footer, header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

genai.configure(api_key=API_KEY, transport="rest")
# Fixed Model Name
model = genai.GenerativeModel('gemini-1.5-flash')
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. DATA HANDLERS ---
def get_data():
    df = conn.read(ttl="0")
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    return df

def update_cloud(new_df):
    existing_df = get_data()
    # Ensure the new data has the 4-digit search column
    if 'FullOrder' in new_df.columns:
        new_df['OrderNumber'] = new_df['FullOrder'].str[-4:]

    combined = pd.concat([existing_df, new_df], ignore_index=True)
    final_df = combined.drop_duplicates(subset=['FullOrder'], keep='last')
    conn.update(data=final_df)

# --- 4. MODE: COWORKER (SEARCH) ---
def coworker_mode():
    df = get_data() # Fetch fresh data
    st.markdown("### 🔍 Quick Order Lookup")

    if 'search_val' not in st.session_state:
        st.session_state.search_val = ""

    # Screen Display
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px; border: 2px solid #d1d5db;">
            <h1 style="color: #31333F; margin: 0; font-family: monospace; letter-spacing: 10px;">
                {st.session_state.search_val if st.session_state.search_val else "----"}
            </h1>
        </div>
    """, unsafe_allow_html=True)

    # Numpad
    rows = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["CLR", "0", "DEL"]]
    for row in rows:
        cols = st.columns(3)
        for i, digit in enumerate(row):
            if cols[i].button(digit, use_container_width=True):
                if digit == "CLR": st.session_state.search_val = ""
                elif digit == "DEL": st.session_state.search_val = st.session_state.search_val[:-1]
                elif len(st.session_state.search_val) < 4: st.session_state.search_val += digit
                st.rerun()

    # Results Logic
    if len(st.session_state.search_val) == 4:
        result = df[df['OrderNumber'] == st.session_state.search_val]
        if not result.empty:
            row = result.iloc[0]
            st.markdown(f"""
                <div style="background-color: {row['Color'].lower()}; padding: 30px; border-radius: 15px; text-align: center; border: 5px solid black; margin-top: 10px;">
                    <h1 style="color: white; font-size: 45px; text-shadow: 2px 2px 4px #000000; margin: 0;">{row['Color'].upper()}</h1>
                    <h2 style="color: white; margin: 0;">Flag #{row['FlagNumber']}</h2>
                    <p style="color: white; margin: 0; opacity: 0.8;">Truck: {row['TruckID']}</p>
                </div>
            """, unsafe_allow_html=True)

            if st.button("✅ DONE - NEXT SEARCH", use_container_width=True):
                st.session_state.search_val = ""
                st.rerun()
        else:
            st.error("Order Not Found")
            if st.button("TRY AGAIN", use_container_width=True):
                st.session_state.search_val = ""
                st.rerun()

# --- 5. MODE: ADMIN ---
def dev_mode():
    st.title("⚙️ Admin Dashboard")
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
        with st.spinner("AI Mapping Data..."):
            for f in files:
                img = Image.open(f)
                prompt = "Extract table to JSON: keys 'FullOrder', 'FlagNumber', 'TruckID', 'Color'."
                res = model.generate_content([prompt, img])
                raw_json = res.text.strip().replace('```json', '').replace('```', '')
                new_rows.extend(json.loads(raw_json))
            if new_rows:
                update_cloud(pd.DataFrame(new_rows))
                st.success("Sync Complete!")
                st.balloons()

    if st.button("🗑️ Wipe All Data", type="secondary"):
        conn.update(data=pd.DataFrame(columns=["FullOrder", "OrderNumber", "FlagNumber", "TruckID", "Color"]))
        st.rerun()

# --- 6. NAVIGATION ---
pg = st.navigation([
    st.Page(coworker_mode, title="Lookup", icon="🔍"),
    st.Page(dev_mode, title="Admin", icon="🔒")
])
pg.run()
