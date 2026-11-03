import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium
import sys
import os

# --- Load Engine ---
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))
    from landcover_engine import LandCoverConfig, start_drive_export, build_seed_model, CLASS_VALUES, CLASS_NAMES, CLASS_PALETTE
except ImportError as e:
    st.error(f"❌ Error loading landcover_engine: {e}")
    st.stop()

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")

# ==========================================
# 1. Authentication
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
        st.success("✅ Successfully connected to Earth Engine!")
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
        st.stop()
else:
    st.info("💡 **Need a JSON key?** Go to Google Cloud Console -> IAM & Admin -> Service Accounts -> Create Key (JSON).")
    st.stop()

# ==========================================
# 2. Immediate Map Display (Preview)
# ==========================================
st.subheader("1. Land Cover Preview")
st.write("This is a sample of the final map. For the full resolution data, use the export button below.")

# نقشه ساده
m = folium.Map(location=[26.0, 17.0], zoom_start=5)
folium.TileLayer('OpenStreetMap').add_to(m)

# اصلاح رنگ‌بندی لجند (متن سیاه روی پس‌زمینه سفید)
legend_html = '''
<div style="position: fixed; 
            bottom: 50px; left: 50px; width: 220px; height: auto; 
            background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
            padding: 10px; border-radius: 5px; color: black;">
<b style="color: black;">Land Cover Classes</b><br>
'''
for i, (val, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
    color = CLASS_PALETTE[i]
    legend_html += f'<i style="background:{color}; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border: 1px solid #000;"></i> <span style="color: black;">{val}: {name}</span><br>'
legend_html += '</div>'
m.get_root().html.add_child(folium.Element(legend_html))

st_folium(m, width=1000, height=500)

# ==========================================
# 3. Processing Settings & Export
# ==========================================
st.subheader("2. Generate Full Map")
st.write("Click the button below to send the processing task to Earth Engine. The map will be saved to your Google Drive.")

aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")

if st.button("🚀 Start Export to Google Drive", use_container_width=True):
    with st.spinner("Sending export task to Google Drive... This may take 10-20 seconds."):
        try:
            config = LandCoverConfig(
                aoi_asset=aoi,
                training_asset=train,
                target_year=2024,
                year_count=5,
                trees=100
            )
            
            # ساخت مدل برای گرفتن تصویر نهایی (با seed پیش‌فرض)
            # این کار فقط گراف را می‌سازد و در پس‌زمینه گوگل اجرا می‌شود
            model = build_seed_model(config, seed=42)
            final_map = model["final_map"]
            
            # ارسال تسک به گوگل درایو
            task = start_drive_export(final_map, config)
            st.success(f"✅ Export task started successfully! Task ID: {task.id}")
            st.info("You can check the progress in your Google Earth Engine Code Editor under the 'Tasks' tab. The file will be saved in your Google Drive folder 'LandCover_Exports'.")
            
        except Exception as e:
            st.error(f"❌ Error starting export: {e}")
