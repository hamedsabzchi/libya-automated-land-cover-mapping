import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium
from streamlit_folium import folium_static
import pandas as pd
import sys
import os

# --- Load Engine ---
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))
    from landcover_engine import LandCoverConfig, load_assets, build_seed_model, start_drive_export, metrics_dictionary, CLASS_VALUES, CLASS_NAMES, CLASS_PALETTE
except ImportError as e:
    st.error(f"❌ Error loading landcover_engine: {e}")
    st.stop()

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("Generate the map directly in your browser. All processing uses your own Earth Engine account.")

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
# 2. Processing Settings
# ==========================================
st.subheader("1. Processing Settings")
col1, col2 = st.columns(2)
with col1:
    aoi = st.text_input("AOI Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
with col2:
    train = st.text_input("Training Points Asset ID:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")

if st.button("🚀 Generate Map in Browser", use_container_width=True):
    with st.spinner("Training model and rendering map... This may take a few minutes."):
        try:
            # Build configuration
            config = LandCoverConfig(
                aoi_asset=aoi,
                training_asset=train,
                target_year=2024,
                year_count=5,
                trees=100
            )
            
            # Build model (using seed 42 for speed)
            model = build_seed_model(config, seed=42)
            final_map = model["final_map"]
            metrics = metrics_dictionary(model).getInfo()
            
            # ----------------------------------------------------
            # A. Display Map
            # ----------------------------------------------------
            st.subheader("2. Land Cover Map")
            
            # Get Map ID from GEE
            map_id = final_map.getMapId({'min': 1, 'max': 12, 'palette': list(CLASS_PALETTE)})
            tile_url = map_id['tile_fetcher'].url_format
            
            # Create Folium Map
            m = folium.Map(location=[26.0, 17.0], zoom_start=6)
            folium.TileLayer(
                tiles=tile_url,
                attr='Google Earth Engine',
                name='Land Cover',
                overlay=True,
                control=True
            ).add_to(m)
            
            # Add Legend
            legend_html = '''
            <div style="position: fixed; 
                        bottom: 50px; left: 50px; width: 200px; height: auto; 
                        background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
                        padding: 10px; border-radius: 5px;">
            <b>Legend</b><br>
            '''
            for i, (val, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
                color = CLASS_PALETTE[i]
                legend_html += f'<i style="background:{color}; width: 15px; height: 15px; display: inline-block; margin-right: 5px;"></i> {val}: {name}<br>'
            legend_html += '</div>'
            
            m.get_root().html.add_child(folium.Element(legend_html))
            
            # Render Map
            st_folium(m, width=1000, height=600)
            
            # ----------------------------------------------------
            # B. Display Accuracy Metrics
            # ----------------------------------------------------
            st.subheader("3. Validation Accuracy")
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Overall Accuracy", f"{metrics['overall']*100:.2f}%")
            col_m2.metric("Kappa Coefficient", f"{metrics['kappa']:.3f}")
            
            # Create accuracy table for classes
            acc_data = []
            prod = metrics['producer'][0] if isinstance(metrics['producer'][0], list) else metrics['producer']
            user = metrics['user'][0] if isinstance(metrics['user'][0], list) else metrics['user']
            
            for i, (val, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
                if i < len(prod) and i < len(user):
                    acc_data.append({
                        "Code": val,
                        "Class": name,
                        "Producer Acc (%)": f"{prod[i]*100:.2f}",
                        "User Acc (%)": f"{user[i]*100:.2f}"
                    })
            
            df = pd.DataFrame(acc_data)
            st.dataframe(df, use_container_width=True)
            
            # ----------------------------------------------------
            # C. Download Button
            # ----------------------------------------------------
            st.subheader("4. Download Data")
            if st.button("📥 Export Map to Google Drive"):
                with st.spinner("Sending export task to Google Drive..."):
                    task = start_drive_export(final_map, config)
                    st.success(f"✅ Export task started! Task ID: {task.id}")
                    st.info("Check your Google Drive folder 'LandCover_Exports' in a few minutes.")

        except Exception as e:
            st.error(f"❌ Processing error: {e}")
