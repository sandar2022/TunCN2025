import streamlit as st
from gtts import gTTS
import io
import requests
import pandas as pd
import re
from PIL import Image
import os
import base64
import json
import socket
from contextlib import closing

# ---------------- CONFIG ----------------
GOOGLE_API_KEY = "AIzaSyBZSRyGFaD660vlPAeibkkDjlLNgClI4o0"

# ---------------- SESSION DEFAULTS ----------------
if 'scanned_words' not in st.session_state:
    st.session_state.scanned_words = []
if 'extracted_text' not in st.session_state:
    st.session_state.extracted_text = ""
if 'word_details' not in st.session_state:
    st.session_state.word_details = {}
if 'manual_words' not in st.session_state:
    st.session_state.manual_words = []
if 'audio_cache' not in st.session_state:
    st.session_state.audio_cache = {}  # maps text -> bytes
if 'offline_mode' not in st.session_state:
    st.session_state.offline_mode = False
if 'last_translation' not in st.session_state:
    st.session_state.last_translation = {"original": "", "translated": ""}

# ----------------- Utilities -----------------
def internet_available(host="8.8.8.8", port=53, timeout=1):
    """Quick network check (not perfect but useful)."""
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            return True
    except Exception:
        return False

def mark_offline():
    st.session_state.offline_mode = True

# ---------------- TRANSLATION (safe wrappers) ----------------
def google_translate_english_to_chinese_safe(text):
    """Translate English->Chinese with graceful fallback (returns None on failure)."""
    if not internet_available():
        mark_offline()
        return None
    try:
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {"q": text, "source": "en", "target": "zh-CN", "format": "text", "key": GOOGLE_API_KEY}
        response = requests.post(url, data=params, timeout=6)
        result = response.json()
        if "data" in result and "translations" in result["data"]:
            return result["data"]["translations"][0]["translatedText"]
        else:
            # treat as failure
            mark_offline()
            return None
    except Exception:
        mark_offline()
        return None

def google_translate_chinese_to_english_safe(text):
    """Translate Chinese->English with graceful fallback (returns None on failure)."""
    if not internet_available():
        mark_offline()
        return None
    try:
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {"q": text, "source": "zh-CN", "target": "en", "format": "text", "key": GOOGLE_API_KEY}
        response = requests.post(url, data=params, timeout=6)
        result = response.json()
        if "data" in result and "translations" in result["data"]:
            return result["data"]["translations"][0]["translatedText"]
        else:
            mark_offline()
            return None
    except Exception:
        mark_offline()
        return None

# ---------------- VISION OCR (safe wrapper) ----------------
def google_vision_ocr_extract_text_safe(image):
    """Use Google Vision API, fall back gracefully (returns '' on failure)."""
    if not internet_available():
        mark_offline()
        return ""
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        content = img_byte_arr.getvalue()
        image_content = base64.b64encode(content).decode('utf-8')

        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
        payload = {
            "requests": [
                {
                    "image": {"content": image_content},
                    "features": [{"type": "TEXT_DETECTION", "maxResults": 50}],
                    "imageContext": {"languageHints": ["zh", "zh-TW", "zh-CN", "en"]}
                }
            ]
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=8)
        result = response.json()
        if 'error' in result:
            mark_offline()
            return ""
        if 'responses' in result and result['responses']:
            text_annotations = result['responses'][0].get('textAnnotations', [])
            if text_annotations:
                return text_annotations[0].get('description', '').strip()
        return ""
    except Exception:
        mark_offline()
        return ""

# ---------------- IMAGE PREP ----------------
def enhance_image_for_ocr(image):
    try:
        if image.mode != 'RGB':
            image = image.convert('RGB')
        width, height = image.size
        if width < 800 or height < 800:
            scale_factor = max(800/width, 800/height)
            new_size = (int(width * scale_factor), int(height * scale_factor))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        return image
    except Exception:
        return image

# ---------------- EXTRACT WORDS ----------------
def extract_individual_chinese_words(text):
    if not text:
        return []
    chinese_words = re.findall(r'[\u4e00-\u9fff]{1,4}', text)
    common_single_chars = {'的', '了', '是', '在', '有', '和', '就', '不', '我', '你', '他'}
    filtered_words = [word for word in chinese_words if len(word) > 1 or word not in common_single_chars]
    seen = set()
    unique_words = []
    for word in filtered_words:
        if word not in seen:
            seen.add(word)
            unique_words.append(word)
    return unique_words

# ---------------- ONLINE DICTIONARY ----------------
def search_online_dictionary(word):
    try:
        if not internet_available():
            mark_offline()
            return None
        apis = [(f"https://hanzi-api.vercel.app/api/definition/{word}", "HanziAPI")]
        for api_url, source in apis:
            try:
                response = requests.get(api_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data and 'definition' in data:
                        return {"pinyin": data.get('pinyin', 'N/A'), "meaning": data['definition'], "source": source}
            except Exception:
                continue
        return None
    except Exception:
        return None

# ---------------- LOCAL DICTIONARY & PINYIN ----------------
def generate_smart_meaning(word):
    char_meanings = {
        "爸": "father", "爷": "grandfather", "奶": "grandmother", "妈": "mother",
        "哥": "older brother", "弟": "younger brother", "姐": "older sister",
        "妹": "younger sister", "兄": "older brother", "朋": "friend", "友": "friend",
        "子": "child", "女": "woman", "男": "man", "孩": "child", "儿": "child",
        "亲": "parent/relative", "戚": "relative", "家": "family/home", "属": "belong/relative",
        "舅": "maternal uncle", "姨": "maternal aunt", "伯": "paternal uncle",
        "叔": "paternal uncle", "姑": "paternal aunt", "婶": "aunt", "侄": "nephew",
        "甥": "nephew", "孙": "grandchild", "起": "rise", "立": "stand", "坐": "sit",
        "下": "down", "举": "lift", "手": "hand", "工": "work/worker", "人": "person",
        "医": "medical", "生": "life/student", "农": "farming", "老": "old", "师": "teacher",
        "学": "study", "校": "school", "员": "member", "警": "police", "兵": "soldier",
        "商": "business", "官": "official", "读": "read", "书": "book", "写": "write",
        "字": "character", "画": "draw/painting", "文": "language/writing", "教": "teach",
        "课": "lesson", "本": "book", "你好": "hello", "谢谢": "thank you", "再见": "goodbye",
        "朋友": "friend", "学校": "school", "老师": "teacher", "学生": "student",
        "早上": "morning", "晚上": "evening", "今天": "today", "明天": "tomorrow",
        "爸爸": "father", "妈妈": "mother", "哥哥": "older brother", "弟弟": "younger brother",
        "姐姐": "older sister", "妹妹": "younger sister", "爷爷": "grandfather", "奶奶": "grandmother",
        "舅舅": "maternal uncle", "阿姨": "maternal aunt", "伯伯": "paternal uncle",
        "叔叔": "paternal uncle", "姑姑": "paternal aunt", "起立": "stand up", "坐下": "sit down",
        "举手": "raise hand", "河流": "river", "海洋": "ocean", "公路": "highway", "画图": "drawing",
    }
    if word in char_meanings:
        return char_meanings[word]
    if len(word) == 1:
        return "Single character - meaning unknown"
    meaning_parts = []
    for char in word:
        if char in char_meanings:
            meaning_parts.append(char_meanings[char])
    if meaning_parts:
        return f"Based on characters: {' + '.join(meaning_parts)}"
    else:
        return "Word meaning unknown"

def generate_smart_pinyin(word):
    pinyin_map = {
        '爸': 'bà', '爷': 'yé', '奶': 'nǎi', '妈': 'mā', '哥': 'gē', '弟': 'dì',
        '姐': 'jiě', '妹': 'mèi', '兄': 'xiōng', '工': 'gōng', '人': 'rén',
        '医': 'yī', '生': 'shēng', '农': 'nóng', '学': 'xué', '校': 'xiào',
        '上': 'shàng', '下': 'xià', '读': 'dú', '书': 'shū', '写': 'xiě', '字': 'zì',
        '说': 'shuō', '话': 'huà', '做': 'zuò', '手': 'shǒu', '作': 'zuò',
        '拍': 'pāi', '球': 'qiú', '花': 'huā', '园': 'yuán', '衣': 'yī', '服': 'fú',
        '大': 'dà', '小': 'xiǎo', '桥': 'qiáo', '画': 'huà', '树': 'shù', '晚': 'wǎn',
        '早': 'zǎo', '天': 'tiān', '我': 'wǒ', '你': 'nǐ', '他': 'tā', '是': 'shì',
        '不': 'bù', '好': 'hǎo', '的': 'de', '了': 'le', '在': 'zài', '有': 'yǒu',
        '河': 'hé', '流': 'liú', '海': 'hǎi', '洋': 'yáng', '公': 'gōng', '路': 'lù',
        '们': 'men', '图': 'tú', '舅': 'jiù', '姨': 'yí', '伯': 'bó', '叔': 'shū',
        '姑': 'gū', '起': 'qǐ', '立': 'lì', '坐': 'zuò', '举': 'jǔ',
    }
    common_pinyin = {
        "你好": "nǐ hǎo", "谢谢": "xiè xie", "再见": "zài jiàn",
        "朋友": "péng you", "学校": "xué xiào", "老师": "lǎo shī", "学生": "xué sheng",
        "早上": "zǎo shang", "晚上": "wǎn shang", "今天": "jīn tiān", "明天": "míng tiān",
        "舅舅": "jiù jiu", "阿姨": "ā yí", "伯伯": "bó bo", "叔叔": "shū shu",
        "姑姑": "gū gu", "起立": "qǐ lì", "坐下": "zuò xià", "举手": "jǔ shǒu",
        "河流": "hé liú", "海洋": "hǎi yáng", "公路": "gōng lù", "画图": "huà tú",
    }
    if word in common_pinyin:
        return common_pinyin[word]
    pinyin_parts = [pinyin_map.get(char, char) for char in word]
    return " ".join(pinyin_parts)

# ---------------- AUDIO (instant + cache) ----------------
def generate_audio_bytes(text):
    """Generate audio bytes (gTTS) and cache them for instant replay."""
    if text in st.session_state.audio_cache:
        return st.session_state.audio_cache[text]
    try:
        buf = io.BytesIO()
        # Use zh-CN (Chinese). If text is in English, you might want to set lang='en' for clearer English TTS.
        # We'll use zh for Chinese text, and en for pure-English text when needed.
        lang = 'zh-cn' if re.search(r'[\u4e00-\u9fff]', text) else 'en'
        tts = gTTS(text=text, lang=lang)
        tts.write_to_fp(buf)
        buf.seek(0)
        audio_bytes = buf.getvalue()
        st.session_state.audio_cache[text] = audio_bytes
        return audio_bytes
    except Exception:
        # audio generation might fail offline; just return None
        return None

def play_audio_immediate(text):
    """Play audio using Streamlit st.audio and HTML fallback. Uses cached bytes when available."""
    audio_bytes = generate_audio_bytes(text)
    if audio_bytes:
        audio_buffer = io.BytesIO(audio_bytes)
        st.audio(audio_buffer, format='audio/mp3')
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        audio_html = f"""<audio controls autoplay>
            <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
            Your browser does not support the audio element.
        </audio>"""
        st.markdown(audio_html, unsafe_allow_html=True)
        return True
    else:
        st.warning("Audio generation unavailable (offline or error).")
        return False

# ---------------- GET WORD DETAILS (keeps local dictionary logic) ----------------
def get_word_details(word):
    """Return pinyin, meaning, and source; also attempt online lookup and translation, with offline fallback."""
    if word in st.session_state.word_details:
        return st.session_state.word_details[word]

    # 1) Try online dictionary
    online = search_online_dictionary(word)
    if online:
        details = online
    else:
        # 2) Try translation zh->en to get meaning if online dictionary not present
        translated_meaning = google_translate_chinese_to_english_safe(word)
        if translated_meaning:
            details = {"pinyin": generate_smart_pinyin(word), "meaning": translated_meaning, "source": "Google Translate"}
        else:
            # 3) fallback to local smart analysis
            details = {"pinyin": generate_smart_pinyin(word), "meaning": generate_smart_meaning(word), "source": "Smart Analysis (Offline)"}
    st.session_state.word_details[word] = details
    return details

# ---------------- DISPLAY word details (bilingual) ----------------
def display_word_details(word, show_original_english=None):
    """Display Chinese word with pinyin and English meaning. Optionally show original English input."""
    details = get_word_details(word)
    col1, col2 = st.columns([2, 1])
    with col1:
        # Show original English if present (from translation)
        if show_original_english:
            st.caption(f"Original English: {show_original_english}")
        st.subheader(f"📖 {word}")
        st.markdown(f"**Pinyin:** {details.get('pinyin','-')}")
        st.markdown(f"**Meaning (EN):** {details.get('meaning','-')}")
        st.markdown(f"**Source:** {details.get('source','-')}")
    with col2:
        st.subheader("🎵 Pronunciation")
        play_key = f"play_{word}"
        if st.button(f"▶️ Play", key=play_key):
            # Try to play Chinese word audio first
            played = play_audio_immediate(word)
            # If offline and the meaning is English text, also offer English playback
            if not played and details.get('meaning'):
                play_audio_immediate(details['meaning'])

# ---------------- PROCESS UPLOADED FILE ----------------
def process_uploaded_file(uploaded_file):
    try:
        if uploaded_file.type.startswith('image/'):
            image = Image.open(uploaded_file)
            enhanced = enhance_image_for_ocr(image)
            extracted_text = google_vision_ocr_extract_text_safe(enhanced)
            if extracted_text and extracted_text.strip():
                st.success("✅ Text successfully extracted using Google Vision OCR")
                words = extract_individual_chinese_words(extracted_text)
                return words, extracted_text
            else:
                return [], "No text found in image using Google Vision OCR or OCR failed (offline)"
        elif uploaded_file.type == 'text/plain':
            text = uploaded_file.getvalue().decode('utf-8')
            words = extract_individual_chinese_words(text)
            return words, text
        else:
            return [], "Unsupported file type"
    except Exception as e:
        return [], f"Error processing file: {str(e)}"

# ---------------- HELPER DETECTION ----------------
def is_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def is_english(text):
    return bool(re.search(r'[A-Za-z]', text)) and not is_chinese(text)

# ---------------- APP UI ----------------
st.title("🔍 Chinese Dictionary Explorer — Bilingual & Offline Friendly")
st.markdown("Type Chinese or English text, upload images, or click sample words. The app will translate English → Chinese, use local dictionary if offline, and play audio instantly.")

# Show offline banner when offline
if st.session_state.offline_mode:
    st.warning("⚠️ Offline Mode: some online services (Translate/Vision) are unavailable. Using local dictionary & cached audio where possible.")

# --- Manual Input (Chinese or English) ---
st.header("📝 Type Chinese or English Text")

# Use a form to handle text input and buttons together
with st.form("text_input_form", clear_on_submit=True):
    manual_input = st.text_area(
        "Enter Chinese or English text (separate words with spaces or new lines):",
        placeholder="Examples: 你好 谢谢  学校  OR  good morning",
        height=120
    )
    
    col1, col2 = st.columns(2)
    with col1:
        process_manual = st.form_submit_button("✨ Process Text", type="primary", use_container_width=True)
    with col2:
        clear_manual = st.form_submit_button("🗑️ Clear Text", use_container_width=True)

if process_manual and manual_input:
    with st.spinner("Processing text..."):
        # If English -> translate first
        if is_english(manual_input) and not is_chinese(manual_input):
            translated = google_translate_english_to_chinese_safe(manual_input)
            if translated:
                st.info(f"🌐 Translated to Chinese: {translated}")
                st.session_state.last_translation = {"original": manual_input, "translated": translated}
                manual_words = extract_individual_chinese_words(translated)
                # Show bilingual lines for user clarity
                st.success(f"✅ Extracted {len(manual_words)} Chinese words from translation: {', '.join(manual_words)}")
                st.session_state.manual_words = manual_words
                # Pre-generate audio for instant playback
                for w in manual_words:
                    generate_audio_bytes(w)
            else:
                st.warning("⚠️ Translation unavailable — falling back to local extraction (treating as Chinese).")
                # fallback: treat input as Chinese attempt (extract any Chinese characters)
                manual_words = extract_individual_chinese_words(manual_input)
                st.session_state.manual_words = manual_words
        else:
            manual_words = extract_individual_chinese_words(manual_input)
            st.session_state.manual_words = manual_words
            # Pre-generate audio for each word
            for w in manual_words:
                generate_audio_bytes(w)
    if manual_words:
        st.success(f"✅ Found {len(manual_words)} Chinese words: {', '.join(manual_words)}")
    else:
        st.warning("❌ No Chinese words found in the text")

if clear_manual:
    # Clear all relevant session state variables
    st.session_state.manual_words = []
    st.session_state.scanned_words = []
    st.session_state.extracted_text = ""
    st.session_state.last_translation = {"original": "", "translated": ""}
    st.success("Text area cleared!")

# Check if we need to clear the text area and reset the trigger
if st.session_state.get('clear_text_trigger', False):
    st.session_state.clear_text_trigger = False
    # This will force a rerun with empty text
    st.rerun()
    
# --- File Upload ---
st.header("📎 Upload Image or Text File for OCR")
st.markdown("Upload PNG/JPG images or TXT files. OCR uses Google Vision; if offline the app will notify and fallback to local where possible.")
uploaded_file = st.file_uploader("Choose image or text file", type=['png', 'jpg', 'jpeg', 'txt'])
if uploaded_file is not None:
    with st.spinner("Processing file with Google Vision OCR..."):
        words, extracted_text = process_uploaded_file(uploaded_file)
        st.session_state.scanned_words = words
        st.session_state.extracted_text = extracted_text
        # Pre-generate audio for found words
        for w in words:
            generate_audio_bytes(w)
    if words:
        st.success(f"✅ Found {len(words)} Chinese words: {', '.join(words)}")
    else:
        st.warning("❌ No Chinese words found or OCR failed")
    if st.session_state.extracted_text and st.session_state.extracted_text != "No text found in image using Google Vision OCR":
        with st.expander("View Extracted Text"):
            st.text_area("OCR Result", st.session_state.extracted_text, height=150, key="extracted_text")

# --- Quick Single Word Search (Chinese or English) ---
st.header("🔍 Quick Single Word Search")
quick_col1, quick_col2 = st.columns([3, 1])
with quick_col1:
    single_word = st.text_input("Enter one Chinese word or English phrase:", placeholder="Example: 你好  OR  good morning", key="single_word")
with quick_col2:
    quick_search = st.button("Search", use_container_width=True)

if quick_search and single_word:
    if is_english(single_word) and not is_chinese(single_word):
        translated = google_translate_english_to_chinese_safe(single_word)
        if translated:
            st.markdown("---")
            st.info(f"🌐 Translated to Chinese: **{translated}**")
            translated_words = extract_individual_chinese_words(translated)
            if translated_words:
                # Pre-generate audio
                for w in translated_words:
                    generate_audio_bytes(w)
                for w in translated_words:
                    st.markdown("---")
                    display_word_details(w, show_original_english=single_word)
            else:
                st.warning("No Chinese word extracted from the translation.")
        else:
            st.warning("Translation failed; showing local analysis instead.")
            # fallback: try to show the English itself (with pinyin unknown)
            st.info(f"Original English: {single_word}")
    else:
        if re.search(r'[\u4e00-\u9fff]', single_word):
            st.markdown("---")
            display_word_details(single_word.strip())
        else:
            st.warning("Please enter a Chinese character or English text to translate.")

# --- Display Results ---
st.markdown("---")
st.header("📚 Processing Results")
all_words = st.session_state.scanned_words + st.session_state.manual_words

if all_words:
    st.success(f"🎉 Processing {len(all_words)} words")
    # Pre-generate audio for all words for instant playback
    for w in all_words:
        generate_audio_bytes(w)
    for i, word in enumerate(all_words):
        st.markdown("---")
        # If we have a last translation mapping that produced these words, show original english
        show_original = None
        if st.session_state.last_translation and st.session_state.last_translation.get("translated"):
            if word in extract_individual_chinese_words(st.session_state.last_translation["translated"]):
                show_original = st.session_state.last_translation.get("original")
        display_word_details(word, show_original_english=show_original)
else:
    st.info("👆 Enter Chinese/English text above, use quick search, or upload a file to get started")
    st.markdown("### 💡 Try these sample words:")
    cols = st.columns(4)
    sample_words = ["你好", "谢谢", "朋友", "学校", "妈妈", "老师", "学生", "早上", "说话", "拍球", "河流", "穿衣服", "晚上", "读书", "唱歌", "写字", "汽车", "飞机", "海洋", "公路", "画图", "自行车", "做作业", "做手工", "中午", "树木", "花园", "高山", "火箭", "玩积木", "大桥", "农民", "爸爸", "爷爷", "哥哥", "姐妹", "兄弟", "工人", "渔民", "医生", "上学", "放学", "你", "我", "他", "们", "是", "再见", "我们", "你们", "他们", "我是老师", "他是学生", "我们是朋友", "再见，老师！", "舅舅", "阿姨", "伯伯", "叔叔", "姑姑", "起立", "坐下", "举手", "男", "女"]
    for i, word in enumerate(sample_words):
        with cols[i % 4]:
            if st.button(word, use_container_width=True, key=f"sample_{i}"):
                st.session_state.manual_words = [word]
                # pre-generate audio
                generate_audio_bytes(word)
                st.rerun()

# --- Clear Button ---
if all_words:
    if st.button("Clear All Words", type="secondary"):
        st.session_state.scanned_words = []
        st.session_state.manual_words = []
        st.session_state.extracted_text = ""
        st.session_state.last_translation = {"original": "", "translated": ""}
        st.rerun()

# --- Sidebar Info ---
with st.sidebar:
    st.markdown("### 📊 Current Status")
    st.write(f"Manual words: {len(st.session_state.manual_words)}")
    st.write(f"File words: {len(st.session_state.scanned_words)}")
    st.write(f"Total: {len(all_words)} words")
    st.markdown("### 🔧 Mode")
    if st.session_state.offline_mode:
        st.write("🔴 Offline Mode (using local dictionary & cached audio)")
    else:
        st.write("🟢 Online Mode (Google services available)")
    st.markdown("### 🎯 Features")
    st.write("• Type Chinese or English (auto-translate English → Chinese)")
    st.write("• Upload images/text files (Google Vision OCR; fallback to offline)")
    st.write("• Local dictionary + online lookup")
    st.write("• Instant audio playback (cached)")
    st.write("• Download audio via browser controls (right-click audio)")
