import streamlit as st
from gtts import gTTS
import io
import requests
import pandas as pd
import re
import pytesseract
from PIL import Image
import os
from google.cloud import vision
from google.cloud import translate_v2 as translate
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

def google_ocr_extract_chinese(image):
    """Use Google Cloud Vision API to extract Chinese text"""
    try:
        client = vision.ImageAnnotatorClient()

        # Convert PIL Image to bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        content = img_byte_arr.getvalue()

        image_vision = vision.Image(content=content)
        response = client.text_detection(image=image_vision)

        if response.error.message:
            st.warning(f"Google OCR Error: {response.error.message}")
            return ""

        if response.text_annotations:
            return response.text_annotations[0].description.strip()
        else:
            return ""
    except Exception as e:
        st.error(f"Google OCR failed: {e}")
        return ""


# Set page configuration
st.set_page_config(
    page_title="Chinese Dictionary Explorer",
    page_icon="🎌",
    layout="wide"
)

# Configure Tesseract path
try:
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    
    tesseract_found = False
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            tesseract_found = True
            break
    
    OCR_AVAILABLE = tesseract_found
    if OCR_AVAILABLE:
        st.sidebar.success("✅ Tesseract OCR Enabled")
    else:
        st.sidebar.warning("⚠️ Tesseract not found")
except:
    OCR_AVAILABLE = False
    st.sidebar.warning("⚠️ OCR features disabled")

# Initialize session state
if 'scanned_words' not in st.session_state:
    st.session_state.scanned_words = []
if 'extracted_text' not in st.session_state:
    st.session_state.extracted_text = ""
if 'word_details' not in st.session_state:
    st.session_state.word_details = {}
if 'manual_words' not in st.session_state:
    st.session_state.manual_words = []

def extract_individual_chinese_words(text):
    """Extract individual Chinese words from text"""
    chinese_words = re.findall(r'[\u4e00-\u9fff]{1,4}', text)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_words = []
    for word in chinese_words:
        if word not in seen:
            seen.add(word)
            unique_words.append(word)
    
    return unique_words

def process_image_with_ocr(image):
    """Process image with OCR and extract Chinese text"""
    try:
        try:
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            text = pytesseract.image_to_string(image, lang='chi_sim', config=custom_config)
        except:
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            text = pytesseract.image_to_string(image, lang='eng', config=custom_config)
        
        return text.strip()
    except Exception as e:
        return f"OCR Error: {e}"

def process_uploaded_file(uploaded_file):
    """Process uploaded file and extract Chinese words"""
    try:
        if uploaded_file.type.startswith('image/'):
            if not OCR_AVAILABLE:
                return [], "OCR not available. Please install Tesseract."
            
            image = Image.open(uploaded_file)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            width, height = image.size
            if width < 800 or height < 800:
                new_size = (max(800, width), max(800, height))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            extracted_text = process_image_with_ocr(image)
            
            if extracted_text and not extracted_text.startswith("OCR Error"):
                words = extract_individual_chinese_words(extracted_text)
                return words, extracted_text
            else:
                return [], extracted_text
                
        elif uploaded_file.type == 'text/plain':
            text = uploaded_file.getvalue().decode('utf-8')
            words = extract_individual_chinese_words(text)
            return words, text
            
        else:
            return [], "Unsupported file type"
            
    except Exception as e:
        return [], f"Error: {str(e)}"

def search_online_dictionary(word):
    """Search online Chinese dictionaries for word meaning"""
    try:
        # Try multiple API endpoints for better coverage
        apis = [
            (f"https://hanzi-api.vercel.app/api/definition/{word}", "HanziAPI"),
            (f"https://cc-cedict.org/wiki/search:{word}", "CC-CEDICT"),
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
    
    # EXPANDED COMPREHENSIVE CHARACTER MEANINGS DICTIONARY
    char_meanings = {
        # Common nouns - people
        "爸": "father", "爷": "grandfather", "奶": "grandmother", "妈": "mother",
        "哥": "older brother", "弟": "younger brother", "姐": "older sister", 
        "妹": "younger sister", "兄": "older brother", "朋": "friend", "友": "friend",
        "子": "child", "女": "woman", "男": "man", "孩": "child", "儿": "child",
        "亲": "parent/relative", "戚": "relative", "家": "family/home", "属": "belong/relative",
        
        # Additional family members
        "舅": "maternal uncle", "姨": "maternal aunt", "伯": "paternal uncle", 
        "叔": "paternal uncle", "姑": "paternal aunt", "婶": "aunt (wife of father's younger brother)",
        "侄": "nephew", "甥": "nephew (sister's son)", "孙": "grandchild",
        
        # Additional actions
        "起": "rise", "立": "stand", "坐": "sit", "下": "down", "举": "lift", "手": "hand",
        
        # Professions & social
        "工": "work/worker", "人": "person", "渔": "fishing", "医": "medical", 
        "生": "life/student", "农": "farming", "老": "old", "师": "teacher", 
        "学": "study", "校": "school", "生": "life/student", "员": "member", 
        "警": "police", "兵": "soldier", "商": "business", "官": "official",
        "民": "people", "众": "crowd", "群": "group", "队": "team",
        
        # Education & writing
        "读": "read", "书": "book", "写": "write", "字": "character", "画": "draw/painting",
        "文": "language/writing", "章": "chapter", "笔": "pen", "纸": "paper", "教": "teach",
        "课": "lesson", "本": "book", "知": "know", "识": "knowledge", "考": "test",
        
        # Communication
        "说": "speak", "话": "speech", "唱": "sing", "歌": "song", "语": "language",
        "言": "speech", "谈": "talk", "讲": "speak", "告": "tell", "诉": "tell",
        "问": "ask", "答": "answer", "叫": "call", "喊": "shout",
        
        # Actions & verbs
        "拍": "pat/clap", "做": "do", "作": "do/make", "走": "walk", "跑": "run",
        "吃": "eat", "喝": "drink", "看": "look/see", "听": "listen", "买": "buy",
        "卖": "sell", "来": "come", "去": "go", "开": "open", "关": "close",
        "坐": "sit", "站": "stand", "睡": "sleep", "醒": "wake", "玩": "play",
        "笑": "laugh", "哭": "cry", "想": "think", "思": "think", "爱": "love",
        "喜": "like", "欢": "happy", "恨": "hate", "怕": "fear", "忘": "forget",
        "记": "remember", "找": "find", "寻": "search", "等": "wait", "停": "stop",
        "始": "begin", "终": "end", "变": "change", "化": "change", "发": "send/develop",
        "展": "develop", "进": "enter/advance", "出": "exit", "入": "enter",
        "回": "return", "到": "arrive", "过": "pass", "经": "pass through",
        "通": "pass through", "行": "go/ok", "动": "move", "活": "live", "死": "die",
        "工": "work", "作": "work", "干": "do", "办": "handle", "理": "manage",
        "管": "manage", "治": "govern", "建": "build", "造": "make", "修": "repair",
        "改": "change", "革": "reform", "创": "create", "造": "create",
        
        # Body parts
        "手": "hand", "头": "head", "脚": "foot", "眼": "eye", "耳": "ear",
        "口": "mouth", "心": "heart", "身": "body", "脸": "face", "鼻": "nose",
        "舌": "tongue", "牙": "tooth", "发": "hair", "皮": "skin", "骨": "bone",
        "血": "blood", "肉": "meat", "脑": "brain", "腿": "leg", "臂": "arm",
        
        # Objects & things
        "球": "ball", "衣": "clothes", "服": "clothes", "花": "flower", "园": "garden",
        "树": "tree", "木": "wood", "桥": "bridge", "车": "vehicle", "房": "house",
        "门": "door", "窗": "window", "桌": "table", "椅": "chair", "床": "bed",
        "灯": "lamp", "电": "electricity", "机": "machine", "器": "device", "具": "tool",
        "刀": "knife", "碗": "bowl", "杯": "cup", "瓶": "bottle", "盒": "box",
        "包": "bag", "箱": "box", "钱": "money", "金": "gold/money", "银": "silver",
        "石": "stone", "铁": "iron", "钢": "steel", "玉": "jade", "宝": "treasure",
        
        # Nature & geography
        "天": "sky/day", "地": "ground", "水": "water", "火": "fire", "山": "mountain",
        "石": "stone", "日": "sun/day", "月": "moon/month", "星": "star", "云": "cloud",
        "雨": "rain", "雪": "snow", "风": "wind", "雷": "thunder", "电": "lightning",
        "江": "river", "河": "river", "湖": "lake", "海": "sea", "洋": "ocean",
        "流": "flow", "泉": "spring", "波": "wave", "浪": "wave", "岛": "island",
        "林": "forest", "森": "forest", "田": "field", "土": "soil", "沙": "sand",
        "原": "plain", "野": "field", "草": "grass", "花": "flower", "叶": "leaf",
        "根": "root", "枝": "branch", "果": "fruit", "实": "fruit", "种": "seed",
        
        # Time & space
        "年": "year", "月": "month", "日": "day", "时": "time", "间": "interval",
        "刻": "moment", "分": "minute", "秒": "second", "季": "season", "节": "festival",
        "春": "spring", "夏": "summer", "秋": "autumn", "冬": "winter", "晨": "morning",
        "晚": "evening/night", "早": "morning/early", "夜": "night", "午": "noon",
        "今": "now", "明": "bright/tomorrow", "昨": "yesterday", "去": "past", "未": "future",
        "上": "up/above", "下": "down/below", "中": "middle", "左": "left", "右": "right",
        "前": "front", "后": "back", "里": "inside", "外": "outside", "内": "inside",
        "旁": "side", "边": "side", "角": "corner", "顶": "top", "底": "bottom",
        "东": "east", "西": "west", "南": "south", "北": "north", "方": "direction",
        
        # Common adjectives/adverbs
        "大": "big", "小": "small", "多": "many", "少": "few", "长": "long", "短": "short",
        "高": "tall/high", "低": "low", "热": "hot", "冷": "cold", "新": "new", "旧": "old",
        "好": "good", "坏": "bad", "快": "fast", "慢": "slow", "美": "beautiful", "丑": "ugly",
        "强": "strong", "弱": "weak", "硬": "hard", "软": "soft", "轻": "light", "重": "heavy",
        "远": "far", "近": "near", "深": "deep", "浅": "shallow", "宽": "wide", "窄": "narrow",
        "直": "straight", "弯": "curved", "平": "flat", "安": "safe", "全": "complete",
        "危": "dangerous", "险": "dangerous", "难": "difficult", "易": "easy", "简": "simple",
        "复": "complex", "清": "clear", "楚": "clear", "模": "vague", "糊": "blurry",
        "真": "true", "假": "false", "正": "correct", "错": "wrong", "对": "correct",
        "同": "same", "异": "different", "特": "special", "别": "other", "普": "common",
        "通": "common", "常": "usual", "奇": "strange", "怪": "strange",
        
        # Pronouns & particles
        "我": "I/me", "你": "you", "他": "he/him", "她": "she/her", "它": "it",
        "们": "plural marker", "自": "self", "己": "self", "各": "each", "每": "every",
        "某": "certain", "这": "this", "那": "that", "哪": "which", "谁": "who",
        "什": "what", "怎": "how", "何": "what", "为": "for/because", "因": "because",
        "果": "result", "虽": "although", "然": "however", "但": "but", "而": "and",
        "且": "moreover", "或": "or", "乃": "is", "即": "namely", "则": "then",
        "虽": "although", "然": "thus", "但": "but", "却": "but", "倒": "instead",
        "反": "instead", "竟": "unexpectedly", "偏": "insist on", "就": "then",
        "才": "only then", "刚": "just", "曾": "once", "已": "already", "经": "already",
        "正": "just now", "在": "at/in", "着": "aspect marker", "了": "completed action",
        "过": "experience marker", "的": "of", "地": "adverbial marker", "得": "complement marker",
        "之": "of", "乎": "question particle", "吗": "question particle", "呢": "question particle",
        "吧": "suggestion particle", "啊": "exclamation", "呀": "exclamation", "哇": "exclamation",
        "哦": "oh", "嗯": "uh-huh", "唉": "alas", "喂": "hello", "嘿": "hey",
        
        # Numbers & quantities
        "一": "one", "二": "two", "三": "three", "四": "four", "五": "five",
        "六": "six", "七": "seven", "八": "eight", "九": "nine", "十": "ten",
        "百": "hundred", "千": "thousand", "万": "ten thousand", "亿": "hundred million",
        "零": "zero", "半": "half", "双": "double", "对": "pair", "单": "single",
        "全": "whole", "整": "whole", "部": "part", "分": "part", "些": "some",
        "点": "point", "第": "ordinal prefix", "初": "beginning",
        
        # Colors
        "红": "red", "黄": "yellow", "蓝": "blue", "绿": "green", "白": "white", "黑": "black",
        "紫": "purple", "灰": "gray", "粉": "pink", "棕": "brown", "橙": "orange",
        
        # Transportation & locations
        "路": "road", "街": "street", "道": "road", "巷": "alley", "弄": "lane",
        "公": "public", "共": "common", "交": "traffic", "通": "traffic", "运": "transport",
        "输": "transport", "车": "vehicle", "汽": "steam", "火": "fire", "船": "ship",
        "航": "navigation", "空": "air", "飞": "fly", "机": "machine", "场": "field",
        "站": "station", "港": "port", "码": "pier", "头": "head", "口": "port",
        "岸": "shore", "边": "side", "界": "border", "境": "border", "国": "country",
        "家": "country", "州": "state", "省": "province", "市": "city", "县": "county",
        "区": "district", "镇": "town", "村": "village", "庄": "village",
    }
    
    # EXPANDED COMMON WORD MEANINGS
    common_words = {
        # Basic greetings & phrases
        "你好": "hello", "您好": "hello (formal)", "你们好": "hello everyone", 
        "大家好": "hello everyone", "谢谢": "thank you", "感谢": "thanks", 
        "多谢": "many thanks", "对不起": "sorry", "抱歉": "apology", 
        "请原谅": "please forgive", "没关系": "it's okay", "不客气": "you're welcome",
        "请": "please", "请问": "may I ask", "再见": "goodbye", "再会": "see you again",
        "明天见": "see you tomorrow", "欢迎": "welcome", "欢迎光临": "welcome",
        
        # Time & dates
        "今天": "today", "明天": "tomorrow", "昨天": "yesterday", "现在": "now",
        "刚才": "just now", "以后": "later", "以前": "before", "将来": "future",
        "过去": "past", "早上": "morning", "早晨": "morning", "中午": "noon",
        "下午": "afternoon", "晚上": "evening", "夜晚": "night", "半夜": "midnight",
        "分钟": "minute", "小时": "hour", "时间": "time", "时候": "time",
        "日期": "date", "星期": "week", "周末": "weekend", "月份": "month",
        "年份": "year", "季节": "season", "春天": "spring", "夏天": "summer",
        "秋天": "autumn", "冬天": "winter",
        
        # People & relationships
        "朋友": "friend", "好朋友": "good friend", "男朋友": "boyfriend", 
        "女朋友": "girlfriend", "家人": "family", "家庭": "family", 
        "父母": "parents", "父亲": "father", "母亲": "mother", "爸爸": "dad",
        "妈妈": "mom", "儿子": "son", "女儿": "daughter", "兄弟": "brothers",
        "姐妹": "sisters", "哥哥": "older brother", "弟弟": "younger brother",
        "姐姐": "older sister", "妹妹": "younger sister", "爷爷": "grandpa",
        "奶奶": "grandma", "老师": "teacher", "学生": "student", "同学": "classmate",
        "同事": "colleague", "老板": "boss", "员工": "employee", "医生": "doctor",
        "护士": "nurse", "警察": "police", "司机": "driver", "工人": "worker",
        
        # Extended family relationships
        "舅舅": "maternal uncle", "阿姨": "maternal aunt", "伯伯": "paternal uncle (older)",
        "叔叔": "paternal uncle (younger)", "姑姑": "paternal aunt", "婶婶": "aunt",
        "侄子": "nephew", "侄女": "niece", "外甥": "nephew (sister's son)",
        "外甥女": "niece (sister's daughter)", "孙子": "grandson", "孙女": "granddaughter",
        
        # Classroom commands & actions
        "起立": "stand up", "坐下": "sit down", "举手": "raise hand",
        
        # Education & school
        "学校": "school", "大学": "university", "中学": "middle school", 
        "小学": "elementary school", "教室": "classroom", "学习": "study",
        "读书": "read/study", "考试": "exam", "练习": "practice", "作业": "homework",
        "课程": "course", "专业": "major", "教育": "education", "知识": "knowledge",
        "文化": "culture", "科学": "science", "技术": "technology", "数学": "math",
        "语文": "language", "英语": "English", "中文": "Chinese", "外语": "foreign language",
        
        # Work & business
        "工作": "work", "上班": "go to work", "下班": "get off work", 
        "公司": "company", "办公室": "office", "会议": "meeting", 
        "项目": "project", "业务": "business", "市场": "market", 
        "销售": "sales", "管理": "management", "经理": "manager", 
        "工资": "salary", "职业": "occupation", " career": "career",
        
        # Food & drinks
        "食物": "food", "食品": "food product", "吃饭": "eat meal", 
        "早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner", 
        "水果": "fruit", "苹果": "apple", "香蕉": "banana", "橘子": "orange",
        "蔬菜": "vegetables", "米饭": "rice", "面条": "noodles", "面包": "bread",
        "肉类": "meat", "牛肉": "beef", "猪肉": "pork", "鸡肉": "chicken",
        "鱼": "fish", "海鲜": "seafood", "汤": "soup", "饮料": "drink",
        "水": "water", "茶": "tea", "咖啡": "coffee", "牛奶": "milk",
        "酒": "alcohol", "啤酒": "beer",
        
        # Home & daily life
        "家": "home", "房子": "house", "房间": "room", "卧室": "bedroom",
        "厨房": "kitchen", "卫生间": "bathroom", "客厅": "living room",
        "家具": "furniture", "床": "bed", "桌子": "table", "椅子": "chair",
        "门": "door", "窗户": "window", "灯": "light", "电视": "TV",
        "电脑": "computer", "手机": "mobile phone", "网络": "internet",
        "衣服": "clothes", "鞋子": "shoes", "帽子": "hat", "包": "bag",
        
        # Transportation
        "交通": "transportation", "汽车": "car", "公共汽车": "bus", 
        "地铁": "subway", "火车": "train", "飞机": "airplane", 
        "自行车": "bicycle", "摩托车": "motorcycle", "出租车": "taxi",
        "车站": "station", "机场": "airport", "码头": "pier", 
        "道路": "road", "公路": "highway", "街道": "street", "桥梁": "bridge",
        
        # Nature & geography
        "河流": "river", "河": "river", "流": "flow", 
        "海洋": "ocean", "海": "sea", "洋": "ocean",
        "江湖": "rivers and lakes", "湖": "lake",
        "天空": "sky", "天气": "weather", "气候": "climate",
        "太阳": "sun", "月亮": "moon", "星星": "star", "地球": "earth",
        "山": "mountain", "山脉": "mountain range", "山峰": "mountain peak",
        "森林": "forest", "树木": "trees", "花草": "flowers and plants",
        "动物": "animals", "植物": "plants", "自然": "nature",
        
        # Arts & entertainment
        "音乐": "music", "歌曲": "song", "唱歌": "sing", "跳舞": "dance",
        "电影": "movie", "电视": "TV", "节目": "program", "游戏": "game",
        "运动": "sports", "比赛": "competition", "艺术": "art", "文化": "culture",
        "画图": "drawing", "图画": "picture", "绘画": "painting", "美术": "fine arts",
        "文学": "literature", "故事": "story", "小说": "novel", "诗歌": "poetry",
        
        # Emotions & feelings
        "高兴": "happy", "快乐": "joyful", "开心": "happy", "幸福": "happiness",
        "悲伤": "sad", "难过": "sad", "痛苦": "pain", "生气": "angry",
        "愤怒": "anger", "害怕": "afraid", "担心": "worried", "紧张": "nervous",
        "爱": "love", "喜欢": "like", "讨厌": "hate", "想念": "miss",
        
        # Common verbs
        "是": "is/am/are", "有": "have", "在": "at/in", "要": "want",
        "想": "think/want", "可以": "can", "能": "can", "会": "can/know how",
        "应该": "should", "必须": "must", "需要": "need", "让": "let",
        "叫": "call", "来": "come", "去": "go", "回": "return",
        "到": "arrive", "走": "walk", "跑": "run", "站": "stand",
        "坐": "sit", "吃": "eat", "喝": "drink", "睡": "sleep",
        "买": "buy", "卖": "sell", "做": "do", "作": "do/make",
        "工作": "work", "学习": "study", "玩": "play", "看": "look/see",
        "听": "listen", "说": "speak", "读": "read", "写": "write",
        "问": "ask", "答": "answer", "找": "find", "用": "use",
        
        # Question words
        "什么": "what", "为什么": "why", "怎么": "how", "哪里": "where",
        "哪个": "which", "谁": "who", "什么时候": "when", "多少": "how much/many",
        
        # Countries & languages
        "中国": "China", "中文": "Chinese", "汉语": "Chinese language",
        "美国": "America", "英语": "English", "英国": "England",
        "法国": "France", "法语": "French", "德国": "Germany", 
        "德语": "German", "日本": "Japan", "日语": "Japanese",
        "韩国": "Korea", "韩语": "Korean", "俄罗斯": "Russia",
        "俄语": "Russian", "西班牙": "Spain", "西班牙语": "Spanish",
        
        # Your specific words that were missing
        "公路": "highway/public road", "画图": "drawing/draw pictures", 
        "们": "plural marker for pronouns", "海洋": "ocean", "河流": "river",
    }
    
    # First check if it's a common word we know
    if word in common_words:
        return common_words[word]
    
    # For single characters
    if len(word) == 1:
        return char_meanings.get(word, "Single character - meaning unknown")
    
    # For multi-character words, analyze components
    meaning_parts = []
    unknown_chars = []
    
    for char in word:
        if char in char_meanings:
            meaning_parts.append(char_meanings[char])
        else:
            unknown_chars.append(char)
    
    if meaning_parts:
        base_meaning = " + ".join(meaning_parts)
        if unknown_chars:
            return f"Based on characters: {base_meaning} + [unknown: {''.join(unknown_chars)}]"
        else:
            return f"Based on characters: {base_meaning}"
    else:
        return "Word meaning unknown - all characters unrecognized"

def generate_smart_pinyin(word):
    """Generate a plausible pinyin for unknown words"""
    pinyin_map = {
        '爸': 'bà', '爷': 'yé', '奶': 'nǎi', '妈': 'mā', '哥': 'gē', '弟': 'dì',
        '姐': 'jiě', '妹': 'mèi', '兄': 'xiōng', '工': 'gōng', '人': 'rén',
        '医': 'yī', '生': 'shēng', '农': 'nóng', '学': 'xué', '校': 'xiào',
        '上': 'shàng', '下': 'xià', '放': 'fàng', '读': 'dú', '书': 'shū', 
        '写': 'xiě', '字': 'zì', '说': 'shuō', '话': 'huà', '唱': 'chàng', 
        '歌': 'gē', '做': 'zuò', '手': 'shǒu', '作': 'zuò', '业': 'yè', 
        '拍': 'pāi', '球': 'qiú', '花': 'huā', '园': 'yuán', '穿': 'chuān', 
        '衣': 'yī', '服': 'fú', '大': 'dà', '小': 'xiǎo', '桥': 'qiáo', 
        '画': 'huà', '树': 'shù', '晚': 'wǎn', '早': 'zǎo', '天': 'tiān',
        '我': 'wǒ', '你': 'nǐ', '他': 'tā', '她': 'tā', '是': 'shì', '不': 'bù',
        '好': 'hǎo', '很': 'hěn', '的': 'de', '了': 'le', '在': 'zài', '有': 'yǒu',
        '和': 'hé', '这': 'zhè', '那': 'nà', '一': 'yī', '二': 'èr', '三': 'sān',
        '红': 'hóng', '黄': 'huáng', '蓝': 'lán', '绿': 'lǜ', '白': 'bái', '黑': 'hēi',
        '河': 'hé', '流': 'liú', '海': 'hǎi', '洋': 'yáng', '公': 'gōng', '路': 'lù',
        '们': 'men', '图': 'tú', '舅': 'jiù', '姨': 'yí', '伯': 'bó', '叔': 'shū',
        '姑': 'gū', '起': 'qǐ', '立': 'lì', '坐': 'zuò', '举': 'jǔ',
    }
    
    # Common word pinyin for better accuracy
    common_pinyin = {
        "晚上": "wǎn shang", "早上": "zǎo shang", "中午": "zhōng wǔ", "下午": "xià wǔ",
        "谢谢": "xiè xie", "你好": "nǐ hǎo", "再见": "zài jiàn", "对不起": "duì bu qǐ",
        "学校": "xué xiào", "老师": "lǎo shī", "学生": "xué sheng", "朋友": "péng you",
        "河流": "hé liú", "海洋": "hǎi yáng", "公路": "gōng lù", "画图": "huà tú",
        "们": "men", "舅舅": "jiù jiu", "阿姨": "ā yí", "伯伯": "bó bo", 
        "叔叔": "shū shu", "姑姑": "gū gu", "起立": "qǐ lì", "坐下": "zuò xià", 
        "举手": "jǔ shǒu",
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
        if translated_meaning and translated_meaning != "Translation unavailable":
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
    """Display detailed information for a single word"""
    details = get_word_details(word)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📖 {word}")
        st.info(f"**Pinyin:** {details['pinyin']}")
        st.info(f"**Meaning:** {details['meaning']}")
        st.info(f"**Source:** {details['source']}")
    
    with col2:
        st.subheader("🎵 Pronunciation")
        audio_buffer = generate_audio(word)
        if audio_buffer:
            st.audio(audio_buffer, format='audio/mp3')
            st.download_button(
                "📥 Download Audio",
                audio_buffer.getvalue(),
                file_name=f"{word}_pronunciation.mp3",
                mime="audio/mp3",
                key=f"audio_{word}"
            )

# MAIN APP
st.title("🔍 Chinese Dictionary Explorer Done by Sandar")
st.markdown("Type Chinese words OR upload files to get meanings and audio pronunciation")

# MANUAL TEXT INPUT - PROMINENTLY DISPLAYED
st.header("📝 Type Chinese Words Here")
st.markdown("Enter Chinese words or text below (separated by spaces or new lines):")

manual_input = st.text_area(
    "Chinese Text Input:",
    placeholder="Type or paste Chinese words here...\nExamples: 你好 谢谢 我爱你 朋友 学校\nOr: 你好，我是学生。我喜欢学习中文。",
    height=120,
    key="manual_input_main"
)

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    process_manual = st.button("✨ Process Text", type="primary", use_container_width=True)
with col2:
    clear_manual = st.button("🗑️ Clear Text", use_container_width=True)
with col3:
    st.write("")  # Spacing

if process_manual and manual_input:
    with st.spinner("Extracting Chinese words..."):
        manual_words = extract_individual_chinese_words(manual_input)
        st.session_state.manual_words = manual_words
    
    if manual_words:
        st.success(f"✅ Found {len(manual_words)} Chinese words: {', '.join(manual_words)}")

        # Automatically display their meanings using Google Translate
        for word in manual_words:
            st.markdown("---")
            display_word_details(word)
        
        st.session_state.scanned_words = []  # Clear file upload words
    else:
        st.warning("❌ No Chinese words found in the text")

if clear_manual:
    st.session_state.manual_words = []
    st.rerun()

# FILE UPLOAD SECTION
st.header("📎 Or Upload Files")
st.markdown("Upload images or text files to extract Chinese words using OCR")

uploaded_file = st.file_uploader(
    "Choose image or text file",
    type=['png', 'jpg', 'jpeg', 'txt'],
    help="Supported: PNG, JPG, JPEG images or TXT files"
)

if uploaded_file is not None:
    with st.spinner("Processing file..."):
        words, extracted_text = process_uploaded_file(uploaded_file)
        st.session_state.scanned_words = words
        st.session_state.extracted_text = extracted_text
    
    if words:
        st.success(f"✅ Found {len(words)} Chinese words: {', '.join(words)}")
        st.session_state.manual_words = []  # Clear manual input words
    else:
        st.warning("❌ No Chinese words found")
        
    if st.session_state.extracted_text:
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
        st.subheader(f"Quick Result: {single_word}")
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
    sample_words = ["你好", "谢谢", "我爱你", "朋友", "学校", "妈妈", "老师", "学生"]
    
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
    st.write("• Get pinyin & meanings")
    st.write("• Audio pronunciation")
    st.write("• Download audio files")
    
    st.markdown("### 🔍 New Words Added")
    st.write("• 舅舅, 阿姨, 伯伯, 叔叔, 姑姑")
    st.write("• 起立, 坐下, 举手")
    st.write("• And many more family terms!")
