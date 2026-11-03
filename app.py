import streamlit as st
import ee
import folium
from streamlit_folium import st_folium

# --- Page Config ---
st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("Please enter your Google Earth Engine Access Token to generate the map. This ensures you use your own Earth Engine quota.")

# --- Token Input ---
# از کاربر می‌خواهیم توکن خودش را وارد کند
access_token = st.text_input("Enter your Earth Engine Access Token:", type="password")

if access_token:
    try:
        # اتصال به GEE با استفاده از توکن کاربر
        credentials = ee.oauth.Credentials(None, token=access_token)
        ee.Initialize(credentials=credentials)
        st.success("✅ Successfully connected to Earth Engine using your token.")
        
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
        st.info("Your token might be invalid or expired. Please get a new one from Earth Engine Code Editor.")
else:
    st.info("💡 How to get your token? Open your Google Earth Engine Code Editor, open the Console, and run this command: `print(ee.data.getAuthToken())`")
