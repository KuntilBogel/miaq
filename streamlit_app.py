import streamlit as st

from main import (
    make,
    colorMake,
    reverseMake,
    reverseColorMake,
    whiteMake,
    reverseWhiteMake,
)

TYPE_MAKERS = {
    "default": make,
    "color": colorMake,
    "reverse": reverseMake,
    "reverseColor": reverseColorMake,
    "white": whiteMake,
    "reverseWhite": reverseWhiteMake,
}

st.set_page_config(page_title="Make it a Quote", page_icon="🗨️")
st.title("🗨️ Make it a Quote")

with st.form("quote_form"):
    name = st.text_input("Name", value="SAMPLE")
    id_ = st.text_input("ID", value="")
    content = st.text_area("Content", value="Make it a Quote")
    icon = st.text_input(
        "Icon URL", value="https://cdn.discordapp.com/embed/avatars/0.png"
    )
    type_ = st.selectbox("Type", list(TYPE_MAKERS.keys()))
    submitted = st.form_submit_button("Generate")

if submitted:
    with st.spinner("Generating image..."):
        try:
            image_io = TYPE_MAKERS[type_](name, id_, content, icon)
        except Exception as e:
            st.error(f"Failed to generate image: {e}")
        else:
            st.image(image_io, use_container_width=True)
            st.download_button(
                "Download PNG",
                data=image_io.getvalue(),
                file_name="quote.png",
                mime="image/png",
            )
