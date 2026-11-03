import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
from streamlit_oauth import OAuth2Component

# ==========================================
# تنظیمات اولیه صفحه
# ==========================================
st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("برای استفاده از این ابزار، لطفاً با حساب گوگل خود وارد شوید.")

# ==========================================
# خواندن کدهای امنیتی از Secrets
# ==========================================
try:
    CLIENT_ID = st.secrets["google_oauth"]["client_id"]
    CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
except Exception:
    st.error("❌ خطا: تنظیمات امنیتی (Secrets) در Streamlit یافت نشد. لطفاً به منوی Manage app بروید و Secrets را تنظیم کنید.")
    st.stop()

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# ==========================================
# دریافت آدرس بازگشتی (متد جدید و صحیح)
# ==========================================
# آدرسی که گوگل باید بعد از لاگین به آن برگردد
REDIRECT_URI = st.query_params.get("redirect_uri", None)
if isinstance(REDIRECT_URI, list):
    REDIRECT_URI = REDIRECT_URI[0] if REDIRECT_URI else None

# اگر آدرس پیدا نشد، از آدرس اصلی استفاده کن
if not REDIRECT_URI:
    REDIRECT_URI = "https://libya-automated-land-cover-mapping-jtmkdtphwky47bfyfdyzf.streamlit.app/"

# ==========================================
# بخش لاگین با گوگل
# ==========================================
oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL)

if 'token' not in st.session_state:
    # دکمه ورود به گوگل
    result = oauth2.authorize_button(
        name="ورود با حساب گوگل",
        redirect_uri=REDIRECT_URI,
        scope="https://www.googleapis.com/auth/earthengine",
        key="google_login",
        use_container_width=True
    )
    if result and 'token' in result:
        st.session_state.token = result['token']
        st.rerun()
else:
    # کاربر لاگین کرده است
    try:
        # اتصال به GEE با استفاده از توکن کاربر
        credentials = ee.oauth.Credentials(None, token=st.session_state.token['access_token'])
        ee.Initialize(credentials=credentials)
        st.success("✅ اتصال با موفقیت انجام شد! (شما از کردیت خودتان استفاده می‌کنید)")
        
        st.subheader("تنظیمات پردازش")
        aoi = st.text_input("شناسه منطقه (AOI Asset):", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
        train = st.text_input("شناسه نقاط آموزشی:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")
        
        if st.button("🚀 شروع پردازش"):
            st.info("در حال پردازش... (نقشه در نسخه بعدی اینجا نمایش داده می‌شود)")
            
            # نمایش یک نقشه ساده و تستی برای اطمینان
            m = folium.Map(location=[26.0, 17.0], zoom_start=5)
            folium.Marker([26.0, 17.0], popup="لیبی").add_to(m)
            st_folium(m, width=700, height=500)
            
    except Exception as e:
        st.error(f"خطا در اتصال به ماهواره‌ها: {e}")
        if st.button("خروج"):
            del st.session_state.token
            st.rerun()
