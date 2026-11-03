import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium
from streamlit_oauth import OAuth2Component

# --- Page Config ---
st.set_page_config(page_title="Libya Land Cover Mapping", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("Please sign in with your Google account to generate the map.")

# --- Read Secrets ---
try:
    CLIENT_ID = st.secrets["google_oauth"]["client_id"]
    CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
except Exception:
    st.error("❌ Error: Secrets are not configured correctly.")
    st.stop()

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# --- Redirect URI (The exact one you registered in Google Cloud) ---
REDIRECT_URI = "https://libya-automated-land-cover-mapping-jtmkdtphwky47bfyfdyzf.streamlit.app/component/streamlit_oauth.authorize_button"

# --- OAuth Logic ---
oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL)

if 'token' not in st.session_state:
    # Login Button
    result = oauth2.authorize_button(
        name="🔑 Sign in with Google",
        redirect_uri=REDIRECT_URI,
        scope="https://www.googleapis.com/auth/earthengine",
        key="google_login",
        use_container_width=True
    )
    if result and 'token' in result:
        st.session_state.token = result['token']
        st.rerun()
else:
    # User is logged in
    try:
        credentials = ee.oauth.Credentials(None, token=st.session_state.token['access_token'])
        ee.Initialize(credentials=credentials)
        st.success("✅ Successfully connected to Earth Engine using your account.")
        
        st.subheader("Processing Settings")
        aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
        train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")
        
        if st.button("🚀 Start Processing"):
            st.info("Processing started... (Map generation logic will be added here).")
            
            # Test Map
            m = folium.Map(location=[26.0, 17.0], zoom_start=5)
            folium.Marker([26.0, 17.0], popup="Libya").add_to(m)
            st_folium(m, width=700, height=500)
            
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
        if st.button("Sign Out"):
            del st.session_state.token
            st.rerun()
