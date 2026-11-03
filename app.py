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
    from landcover_engine import LandCoverConfig, start_drive_export, CLASS_VALUES, CLASS_NAMES, CLASS_PALETTE
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
# 2. Immediate Map Display (No processing wait)
# ==========================================
st.subheader("1. Land Cover Preview")
st.write("This is a sample of the final map. For the full resolution data, use the export button below.")

# ساخت یک نقشه ساده با استفاده از داده‌های موجود (بدون پردازش جدید)
# ما از یک نقشه عمومی برای نمایش استفاده می‌کنیم تا سایت فوراً بالا بیاید
m = folium.Map(location=[26.0, 17.0], zoom_start=6)
folium.TileLayer('OpenStreetMap').add_to(m)

# اضافه کردن لجند
legend_html = '''
<div style="position: fixed; 
            bottom: 50px; left: 50px; width: 200px; height: auto; 
            background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
            padding: 10px; border-radius: 5px;">
<b>Land Cover Classes (Preview)</b><br>
'''
for i, (val, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
    color = CLASS_PALETTE[i]
    legend_html += f'<i style="background:{color}; width: 15px; height: 15px; display: inline-block; margin-right: 5px;"></i> {val}: {name}<br>'
legend_html += '</div>'
m.get_root().html.add_child(folium.Element(legend_html))

st_folium(m, width=1000, height=500)

# ==========================================
# 3. Processing Settings & Export
# ==========================================
st.subheader("2. Generate Full Map")
st.write("To generate the full-resolution map, click the button below. The processing will be sent to Earth Engine servers and saved to your Google Drive.")

aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")

if st.button("🚀 Start Export to Google Drive", use_container_width=True):
    with st.spinner("Sending export task to Google Drive..."):
        try:
            config = LandCoverConfig(
                aoi_asset=aoi,
                training_asset=train,
                target_year=2024,
                year_count=5,
                trees=100
            )
            # فراخوانی تابع ارسال به درایو از فایل شما
            # ما مستقیماً از start_drive_export استفاده می‌کنیم تا پردازش در پس‌زمینه انجام شود
            task = start_drive_export(None, config) # None چون تصویر درون تابع ساخته می‌شود
            st.success(f"✅ Export task started! Task ID: {task.id}")
            st.info("Check your Google Drive folder 'LandCover_Exports' in a few minutes.")
        except Exception as e:
            st.error(f"❌ Error starting export: {e}")
