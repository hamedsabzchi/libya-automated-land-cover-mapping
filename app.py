import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium
# ایمپورت کردن موتور پردازش شما
try:
    from landcover_engine import search_seeds, start_drive_export, LandCoverConfig
except ImportError:
    st.error("❌ Error: landcover_engine.py not found. Please upload it to the root directory.")
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
        
        # ==========================================
        # تنظیمات پردازش
        # ==========================================
        st.subheader("Processing Settings")
        aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
        train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")
        
        if st.button("🚀 Start Processing"):
            with st.spinner("Training Random Forest model... This may take a few minutes."):
                try:
                    # ساخت تنظیمات بر اساس ورودی‌های کاربر
                    config = LandCoverConfig(
                        aoi_asset=aoi,
                        training_asset=train,
                        target_year=2024,
                        year_count=5,
                        trees=100 # برای سرعت بیشتر در تست، تعداد درختان را کمتر کردیم
                    )
                    
                    # اجرای جستجوی بهترین مدل (این تابع از فایل شما صدا زده می‌شود)
                    result = search_seeds(config)
                    best_model = result["model"]
                    
                    st.success(f"✅ Processing complete! Best seed: {result['best_metrics']['seed']}")
                    
                    # ==========================================
                    # نمایش نقشه نهایی
                    # ==========================================
                    st.subheader("Final Land Cover Map")
                    
                    # دریافت نقشه نهایی از مدل شما
                    final_map = best_model["final_map"]
                    
                    # تعریف رنگ‌ها
                    palette = [
                        '#002200', '#185e0a', '#74a56a', '#fffb00', '#FF8C00', '#43BE0A',
                        '#bb6d3a', '#553a17', '#808080', '#00008B', '#15c0df', '#8B4513'
                    ]
                    vis_params = {'min': 1, 'max': 12, 'palette': palette}
                    
                    # دریافت لینک تایل‌های نقشه از GEE
                    map_id = final_map.getMapId(vis_params)
                    tile_url = map_id['tile_fetcher'].url_format
                    
                    # ساخت نقشه تعاملی
                    m = folium.Map(location=[26.0, 17.0], zoom_start=6)
                    folium.TileLayer(
                        tiles=tile_url,
                        attr='Google Earth Engine',
                        name='Land Cover',
                        overlay=True,
                        control=True
                    ).add_to(m)
                    
                    st_folium(m, width=1000, height=600)
                    
                    # ==========================================
                    # دکمه دانلود
                    # ==========================================
                    st.subheader("Download Map")
                    if st.button("Export to Google Drive"):
                        with st.spinner("Sending export task to Google Drive..."):
                            task = start_drive_export(final_map, config)
                            st.success(f"✅ Export task started! Check your Google Drive (folder: LandCover_Exports). Task ID: {task.id}")
                            
                except Exception as e:
                    st.error(f"❌ Processing error: {e}")
                    
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
else:
    st.info("💡 **How to get this file?** Go to Google Cloud Console -> IAM & Admin -> Service Accounts. Create a service account, give it the 'Earth Engine Resource Viewer' role, and create a JSON key. Download it and upload it here.")
