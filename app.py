import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
from streamlit_oauth import OAuth2Component

st.set_page_config(page_title="Libya Land Cover App", layout="wide")
st.title("🌍 Libya Automated Land Cover Mapping")
st.write("برای استفاده از این ابزار، لطفاً با حساب گوگل خود وارد شوید.")

try:
    CLIENT_ID = st.secrets["google_oauth"]["client_id"]
    CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
except Exception:
    st.error("❌ خطا: تنظیمات Secrets یافت نشد.")
    st.stop()

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# ==========================================
# دریافت هوشمند آدرس بازگشتی
# ==========================================
# دریافت آدرس از Query Params که خود Streamlit می‌سازد
redirect_uri = st.query_params.get("redirect_uri")
if isinstance(redirect_uri, list):
    redirect_uri = redirect_uri[0] if redirect_uri else None

if not redirect_uri:
    redirect_uri = "https://libya-automated-land-cover-mapping-jtmkdtphwky47bfyfdyzf.streamlit.app/"

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL)

if 'token' not in st.session_state:
    result = oauth2.authorize_button(
        name="ورود با حساب گوگل",
        redirect_uri=redirect_uri,
        scope="https://www.googleapis.com/auth/earthengine",
        key="google_login",
        use_container_width=True
    )
    if result and 'token' in result:
        st.session_state.token = result['token']
        st.rerun()
else:
    try:
        credentials = ee.oauth.Credentials(None, token=st.session_state.token['access_token'])
        ee.Initialize(credentials=credentials)
        st.success("✅ اتصال با موفقیت انجام شد!")
        
        st.subheader("تنظیمات پردازش")
        aoi = st.text_input("شناسه منطقه (AOI Asset):", "projects/practical-proxy-441422-n6/assets/Libya/Fezzan")
        train = st.text_input("شناسه نقاط آموزشی:", "projects/practical-proxy-441422-n6/assets/Libya/TD-V4")
        
        if st.button("🚀 شروع پردازش"):
            st.info("در حال پردازش...")
            m = folium.Map(location=[26.0, 17.0], zoom_start=5)
            folium.Marker([26.0, 17.0], popup="لیبی").add_to(m)
            st_folium(m, width=700, height=500)
            
    except Exception as e:
        st.error(f"خطا: {e}")
        if st.button("خروج"):
            del st.session_state.token
            st.rerun()
