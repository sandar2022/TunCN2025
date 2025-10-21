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

# Configuration
GOOGLE_API_KEY = "AIzaSyBZSRyGFaD660vlPAeibkkDjlLNgClI4o0"

def google_translate_chinese_to_english(text):
    """Translate Chinese text using Google Translate REST API + API key"""
    try:
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {
            "q": text,
            "source": "zh-CN",
            "target": "en",
            "format": "text",
            "key": GOOGLE_API_KEY
        }
        response = requests.post(url, data=params)
        result = response.json()
        
        if "data" in result and "translations" in result["data"]:
            translated = result["data"]["translations"][0]["translatedText"]
            return translated
        else:
            return "Translation unavailable"
    except Exception as e:
        return f"Error: {e}"

def google_vision_ocr_extract_text(image):
    """Use Google Cloud Vision API REST endpoint with API key"""
    try:
        # Convert PIL Image to base64
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        content = img_byte_arr.getvalue()
        image_content = base64.b64encode(content).decode('utf-8')

        # Prepare the request
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
        
        payload = {
            "requests": [
                {
                    "image": {
                        "content": image_content
                    },
                    "features": [
                        {
                            "type": "TEXT_DETECTION",
                            "maxResults": 50
                        }
                    ],
                    "imageContext": {
                        "languageHints": ["zh", "zh-TW", "zh-CN", "en"]
                    }
                }
            ]
        }

        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        result = response.json()

        # Check for errors
        if 'error' in result:
            st.error(f"Google Vision API Error: {result['error']['message']}")
            return ""

        # Extract text from response
        if 'responses' in result and result['responses']:
            text_annotations = result['responses'][0].get('textAnnotations', [])
            if text_annotations:
                full_text = text_annotations[0].get('description', '')
                return full_text.strip()

        return ""

    except Exception as e:
        st.error(f"Google Vision OCR failed: {str(e)}")
        return ""

def enhance_image_for_ocr(image):
    """Enhance image quality for better OCR results"""
    try:
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize image if too small
        width, height = image.size
        if width < 800 or height < 800:
            scale_factor = max(800/width, 800/height)
            new_size = (int(width * scale_factor), int(height * scale_factor))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        return image
    except Exception as e:
        st.warning(f"Image enhancement failed: {e}")
        return image

def extract_individual_chinese_words(text):
    """Extract individual Chinese words from text with improved filtering"""
    if not text:
        return []
        
    # Find all Chinese character sequences (1-4 characters)
    chinese_words = re.findall(r'[\u4e00-\u9fff]{1,4}', text)
    
    # Filter out single characters that are very common but might be noise
    common_single_chars = {'的', '了', '是', '在', '有', '和', '就', '不', '我', '你', '他'}
    filtered_words = [word for word in chinese_words if len(word) > 1 or word not in common_single_chars]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_words = []
    for word in filtered_words:
        if word not in seen:
            seen.add(word)
            unique_words.append(word)
    
    return unique_words

def process_uploaded_file(uploaded_file):
    """Process uploaded file and extract Chinese words using Google Vision OCR"""
    try:
        if uploaded_file.type.startswith('image/'):
            # Process image with Google Vision OCR
            image = Image.open(uploaded_file)
            
            # Enhance image for better OCR
            enhanced_image = enhance_image_for_ocr(image)
            
            # Extract text using Google Vision OCR
            extracted_text = google_vision_ocr_extract_text(enhanced_image)
            
            if extracted_text and extracted_text.strip():
                st.success("✅ Text successfully extracted using Google Vision OCR")
                words = extract_individual_chinese_words(extracted_text)
                return words, extracted_text
            else:
                return [], "No text found in image using Google Vision OCR"
                
        elif uploaded_file.type == 'text/plain':
            # Process text file
            text = uploaded_file.getvalue().decode('utf-8')
            words = extract_individual_chinese_words(text)
            return words, text
            
        else:
            return [], "Unsupported file type"
            
    except Exception as e:
        return [], f"Error processing file: {str(e)}"

def search_online_dictionary(word):
    """Search online Chinese dictionaries for word meaning"""
    try:
        # Try multiple API endpoints for better coverage
        apis = [
            (f"https://hanzi-api.vercel.app/api/definition/{word}", "HanziAPI"),
        ]
        
        for api_url, source in apis:
            try:
                response = requests.get(api_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data and 'definition' in data:
                        return {
                            "pinyin": data.get('pinyin', 'N/A'),
                            "meaning": data['definition'],
                            "source": source
                        }
            except:
                continue
        
        return None
    except Exception as e:
        return None

def generate_smart_meaning(word):
    """Generate a smart meaning for unknown words using comprehensive character analysis"""
    
    # Comprehensive character meanings dictionary
    char_meanings = {
        # Common nouns - people
        "爸": "father", "爷": "grandfather", "奶": "grandmother", "妈": "mother",
        "哥": "older brother", "弟": "younger brother", "姐": "older sister", 
        "妹": "younger sister", "兄": "older brother", "朋": "friend", "友": "friend",
        "子": "child", "女": "woman", "男": "man", "孩": "child", "儿": "child",
        "亲": "parent/relative", "戚": "relative", "家": "family/home", "属": "belong/relative",
        
        # Additional family members
        "舅": "maternal uncle", "姨": "maternal aunt", "伯": "paternal uncle", 
        "叔": "paternal uncle", "姑": "paternal aunt", "婶": "aunt",
        "侄": "nephew", "甥": "nephew", "孙": "grandchild",
        
        # Actions
        "起": "rise", "立": "stand", "坐": "sit", "下": "down", "举": "lift", "手": "hand",
        
        # Professions & social
        "工": "work/worker", "人": "person", "医": "medical", 
        "生": "life/student", "农": "farming", "老": "old", "师": "teacher", 
        "学": "study", "校": "school", "员": "member", 
        "警": "police", "兵": "soldier", "商": "business", "官": "official",
        
        # Education & writing
        "读": "read", "书": "book", "写": "write", "字": "character", "画": "draw/painting",
        "文": "language/writing", "教": "teach", "课": "lesson", "本": "book",
        
        # Common words dictionary
        "你好": "hello", "谢谢": "thank you", "再见": "goodbye", 
        "朋友": "friend", "学校": "school", "老师": "teacher", "学生": "student",
        "早上": "morning", "晚上": "evening", "今天": "today", "明天": "tomorrow",
        "爸爸": "father", "妈妈": "mother", "哥哥": "older brother", "弟弟": "younger brother",
        "姐姐": "older sister", "妹妹": "younger sister", "爷爷": "grandfather", "奶奶": "grandmother",
        "舅舅": "maternal uncle", "阿姨": "maternal aunt", "伯伯": "paternal uncle",
        "叔叔": "paternal uncle", "姑姑": "paternal aunt",
        "起立": "stand up", "坐下": "sit down", "举手": "raise hand",
        "河流": "river", "海洋": "ocean", "公路": "highway", "画图": "drawing",
    }
    
    # First check if it's a common word we know
    if word in char_meanings:
        return char_meanings[word]
    
    # For single characters
    if len(word) == 1:
        return "Single character - meaning unknown"
    
    # For multi-character words, try to analyze components
    meaning_parts = []
    for char in word:
        if char in char_meanings:
            meaning_parts.append(char_meanings[char])
    
    if meaning_parts:
        return f"Based on characters: {' + '.join(meaning_parts)}"
    else:
        return "Word meaning unknown"

def generate_smart_pinyin(word):
    """Generate a plausible pinyin for unknown words"""
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
    
    # Common word pinyin
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
    
    pinyin_parts = []
    for char in word:
        pinyin_parts.append(pinyin_map.get(char, char))
    return " ".join(pinyin_parts)

def generate_audio(text):
    """Generate audio using gTTS"""
    try:
        audio_buffer = io.BytesIO()
        tts = gTTS(text=text, lang='zh-cn')
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer
    except Exception as e:
        st.error(f"Audio generation failed: {e}")
        return None

def get_word_details(word):
    """Get detailed information for a word, with Google Translate fallback"""
    if word in st.session_state.word_details:
        return st.session_state.word_details[word]
    
    # Step 1: Try online dictionary
    online_result = search_online_dictionary(word)
    if online_result:
        result = online_result
        source = f"Online - {online_result['source']}"
    else:
        # Step 2: Try Google Translate API
        translated_meaning = google_translate_chinese_to_english(word)
        if translated_meaning and translated_meaning != "Translation unavailable" and not translated_meaning.startswith("Error"):
            result = {
                "pinyin": generate_smart_pinyin(word),
                "meaning": translated_meaning
            }
            source = "Google Translate"
        else:
            # Step 3: Fallback to internal smart meaning
            result = {
                "pinyin": generate_smart_pinyin(word),
                "meaning": generate_smart_meaning(word)
            }
            source = "Smart Analysis (Offline)"
    
    st.session_state.word_details[word] = {
        **result,
        "source": source
    }
    
    return st.session_state.word_details[word]

def display_word_details(word):
    """Display detailed information for a single word with iPhone-friendly audio"""
    details = get_word_details(word)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📖 {word}")
        st.info(f"**Pinyin:** {details['pinyin']}")
        st.info(f"**Meaning:** {details['meaning']}")
        st.info(f"**Source:** {details['source']}")
    
    with col2:
        st.subheader("🎵 Pronunciation")
        
        # Play button triggers audio generation
        play_button_key = f"play_{word}"
        if st.button(f"▶️ Play {word}", key=play_button_key):
            audio_buffer = generate_audio(word)
            if audio_buffer:
                audio_buffer.seek(0)
                # Streamlit native audio
                st.audio(audio_buffer, format='audio/mp3')
                
                # Download button
                st.download_button(
                    "📥 Download Audio",
                    audio_buffer.getvalue(),
                    file_name=f"{word}_pronunciation.mp3",
                    mime="audio/mp3",
                    key=f"download_{word}"
                )
                
                # Optional HTML audio fallback for iOS
                audio_base64 = base64.b64encode(audio_buffer.getvalue()).decode("utf-8")
                audio_html = f"""
                <audio controls>
                  <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                  Your browser does not support the audio element.
                </audio>
                """
                st.markdown(audio_html, unsafe_allow_html=True)


# Initialize session state
if 'scanned_words' not in st.session_state:
    st.session_state.scanned_words = []
if 'extracted_text' not in st.session_state:
    st.session_state.extracted_text = ""
if 'word_details' not in st.session_state:
    st.session_state.word_details = {}
if 'manual_words' not in st.session_state:
    st.session_state.manual_words = []

# MAIN APP
st.title("🔍 Chinese Dictionary Explorer")
st.markdown("Type Chinese words OR upload files to get meanings and audio pronunciation")

# MANUAL TEXT INPUT
st.header("📝 Type Chinese Words Here")
st.markdown("Enter Chinese words or text below (separated by spaces or new lines):")

manual_input = st.text_area(
    "Chinese Text Input:",
    placeholder="Type or paste Chinese words here...\nExamples: 你好 谢谢 我爱你 朋友 学校",
    height=100,
    key="manual_input_main"
)

col1, col2 = st.columns(2)
with col1:
    process_manual = st.button("✨ Process Text", type="primary", use_container_width=True)
with col2:
    clear_manual = st.button("🗑️ Clear Text", use_container_width=True)

if process_manual and manual_input:
    with st.spinner("Extracting Chinese words..."):
        manual_words = extract_individual_chinese_words(manual_input)
        st.session_state.manual_words = manual_words
    
    if manual_words:
        st.success(f"✅ Found {len(manual_words)} Chinese words: {', '.join(manual_words)}")
    else:
        st.warning("❌ No Chinese words found in the text")

if clear_manual:
    st.session_state.manual_words = []
    st.rerun()

# FILE UPLOAD SECTION
st.header("📎 Or Upload Files")
st.markdown("Upload images or text files to extract Chinese words using **Google Cloud Vision OCR**")

uploaded_file = st.file_uploader(
    "Choose image or text file",
    type=['png', 'jpg', 'jpeg', 'txt'],
    help="Supported: PNG, JPG, JPEG images or TXT files"
)

if uploaded_file is not None:
    with st.spinner("Processing file with Google Vision OCR..."):
        words, extracted_text = process_uploaded_file(uploaded_file)
        st.session_state.scanned_words = words
        st.session_state.extracted_text = extracted_text
    
    if words:
        st.success(f"✅ Found {len(words)} Chinese words: {', '.join(words)}")
    else:
        st.warning("❌ No Chinese words found")
        
    if st.session_state.extracted_text and st.session_state.extracted_text != "No text found in image using Google Vision OCR":
        with st.expander("View Extracted Text"):
            st.text_area("OCR Result", st.session_state.extracted_text, height=150, key="extracted_text")

# QUICK SEARCH
st.header("🔍 Quick Single Word Search")
quick_col1, quick_col2 = st.columns([3, 1])
with quick_col1:
    single_word = st.text_input("Enter one Chinese word:", placeholder="Example: 你好", key="single_word")
with quick_col2:
    st.write("")
    st.write("")
    quick_search = st.button("Search", use_container_width=True)

if quick_search and single_word:
    if re.search(r'[\u4e00-\u9fff]', single_word):
        st.markdown("---")
        display_word_details(single_word.strip())
    else:
        st.warning("Please enter a Chinese character")

# DISPLAY RESULTS
st.markdown("---")
st.header("📚 Processing Results")

# Combine words from both sources
all_words = st.session_state.scanned_words + st.session_state.manual_words

if all_words:
    st.success(f"🎉 Processing {len(all_words)} words")
    
    for i, word in enumerate(all_words):
        st.markdown("---")
        display_word_details(word)
        
else:
    st.info("👆 Enter Chinese words above or upload a file to get started")
    
    # Sample words
    st.markdown("### 💡 Try these sample words:")
    cols = st.columns(4)
    sample_words = ["你好", "谢谢", "朋友", "学校", "妈妈", "老师", "学生", "早上","说话","拍球","河流","穿衣服","晚上","读书","唱歌","写字","汽车","飞机"]
    
    for i, word in enumerate(sample_words):
        with cols[i % 4]:
            if st.button(word, use_container_width=True):
                st.session_state.manual_words = [word]
                st.rerun()

# Clear button
if all_words:
    if st.button("Clear All Words", type="secondary"):
        st.session_state.scanned_words = []
        st.session_state.manual_words = []
        st.session_state.extracted_text = ""
        st.rerun()

# Sidebar info
with st.sidebar:
    st.markdown("### 📊 Current Status")
    st.write(f"Manual words: {len(st.session_state.manual_words)}")
    st.write(f"File words: {len(st.session_state.scanned_words)}")
    st.write(f"Total: {len(all_words)} words")
    
    st.markdown("### 🎯 Features")
    st.write("• Type Chinese words directly")
    st.write("• Upload images/text files")
    st.write("• **Google Vision OCR**")
    st.write("• Get pinyin & meanings")
    st.write("• Audio pronunciation")
    st.write("• Download audio files")
    
    st.markdown("### 🔧 OCR Technology")
    st.success("✅ Google Cloud Vision API")
    st.write("• Better Chinese text recognition")
    st.write("• High accuracy")
    st.write("• Direct API integration")
