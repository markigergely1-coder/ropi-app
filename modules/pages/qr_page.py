import streamlit as st
from io import BytesIO


def _generate_qr_bytes(url):
    import qrcode
    qr = qrcode.QRCode(box_size=8, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_qr_page():
    st.title("📲 Check-in QR kód")
    st.markdown("Mutasd meg ezt a kódot a tagoknak, vagy nyomtasd ki a terembe!")

    try:
        checkin_url = st.secrets["app"]["checkin_url"]
    except Exception:
        checkin_url = "https://markigergely1-coder.github.io/ropi-app/checkin.html"

    col_qr, col_info = st.columns([1, 1], vertical_alignment="center")
    with col_qr:
        st.image(_generate_qr_bytes(checkin_url), width=260)
    with col_info:
        st.markdown("### Check-in link:")
        st.code(checkin_url, language=None)
        st.link_button("🔗 Megnyitás", checkin_url, use_container_width=True)
        st.caption("A tagok ezzel a linkkel vagy QR kóddal jelentkeznek be az alkalomra.")
