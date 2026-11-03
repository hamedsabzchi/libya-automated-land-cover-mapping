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
    # ==========================================
    # راهنمای کاربر (به زبان انگلیسی)
    # ==========================================
    st.info("""
    ### 💡 How to get your Service Account JSON key file?
    
    To use this app without consuming the owner's Earth Engine quota, you need to provide your own Service Account key. Follow these steps:

    1. **Go to Google Cloud Console:** Open [Google Cloud Console](https://console.cloud.google.com/) and select your Earth Engine project.
    2. **Navigate to Service Accounts:** In the left menu, go to **IAM & Admin** > **Service Accounts**.
    3. **Create or Select an Account:**
       * Click **+ Create Service Account**, give it a name (e.g., `streamlit-web`), and click **Create and Continue**.
       * In the "Role" section, search for and select **Earth Engine Resource Viewer**. Click **Continue** and **Done**.
       * *(If you already have a service account, just click on its name).*
    4. **Create a Key:**
       * Go to the **Keys** tab.
       * Click **Add Key** > **Create new key**.
       * Select **JSON** and click **Create**.
    5. **Download & Upload:**
       * A `.json` file will be downloaded to your computer.
       * Upload that file using the box above.
    """)
