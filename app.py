import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
from google_auth_oauthlib.flow import Flow
import urllib.parse

# --- Page Config ---
st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("Please sign in with your Google account to generate the map. Your session will use your own Google Earth Engine quota.")

# --- Read Secrets ---
try:
    CLIENT_ID = st.secrets["google_oauth"]["client_id"]
    CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
    REDIRECT_URI = st.secrets["google_oauth"]["redirect_uri"]
except Exception as e:
    st.error("❌ Error: Missing secrets configuration.")
    st.stop()

# --- OAuth Flow ---
def get_auth_url():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=["https://www.googleapis.com/auth/earthengine"],
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return auth_url

# --- Handle Login State ---
if "credentials" not in st.session_state:
    st.session_state.credentials = None

# --- Login Logic ---
if st.session_state.credentials is None:
    # Check if we are returning from Google with a code
    query_params = st.query_params
    if "code" in query_params:
        auth_code = query_params["code"][0] if isinstance(query_params["code"], list) else query_params["code"]
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [REDIRECT_URI],
                }
            },
            scopes=["https://www.googleapis.com/auth/earthengine"],
            redirect_uri=REDIRECT_URI,
        )
        try:
            flow.fetch_token(code=auth_code)
            st.session_state.credentials = flow.credentials
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"❌ Authentication failed: {e}")
            st.stop()

    # Show Login Button
    auth_url = get_auth_url()
    st.markdown(
        f'<a href="{auth_url}" target="_self"><button style="background-color: #4CAF50; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 8px;">🔑 Sign in with Google</button></a>',
        unsafe_allow_html=True,
    )
    st.stop()

# --- App Logic (User is logged in) ---
try:
    ee.Initialize(credentials=st.session_state.credentials)
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
        st.session_state.credentials = None
        st.rerun()
