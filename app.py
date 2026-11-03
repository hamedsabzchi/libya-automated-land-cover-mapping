import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium
import pandas as pd
import sys
import os

# --- Load Engine ---
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))
    from landcover_engine import LandCoverConfig, build_seed_model, metrics_dictionary, CLASS_VALUES, CLASS_NAMES, CLASS_PALETTE
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
# 2. Processing (Small Area for Speed)
# ==========================================
st.subheader("1. Generate Map & Accuracy")
st.write("Click the button below to process a small sample area. This allows you to see the map, legend, and validation metrics quickly without timing out.")

# یک نقطه کوچک در لیبی برای تست سریع (اطراف طرابلس)
# این نقطه جایگزین کل منطقه بزرگ شده است تا سایت Time out ندهد
small_aoi = ee.Geometry.Rectangle([13.0, 32.5, 13.5, 33.0])

# تنظیمات مدل
config = LandCoverConfig(
    aoi_asset="projects/practical-proxy-441422-n6/assets/Libya/Fezzan", # فقط برای شناسه
    training_asset="projects/practical-proxy-441422-n6/assets/Libya/TD-V4",
    target_year=2024,
    year_count=5,
    trees=50 # کاهش تعداد درختان برای سرعت
)

if st.button("🚀 Generate Map & Metrics", use_container_width=True):
    with st.spinner("Training model and sampling validation points..."):
        try:
            # ساخت مدل (با seed=42)
            model = build_seed_model(config, seed=42)
            
            # --- A. Extract Validation Metrics ---
            metrics = metrics_dictionary(model).getInfo()
            
            st.subheader("2. Validation Accuracy")
            col1, col2 = st.columns(2)
            col1.metric("Overall Accuracy", f"{metrics['overall']*100:.2f}%")
            col2.metric("Kappa Coefficient", f"{metrics['kappa']:.3f}")
            
            # جدول دقت کلاس‌ها
            prod = metrics['producer'][0] if isinstance(metrics['producer'][0], list) else metrics['producer']
            user = metrics['user'][0] if isinstance(metrics['user'][0], list) else metrics['user']
            
            acc_data = []
            for i, (val, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
                if i < len(prod) and i < len(user):
                    acc_data.append({
                        "Code": val,
                        "Class": name,
                        "Producer Acc (%)": f"{prod[i]*100:.2f}",
                        "User Acc (%)": f"{user[i]*100:.2f}"
                    })
            st.dataframe(pd.DataFrame(acc_data), use_container_width=True)

            # --- B. Display Map ---
            st.subheader("3. Land Cover Map (Sample Area)")
            
            # گرفتن تصویر نهایی و کلیپ کردن به منطقه کوچک
            final_map = model["final_map"].clip(small_aoi)
            map_id = final_map.getMapId({'min': 1, 'max': 12, 'palette': list(CLASS_PALETTE)})
            tile_url = map_id['tile_fetcher'].url_format
            
            # ساخت نقشه
            m = folium.Map(location=[32.75, 13.25], zoom_start=10)
            folium.TileLayer(
                tiles=tile_url,
                attr='Google Earth Engine',
                name='Land Cover',
                overlay=True,
                control=True
            ).add_to(m)
            
            # اضافه کردن لجند
            legend_html = '''
            <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; 
                        background-color: white; border:2px solid grey; z-index:9999; 
                        font-size:14px; padding: 10px; border-radius: 5px; color: black;">
            <b style="color: black;">Land Cover Classes</b><br>
            '''
            for i, (val, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
                color = CLASS_PALETTE[i]
                legend_html += f'<i style="background:{color}; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border: 1px solid #000;"></i> <span style="color: black;">{val}: {name}</span><br>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))
            
            st_folium(m, width=1000, height=500)

            # --- C. Display Confusion Matrix ---
            st.subheader("4. Confusion Matrix")
            st.write("Rows = Reference, Columns = Mapped")
            
            conf_matrix = metrics['confusion']
            if conf_matrix:
                # اگر ماتریس تک بعدی بود، به دو بعدی تبدیل کن
                if not isinstance(conf_matrix[0], list):
                    conf_matrix = [conf_matrix]
                
                df_conf = pd.DataFrame(conf_matrix, index=[f"Ref {c}" for c in CLASS_VALUES], columns=[f"Map {c}" for c in CLASS_VALUES])
                st.dataframe(df_conf, use_container_width=True)

        except Exception as e:
            st.error(f"❌ Processing error: {e}")
