import streamlit as st
import ee
import json
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("این یک نسخه وب از پروژه نقشه‌برداری خودکار لیبی است.")

try:
    # خواندن کلید از Secrets
    service_account_info = dict(st.secrets["gcp_service_account"])
    credentials = ee.ServiceAccountCredentials(
        service_account_info["client_email"], 
        key_data=json.dumps(service_account_info)
    )
    ee.Initialize(credentials)
    st.success("✅ اتصال به Google Earth Engine با موفقیت انجام شد!")
except Exception as e:
    st.error(f"❌ خطا در اتصال به GEE: {e}")

st.subheader("تنظیمات پردازش")
aoi = st.text_input("شناسه منطقه (AOI Asset):", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
train = st.text_input("شناسه نقاط آموزشی:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")

if st.button("🚀 شروع پردازش"):
    st.info("در حال پردازش... (نقشه در نسخه بعدی اینجا نمایش داده می‌شود)")
    m = folium.Map(location=[26.0, 17.0], zoom_start=5)
    folium.Marker([26.0, 17.0], popup="لیبی").add_to(m)
    st_folium(m, width=700, height=500)
