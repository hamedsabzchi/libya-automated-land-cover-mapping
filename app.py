
import streamlit as st
import ee
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")

# ==========================================
# بخش ساده برای دریافت توکن
# ==========================================
st.write("Please enter your Google Earth Engine Access Token to generate the map. This ensures you use your own Earth Engine quota.")

# کادر ورود توکن
access_token = st.text_input("Enter your Earth Engine Access Token:", type="password")

if access_token:
    try:
        # اتصال به GEE با استفاده از توکن کاربر
        credentials = ee.oauth.Credentials(None, token=access_token)
        ee.Initialize(credentials=credentials)
        st.success("✅ Successfully connected to Earth Engine using your token!")
        
        # ==========================================
        # بخش پردازش
        # ==========================================
        st.subheader("Processing Settings")
        aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
        train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")
        
        if st.button("🚀 Start Processing"):
            st.info("Processing started... (Map generation logic will be added here).")
            
            # نمایش یک نقشه ساده و تستی
            m = folium.Map(location=[26.0, 17.0], zoom_start=5)
            folium.Marker([26.0, 17.0], popup="Libya").add_to(m)
            st_folium(m, width=700, height=500)
            
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
        st.info("Your token might be invalid. Please make sure you copied the entire token.")
else:
    st.info("💡 **How to get your token?** Open the [Google Earth Engine Code Editor](https://code.earthengine.google.com/). In the Console tab at the bottom, run this command: `print(ee.data.getAuthToken())`. If it gives an error, use your browser's Developer Tools (F12) to get the token.")
