import io
import ipaddress
import socket
import sys
import textwrap
import unicodedata
import warnings
from itertools import groupby
from urllib.parse import urlparse

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, UnidentifiedImageError
from pilmoji import Pilmoji

warnings.simplefilter("ignore")

ALLOWED_ICON_SCHEMES = {"http", "https"}
ICON_FETCH_TIMEOUT = 10  # seconds
MAX_ICON_BYTES = 8 * 1024 * 1024  # 8 MB
MAX_CONTENT_LEN = 500
MAX_NAME_LEN = 100
MAX_ID_LEN = 100

# --- wrap.py (fullwidth-aware text wrapping) ---

east_asian_widths = {
    'W': 2,   # Wide
    'F': 2,   # Full-width (wide)
    'Na': 1,  # Narrow
    'H': 1,   # Half-width (narrow)
    'N': 1,   # Neutral (not East Asian, treated as narrow)
    'A': 1    # Ambiguous (s/b wide in East Asian context, narrow otherwise, but that doesn't work)
}


def column_width(text):
    if isinstance(text, str) and sys.version_info < (3, 0):
        return len(text)
    combining_correction = sum([-1 for c in text if unicodedata.combining(c)])
    try:
        width = sum([east_asian_widths[unicodedata.east_asian_width(c)] for c in text])
    except AttributeError:
        width = len(text)
    return width + combining_correction


class TextWrapper(textwrap.TextWrapper):
    def _wrap_chunks(self, chunks):
        lines = []

        chunks.reverse()

        while chunks:
            cur_line = []
            cur_len = 0

            if lines:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent

            width = self.width - column_width(indent)

            if self.drop_whitespace and chunks[-1].strip() == '' and lines:
                del chunks[-1]

            while chunks:
                l = column_width(chunks[-1])

                if cur_len + l <= width:
                    cur_line.append(chunks.pop())
                    cur_len += l

                else:
                    break

            if chunks and column_width(chunks[-1]) > width:
                self._handle_long_word(chunks, cur_line, cur_len, width)

            if self.drop_whitespace and cur_line and cur_line[-1].strip() == '':
                del cur_line[-1]

            if cur_line:
                lines.append(indent + ''.join(cur_line))

        return lines

    def _break_word(self, word, space_left):
        total = 0
        for i, c in enumerate(word):
            total += column_width(c)
            if total > space_left:
                return word[:i - 1], word[i - 1:]
        return word, ''

    def _split(self, text):
        split = lambda t: textwrap.TextWrapper._split(self, t)
        chunks = []
        for chunk in split(text):
            for w, g in groupby(chunk, column_width):
                if w == 1:
                    chunks.extend(split(''.join(g)))
                else:
                    chunks.extend(list(g))
        return chunks

    def _handle_long_word(self, reversed_chunks, cur_line, cur_len, width):
        space_left = max(width - cur_len, 1)
        if self.break_long_words:
            l, r = self._break_word(reversed_chunks[-1], space_left)
            cur_line.append(l)
            reversed_chunks[-1] = r

        elif not cur_line:
            cur_line.append(reversed_chunks.pop())


def fw_wrap(text, width=50):
    w = TextWrapper(width=width)
    return w.wrap(text)


# --- main.py (quote image generation) ---


class IconFetchError(Exception):
    """Raised when the user-supplied icon URL can't be safely fetched as an image."""


def _assert_public_host(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise IconFetchError(f"Could not resolve icon host '{hostname}'") from e

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise IconFetchError("Icon URL resolves to a disallowed address")


def fetch_icon_image(url):
    if not url or not url.strip():
        raise IconFetchError("Icon URL is required")

    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_ICON_SCHEMES:
        raise IconFetchError("Icon URL must use http or https")
    if not parsed.hostname:
        raise IconFetchError("Icon URL is missing a host")

    _assert_public_host(parsed.hostname)

    try:
        resp = requests.get(url, timeout=ICON_FETCH_TIMEOUT, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise IconFetchError(f"Failed to download icon: {e}") from e

    content_type = resp.headers.get("Content-Type", "")
    if content_type and not content_type.split(";")[0].strip().startswith("image/"):
        raise IconFetchError(f"Icon URL did not return an image (got '{content_type}')")

    data = bytearray()
    for chunk in resp.iter_content(chunk_size=65536):
        data.extend(chunk)
        if len(data) > MAX_ICON_BYTES:
            raise IconFetchError("Icon image is too large (max 8MB)")

    if not data:
        raise IconFetchError("Icon URL returned no data")

    try:
        img = Image.open(io.BytesIO(bytes(data)))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise IconFetchError("Icon URL did not return a valid image") from e

    return img


def check_text_lengths(name, id, content):
    if len(content) > MAX_CONTENT_LEN:
        raise ValueError(f"content is too long (max {MAX_CONTENT_LEN} characters)")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"name is too long (max {MAX_NAME_LEN} characters)")
    if len(id) > MAX_ID_LEN:
        raise ValueError(f"id is too long (max {MAX_ID_LEN} characters)")


BASE_GD_IMAGE = Image.open("images/base-gd.png")
BASE_RV_IMAGE = Image.open("images/base-gd-rv.png")

BASE_GD_W_IMAGE = Image.open("images/base-gd-w.png")
BASE_RV_W_IMAGE = Image.open("images/base-gd-w-rv.png")

BASE_IMAGE = Image.open("images/base.png")
if BASE_IMAGE.mode != "RGBA":
    BASE_IMAGE = BASE_IMAGE.convert("RGBA")
MPLUS_FONT = ImageFont.truetype("fonts/MPLUSRounded1c-Regular.ttf", size=16)
MPLUS_FONTBOLD = ImageFont.truetype("fonts/MPLUSRounded1c-Bold.ttf", size=16)
BRAND = "http://s.id/MaiSakurajima"


def getsize(font, text):
    left, top, right, bottom = font.getbbox(text)
    return right - left, bottom


def drawText(im, ofs, string, font="fonts/MPLUSRounded1c-Regular.ttf", bold_font="fonts/MPLUSRounded1c-Bold.ttf", size=16, color=(0, 0, 0, 255), split_len=None, padding=4, disable_dot_wrap=False):
    v = ImageDraw.Draw(im)
    fontObj = ImageFont.truetype(font, size=size)
    boldFontObj = ImageFont.truetype(bold_font, size=size)

    pure_lines = []
    pos = 0
    l = ""

    if not disable_dot_wrap:
        for char in string:
            if char == "\n":
                pure_lines.append(l)
                l = ""
                pos += 1
            elif char in ["、", ",", "。", "."]:
                pure_lines.append(l + char)
                l = ""
                pos += 1
            else:
                l += char
                pos += 1
        if l:
            pure_lines.append(l)
    else:
        pure_lines = string.split("\n")

    lines = []
    for line in pure_lines:
        lines.extend(fw_wrap(line, width=split_len))

    dy = 0
    draw_lines = []

    for line in lines:
        tsize = getsize(fontObj, line)
        ofs_y = ofs[1] + dy
        t_height = tsize[1]
        x = int(ofs[0] - (tsize[0] / 2))
        draw_lines.append((x, ofs_y, line))
        ofs_y += t_height + padding
        dy += t_height + padding

    adj_y = -30 * (len(draw_lines) - 1)

    for dl in draw_lines:
        with Pilmoji(im) as p:
            parts = dl[2].split('*')  # * for bold
            xPos = dl[0]
            yPos = adj_y + dl[1]

            for i, part in enumerate(parts):
                if i % 2 == 1:
                    p.text((xPos, yPos), part, font=boldFontObj, fill=color)
                    xPos += v.textlength(part, font=boldFontObj)
                else:
                    subparts = part.split('_')  # _ for italic
                    for j, subpart in enumerate(subparts):
                        if j % 2 == 1:
                            text_width, text_height = getsize(fontObj, subpart)

                            padding = 15
                            italic_text_image = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), (0, 0, 0, 0))
                            italic_draw = ImageDraw.Draw(italic_text_image)
                            italic_draw.text((padding, padding), subpart, font=fontObj, fill=color)

                            slant_amount = 0.2
                            italic_text_image = italic_text_image.transform(
                                italic_text_image.size,
                                Image.AFFINE,
                                (1, slant_amount, 0, 0, 1, 0),
                                resample=Image.BICUBIC
                            )

                            im.alpha_composite(italic_text_image, dest=(int(xPos), int(yPos - padding)))

                            xPos += text_width + int(slant_amount * size)
                        else:
                            strikethrough_parts = subpart.split('~')
                            for k, s_part in enumerate(strikethrough_parts):
                                if k % 2 == 1:
                                    p.text((xPos, yPos), s_part, font=fontObj, fill=color)
                                    text_width = v.textlength(s_part, font=fontObj)
                                    line_y = yPos + text_height // 2  # Middle of the text
                                    v.line((xPos, line_y, xPos + text_width, line_y), fill=color, width=1)
                                    xPos += text_width
                                else:
                                    p.text((xPos, yPos), s_part, font=fontObj, fill=color)
                                    xPos += v.textlength(s_part, font=fontObj)

    real_y = ofs[1] + adj_y + dy
    return (0, dy, real_y)


def make(name, id, content, icon):
    check_text_lengths(name, id, content)
    img = BASE_IMAGE.copy()

    icon = fetch_icon_image(icon)
    icon = icon.resize((720, 720), Image.LANCZOS)
    icon = icon.convert("L")
    icon_filtered = ImageEnhance.Brightness(icon)

    img.paste(icon_filtered.enhance(0.7), (0, 0))
    img.paste(BASE_GD_IMAGE, (0, 0), BASE_GD_IMAGE)

    tx = ImageDraw.Draw(img)

    tsize_t = drawText(img, (890, 270), content, size=55, color=(255, 255, 255, 255), split_len=20)

    name_y = tsize_t[2] + 40
    tsize_name = drawText(img, (890, name_y), f"@{name}", size=28, color=(255, 255, 255, 255), split_len=25, disable_dot_wrap=True)

    id_y = name_y + tsize_name[1] + 4
    drawText(img, (890, id_y), id, size=18, color=(180, 180, 180, 255), split_len=45, disable_dot_wrap=True)

    tx.text((1070, 694), BRAND, font=MPLUS_FONT, fill=(120, 120, 120, 255))

    file = io.BytesIO()
    img.save(file, format="PNG", quality=95)
    file.seek(0)
    return file


def colorMake(name, id, content, icon):
    check_text_lengths(name, id, content)
    img = BASE_IMAGE.copy()

    icon = fetch_icon_image(icon)
    icon = icon.resize((720, 720), Image.LANCZOS)

    img.paste(icon, (0, 0))
    img.paste(BASE_GD_IMAGE, (0, 0), BASE_GD_IMAGE)

    tx = ImageDraw.Draw(img)

    tsize_t = drawText(img, (890, 270), content, size=55, color=(255, 255, 255, 255), split_len=20)

    name_y = tsize_t[2] + 40
    tsize_name = drawText(img, (890, name_y), f"@{name}", size=28, color=(255, 255, 255, 255), split_len=25, disable_dot_wrap=True)

    id_y = name_y + tsize_name[1] + 4
    drawText(img, (890, id_y), id, size=18, color=(180, 180, 180, 255), split_len=45, disable_dot_wrap=True)

    tx.text((1070, 694), BRAND, font=MPLUS_FONT, fill=(120, 120, 120, 255))

    file = io.BytesIO()
    img.save(file, format="PNG", quality=95)
    file.seek(0)
    return file


def reverseMake(name, id, content, icon):
    check_text_lengths(name, id, content)
    img = BASE_IMAGE.copy()

    icon = fetch_icon_image(icon)
    icon = icon.resize((720, 720), Image.LANCZOS)
    icon = icon.convert("L")
    icon_filtered = ImageEnhance.Brightness(icon)

    img.paste(icon_filtered.enhance(0.7), (570, 0))
    img.paste(BASE_RV_IMAGE, (0, 0), BASE_RV_IMAGE)

    tx = ImageDraw.Draw(img)

    tsize_t = drawText(img, (390, 270), content, size=55, color=(255, 255, 255, 255), split_len=20)

    name_y = tsize_t[2] + 40
    tsize_name = drawText(img, (390, name_y), f"@{name}", size=28, color=(255, 255, 255, 255), split_len=25, disable_dot_wrap=True)

    id_y = name_y + tsize_name[1] + 4
    drawText(img, (390, id_y), id, size=18, color=(180, 180, 180, 255), split_len=45, disable_dot_wrap=True)

    tx.text((6, 694), BRAND, font=MPLUS_FONT, fill=(120, 120, 120, 255))

    file = io.BytesIO()
    img.save(file, format="PNG", quality=95)
    file.seek(0)
    return file


def reverseColorMake(name, id, content, icon):
    check_text_lengths(name, id, content)
    img = BASE_IMAGE.copy()

    icon = fetch_icon_image(icon)
    icon = icon.resize((720, 720), Image.LANCZOS)

    img.paste(icon, (570, 0))
    img.paste(BASE_RV_IMAGE, (0, 0), BASE_RV_IMAGE)

    tx = ImageDraw.Draw(img)

    tsize_t = drawText(img, (390, 270), content, size=55, color=(255, 255, 255, 255), split_len=20)

    name_y = tsize_t[2] + 40
    tsize_name = drawText(img, (390, name_y), f"@{name}", size=28, color=(255, 255, 255, 255), split_len=25, disable_dot_wrap=True)

    id_y = name_y + tsize_name[1] + 4
    drawText(img, (390, id_y), id, size=18, color=(180, 180, 180, 255), split_len=45, disable_dot_wrap=True)

    tx.text((6, 694), BRAND, font=MPLUS_FONT, fill=(120, 120, 120, 255))

    file = io.BytesIO()
    img.save(file, format="PNG", quality=95)
    file.seek(0)
    return file


def whiteMake(name, id, content, icon):
    check_text_lengths(name, id, content)
    img = BASE_IMAGE.copy()

    icon = fetch_icon_image(icon).convert("RGBA")
    icon = icon.resize((720, 720), Image.LANCZOS)

    img.paste(icon, (0, 0), icon)
    img.paste(BASE_GD_W_IMAGE, (0, 0), BASE_GD_W_IMAGE)

    tx = ImageDraw.Draw(img)

    tsize_t = drawText(img, (890, 270), content, size=55, color=(0, 0, 0, 0), split_len=20)

    name_y = tsize_t[2] + 40
    tsize_name = drawText(img, (890, name_y), f"@{name}", size=28, color=(0, 0, 0, 0), split_len=25, disable_dot_wrap=True)

    id_y = name_y + tsize_name[1] + 4
    drawText(img, (890, id_y), id, size=18, color=(90, 90, 90, 255), split_len=45, disable_dot_wrap=True)

    tx.text((1070, 694), BRAND, font=MPLUS_FONT, fill=(120, 120, 120, 255))

    file = io.BytesIO()
    img.save(file, format="PNG", quality=95)
    file.seek(0)
    return file


def reverseWhiteMake(name, id, content, icon):
    check_text_lengths(name, id, content)
    img = BASE_IMAGE.copy()

    icon = fetch_icon_image(icon).convert("RGBA")
    icon = icon.resize((720, 720), Image.LANCZOS)

    img.paste(icon, (570, 0), icon)
    img.paste(BASE_RV_W_IMAGE, (0, 0), BASE_RV_W_IMAGE)

    tx = ImageDraw.Draw(img)

    tsize_t = drawText(img, (390, 270), content, size=55, color=(0, 0, 0, 0), split_len=20)

    name_y = tsize_t[2] + 40
    tsize_name = drawText(img, (390, name_y), f"@{name}", size=28, color=(0, 0, 0, 0), split_len=25, disable_dot_wrap=True)

    id_y = name_y + tsize_name[1] + 4
    drawText(img, (390, id_y), id, size=18, color=(90, 90, 90, 255), split_len=45, disable_dot_wrap=True)

    tx.text((6, 694), BRAND, font=MPLUS_FONT, fill=(110, 110, 110, 255))

    file = io.BytesIO()
    img.save(file, format="PNG", quality=95)
    file.seek(0)
    return file


# --- Streamlit UI ---

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
    name = st.text_input("Name", value="SAMPLE", max_chars=MAX_NAME_LEN)
    id_ = st.text_input("ID", value="", max_chars=MAX_ID_LEN)
    content = st.text_area("Content", value="Make it a Quote", max_chars=MAX_CONTENT_LEN)
    icon = st.text_input(
        "Icon URL", value="https://cdn.discordapp.com/embed/avatars/0.png"
    )
    type_ = st.selectbox("Type", list(TYPE_MAKERS.keys()))
    submitted = st.form_submit_button("Generate")

if submitted:
    if not icon.strip():
        st.error("Icon URL is required")
    else:
        with st.spinner("Generating image..."):
            try:
                image_io = TYPE_MAKERS[type_](name, id_, content, icon)
            except (IconFetchError, ValueError) as e:
                st.error(str(e))
            except Exception:
                st.error("Failed to generate image")
            else:
                st.image(image_io, use_container_width=True)
                st.download_button(
                    "Download PNG",
                    data=image_io.getvalue(),
                    file_name="quote.png",
                    mime="image/png",
                )
