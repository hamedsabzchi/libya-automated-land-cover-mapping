import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")

st.write("Please upload your Google Earth Engine Service Account JSON key file to generate the map. This ensures you use your own Earth Engine quota.")

# ==========================================
# بخش آپلود فایل کلید
# ==========================================
uploaded_file = st.file_uploader("Upload your Service Account JSON key file:", type=["json"])

if uploaded_file is not None:
    try:
        # خواندن فایل آپلود شده
        service_account_info = json.load(uploaded_file)
        
        # اتصال به GEE با استفاده از فایل کاربر
        credentials = ee.ServiceAccountCredentials(
            service_account_info["client_email"], 
            key_data=json.dumps(service_account_info)
        )
        ee.Initialize(credentials=credentials)
        st.success("✅ Successfully connected to Earth Engine using your Service Account!")
        
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
        st.info("Make sure your JSON file is a valid Service Account key.")
else:
    st.info("💡 **How to get this file?** Go to Google Cloud Console -> IAM & Admin -> Service Accounts. Create a service account, give it the 'Earth Engine Resource Viewer' role, and create a JSON key. Download it and upload it here.")
