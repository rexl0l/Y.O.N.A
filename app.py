import streamlit as st
import time
from pathlib import Path
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
from PIL import Image
import json
import fitz  # PyMuPDF




# --- 1. SETUP ---
st.set_page_config(page_title="YourOrderNumberAssistant", layout="centered", page_icon="🦥")

API_KEY = st.secrets["GEMINI_API_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

genai.configure(api_key=API_KEY)
# Using the standard model name for the API
model = genai.GenerativeModel('gemini-2.5-flash')
conn = st.connection("gsheets", type=GSheetsConnection)




# 2. IMAGE OPTIMIZATION (reduces Gemini token usage / credit exhaustion)
MAX_IMAGE_DIM = 1024  # Screenshot-like size; enough for table extraction

def images_from_file(f):
    """Yield PIL Images from an uploaded file (photo or PDF)."""
    name = getattr(f, "name", "").lower()
    raw = f.read()
    f.seek(0)
    if name.endswith(".pdf"):
        doc = fitz.open(stream=raw, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            yield img
        doc.close()
    else:
        yield Image.open(f).copy()


def resize_image_for_api(img, max_dim=MAX_IMAGE_DIM):
    """Downscale image to reduce API token usage. Tables remain readable."""
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    ratio = max_dim / max(w, h)
    new_size = (int(w * ratio), int(h * ratio))
    return img.resize(new_size, Image.Resampling.LANCZOS)


# 3. SCHEMA NORMALIZATION (handles Gemini output variations)
EXPECTED_KEYS = {"FullOrder", "FlagNumber", "TruckID", "Color"}
KEY_ALIASES = {
    "fullorder": "FullOrder", "full order": "FullOrder", "order": "FullOrder",
    "order number": "FullOrder", "number order": "FullOrder", "order #": "FullOrder",
    "order_id": "FullOrder", "order id": "FullOrder", "orderid": "FullOrder",
    "flagnumber": "FlagNumber", "flag number": "FlagNumber", "flag": "FlagNumber",
    "flag #": "FlagNumber", "number": "FlagNumber", "#": "FlagNumber",
    "flag_number": "FlagNumber",
    "truckid": "TruckID", "truck id": "TruckID", "truck": "TruckID",
    "inbound": "TruckID", "load": "TruckID", "truck_id": "TruckID",
    "color": "Color", "colour": "Color", "flag color": "Color", "flag colour": "Color",
}

def normalize_row(row):
    """Map Gemini output keys to our schema."""
    if not isinstance(row, dict):
        return row
    out = {}
    for k, v in row.items():
        key_lower = str(k).strip().lower()
        mapped = KEY_ALIASES.get(key_lower, k if key_lower in {s.lower() for s in EXPECTED_KEYS} else None)
        if mapped:
            out[mapped] = v
    return out if out else row


def rows_from_spreadsheet(f):
    """Parse CSV or Excel file and yield normalized row dicts. No API used."""
    name = getattr(f, "name", "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(f)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(f)
    else:
        return
    for _, row in df.iterrows():
        normalized = normalize_row(row.to_dict())
        if normalized:
            yield normalized


def is_spreadsheet(name):
    n = (name or "").lower()
    return n.endswith(".csv") or n.endswith(".xlsx") or n.endswith(".xls")


# 4. DATA HANDLERS
def get_data():
    df = conn.read(ttl="0")
    if df.empty:
        return pd.DataFrame(columns=["FullOrder", "FlagNumber", "TruckID", "Color"])
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






# 3. MODE: COWORKER (SEARCH)
def coworker_mode():
    st.title("Order Lookup")
    st.write("Enter the last 4 digits of the order number.")
    st.caption("Need help? See **How To** in the sidebar.")
    query = st.text_input("Search Order:", placeholder="e.g. 0351", help="Type only the last 4 digits, no spaces needed")

    if query:
        # Idiot-proof: strip and keep only digits (handles "0 3 5 1" or "0351 ")
        digits = "".join(c for c in str(query).strip() if c.isdigit())
        if not digits:
            st.warning("Please enter at least one digit.")
        else:
            df = get_data()
            results = df[df['FullOrder'].str.endswith(digits, na=False)] if not df.empty else df

            if not results.empty:
                row = results.iloc[0]
                # Fetch the color from the spreadsheet (e.g., "Red", "Blue")
                flag_color = row['Color'].lower()

                # BIG COLOR BOX DISPLAY
                st.markdown(f"""
                    <div style="
                        background-color: {flag_color}; 
                        padding: 40px; 
                        border-radius: 20px; 
                        text-align: center; 
                        border: 5px solid black;
                        margin-top: 20px;
                    ">
                        <h1 style="color: white; font-size: 60px; text-shadow: 2px 2px 4px #000; margin: 0;">
                            {row['Color'].upper()}
                        </h1>
                        <h2 style="color: white; margin: 0; text-shadow: 1px 1px 2px #000;">
                            FLAG #{row['FlagNumber']}
                        </h2>
                        <p style="color: white; margin: 0; font-size: 20px; opacity: 0.8;">
                            Truck: {row['TruckID']}
                        </p>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.warning(f"No match found for '{digits}'.")

#  4. MODE: DEV (ADMIN) -
def dev_mode():
    st.title("⚙️ Admin Dashboard")

    if "auth" not in st.session_state: st.session_state.auth = False
    if not st.session_state.auth:
        pw = st.text_input("Password", type="password")
        if st.button("Login") and pw == ADMIN_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        return

    st.subheader("📤 Scan New Sheets")
    st.caption("Need help? See **How To** in the sidebar. 💡 Upload photos, PDF, CSV, or Excel. CSV/Excel skip AI—no credits used.")
    files = st.file_uploader("Upload files", type=['png', 'jpg', 'jpeg', 'pdf', 'csv', 'xlsx', 'xls'], accept_multiple_files=True)

    if files and st.button("🚀 Analyze & Sync"):
        new_rows = []
        with st.spinner("Processing..."):
            for f in files:
                if is_spreadsheet(f.name):
                    new_rows.extend(rows_from_spreadsheet(f))
                    continue
                for img in images_from_file(f):
                    orig_w, orig_h = img.size
                    img = resize_image_for_api(img)
                    new_w, new_h = img.size
                    st.caption(f"🖼️ Image resized: {orig_w}×{orig_h} → {new_w}×{new_h}")
                    prompt = """
                    Extract ALL rows from this table. The format and header names may vary—ignore exact labels.
                    Map to these output keys based on CONTENT, not header text:

                    - FullOrder: The long numeric order ID (many digits). Headers might say "Order", "Number Order", "Order #", "ID", etc.
                    - FlagNumber: The small integer (usually 1-50) for flag/position. Headers might say "Flag", "Flag #", "Number", "#", etc.
                    - TruckID: The inbound/delivery code, typically starting with I or T. Headers might say "Truck", "Inbound", "Load", etc.
                    - Color: The color name (Red, Blue, Green, etc.). Headers might say "Color", "Flag Color", "Colour", etc.

                    Output a JSON array of objects, one per row: [{"FullOrder": "...", "FlagNumber": "...", "TruckID": "...", "Color": "..."}, ...]
                    Match by what the data IS (long number vs small number vs code vs color), not by column title.
                    """
                    res = model.generate_content([prompt, img])
                    raw_json = res.text.strip().replace('```json', '').replace('```', '').strip()
                    parsed = json.loads(raw_json)
                    rows = parsed if isinstance(parsed, list) else [parsed]
                    new_rows.extend(normalize_row(r) for r in rows)
                    time.sleep(0.5)  # Throttle to avoid rate-limit exhaustion

            if new_rows:
                update_cloud(pd.DataFrame(new_rows))
                st.success(f"Cloud Updated! Added {len(new_rows)} order(s).")
                st.balloons()

    st.divider()

    # --- DATA VIEW & CLEAR SECTION ---
    st.subheader("📋 Live Database")
    df = get_data()
    st.dataframe(df, use_container_width=True)

    # The Clear All Button (with confirmation)
    st.write("---")
    st.warning("⚠️ **Danger Zone**")
    if "confirm_clear" not in st.session_state:
        st.session_state.confirm_clear = False
    if not st.session_state.confirm_clear:
        if st.button("🗑️ Clear All Spreadsheet Data"):
            st.session_state.confirm_clear = True
            st.rerun()
    else:
        st.error("Are you sure? This will delete ALL order data. This cannot be undone.")
        col1, col2, _ = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ Yes, clear everything"):
                empty_df = pd.DataFrame(columns=["FullOrder", "FlagNumber", "TruckID", "Color"])
                conn.update(data=empty_df)
                st.session_state.confirm_clear = False
                st.success("Spreadsheet has been wiped clean!")
                st.rerun()
        with col2:
            if st.button("❌ Cancel"):
                st.session_state.confirm_clear = False
                st.rerun()





# --- 5. HOW TO PAGE ---
HOW_TO_IMAGES = Path(__file__).parent / "how_to_images"

def how_to_page():
    st.title("📖 How To Use")
    st.caption("Simple step-by-step guide. Stuck? Start here.")

    st.markdown("---")
    st.subheader("🔍 Part 1: Finding an Order")
    if (HOW_TO_IMAGES / "order_lookup.png").exists():
        st.image(str(HOW_TO_IMAGES / "order_lookup.png"), caption="Order Lookup screen", use_container_width=True)
    st.markdown("""
    **Step 1.** Click **Order Lookup** in the sidebar (left side).  
    **Step 2.** Type the **last 4 digits** of the order number in the box.  
    **Step 3.** Press Enter or tap outside the box.  
    **Step 4.** You'll see the **flag color**, **flag number**, and **truck**.
    """)
    with st.expander("💡 Tips"):
        st.markdown("- Use only the last 4 digits (e.g. `0351` not the full number)")
        st.markdown("- No spaces needed")
        st.markdown("- If you see 'No match found', check the number or ask someone to upload the manifest")

    st.markdown("---")
    st.subheader("📤 Part 2: Uploading New Orders")
    if (HOW_TO_IMAGES / "upload_orders.png").exists():
        st.image(str(HOW_TO_IMAGES / "upload_orders.png"), caption="Admin upload section", use_container_width=True)
    st.markdown("""
    **Step 1.** Click **Admin** in the sidebar.  
    **Step 2.** Enter the admin password.  
    **Step 3.** Click **Choose Files** and select your file(s):
    - Photos of the manifest (PNG, JPG)
    - PDF manifest
    - CSV or Excel spreadsheet
    **Step 4.** Click **🚀 Analyze & Sync**  
    **Step 5.** Wait for "Cloud Updated!" — you're done!
    """)
    with st.expander("💡 Tips"):
        st.markdown("- You can upload multiple files at once")
        st.markdown("- Screenshots or smaller images use fewer credits")
        st.markdown("- CSV/Excel skip AI and process instantly")

    st.markdown("---")
    st.subheader("❓ Common Questions")
    with st.expander("What if I get 'No match found'?"):
        st.markdown("The order number might not be in the database yet. Have someone upload the manifest in Admin.")
    with st.expander("I forgot the admin password"):
        st.markdown("Ask your admin or check your team's setup.")
    with st.expander("Can I add screenshots to this guide?"):
        st.markdown("Yes! Add `order_lookup.png` and `upload_orders.png` to the `how_to_images` folder in the project.")


# --- 6. NAVIGATION ---
pg = st.navigation([
    
    st.Page(coworker_mode, title="Order Lookup", icon="🔍"),
    st.Page(how_to_page, title="How To", icon="📖"),
    st.Page(dev_mode, title="Admin", icon="🔒")
])
pg.run()
