import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium
import sys
import os

# ==========================================
# خواندن فایل از داخل پوشه python
# ==========================================
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))
    from landcover_engine import LandCoverConfig, load_assets, build_seed_model, start_drive_export
except ImportError as e:
    st.error(f"❌ Error loading landcover_engine: {e}")
    st.stop()

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("Please upload your Google Earth Engine Service Account JSON key file to generate the map. This ensures you use your own Earth Engine quota.")

# ==========================================
# بخش آپلود فایل کلید
# ==========================================
uploaded_file = st.file_uploader("Upload your Service Account JSON key file:", type=["json"])

if uploaded_file is not None:
    try:
        service_account_info = json.load(uploaded_file)
        credentials = ee.ServiceAccountCredentials(
            service_account_info["client_email"], 
            key_data=json.dumps(service_account_info)
        )
        ee.Initialize(credentials=credentials)
        st.success("✅ Successfully connected to Earth Engine using your Service Account!")
        
        st.subheader("Processing Settings")
        aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
        train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")
        
        # ==========================================
        # ۱. دکمه ارسال به گوگل درایو (بدون تایم اوت)
        # ==========================================
        if st.button("🚀 Start Processing (Send to Google Drive)"):
            with st.spinner("Sending export task to Google Drive. This might take a moment..."):
                try:
                    # تنظیمات
                    config = LandCoverConfig(
                        aoi_asset=aoi,
                        training_asset=train,
                        target_year=2024,
                        year_count=5,
                        trees=100
                    )
                    
                    # ساخت مدل (فقط ساخت گراف، نه اجرای آن)
                    # ما از seed 42 به عنوان پیش‌فرض استفاده می‌کنیم تا سریع باشد
                    model = build_seed_model(config, seed=42)
                    final_map = model["final_map"]
                    
                    # ارسال تسک به گوگل درایو
                    task = start_drive_export(final_map, config)
                    st.success(f"✅ Export task started successfully! Task ID: {task.id}")
                    st.info("You can check the progress of your export in the Earth Engine Code Editor under the 'Tasks' tab. The file will be saved in your Google Drive folder 'LandCover_Exports'.")
                    
                except Exception as e:
                    st.error(f"❌ Processing error: {e}")

        # ==========================================
        # ۲. نمایش نقشه پیش‌نمایش (فقط یک لایه ساده برای تست)
        # ==========================================
        st.subheader("Quick Preview (Test Map)")
        st.write("This is a simple preview. For the full map, please use the export button above.")
        
        m = folium.Map(location=[26.0, 17.0], zoom_start=6)
        folium.Marker([26.0, 17.0], popup="Libya").add_to(m)
        st_folium(m, width=1000, height=500)

    except Exception as e:
        st.error(f"❌ Connection error: {e}")
else:
    st.info("💡 **How to get this file?** Go to Google Cloud Console -> IAM & Admin -> Service Accounts. Create a service account, give it the 'Earth Engine Resource Viewer' role, and create a JSON key. Download it and upload it here.")
