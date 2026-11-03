import streamlit as st
import ee

st.set_page_config(page_title="Libya Land Cover App", layout="wide")

st.title("🌍 Libya Automated Land Cover Mapping")
st.write("این یک نسخه وب از پروژه نقشه‌برداری خودکار لیبی است.")

try:
    ee.Initialize()
    st.success("✅ اتصال به Google Earth Engine با موفقیت انجام شد!")
except Exception as e:
    st.error(f"❌ خطا در اتصال به GEE: {e}")
    st.info("💡 توجه: برای اجرای این کد در سرور، نیاز به تنظیمات احراز هویت (Service Account) داریم.")

st.subheader("تنظیمات نقشه")
aoi = st.text_input("شناسه منطقه (AOI Asset):", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
st.write(f"منطقه انتخاب شده: {aoi}")

if st.button("شروع پردازش"):
    st.info("در نسخه‌های بعدی، این دکمه پردازش را شروع می‌کند.")
