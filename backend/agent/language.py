import re
import unicodedata


VIETNAMESE_MARKS = re.compile(r'[ăđơưĂĐƠƯ\u1ea0-\u1ef9]')
VIETNAMESE_WORDS = re.compile(
    r'\b(?:có|áo|nào|không|tìm|giá|tiền|màu|bán|này|xin|chào|cảm|mình|bạn|cho|làm)\b'
)
VIETNAMESE_PLAIN = re.compile(
    r'\b(?:toi muon|minh muon|cho minh|cho toi|cho nguoi moi|ao thun|ao ni|mau trang|'
    r'gia re|tiet kiem|bao nhieu|co the|san pham|don hang|xin chao|cam on|khong)\b|\bco\b.{0,55}\bnao\b'
)
ENGLISH_MARKERS = re.compile(
    r'\b(?:the|this|these|that|those|you|your|we|our|would|could|should|is|are|can|'
    r'hi|hello|thanks|find|show|any|recommend|recommendation|trade-off|reasoning|found|budget-friendly|beginner)\b'
)
ENGLISH_LABELS = re.compile(
    r'^\s*(?:[#>*\-]+\s*)*(?:recommendation|reasoning|trade-off|best value|why it works|'
    r'budget strategy|base cost|pros|cons)(?=$|[ :*—\-])', re.IGNORECASE | re.MULTILINE,
)
UNTRANSLATED_VI_TERMS = re.compile(
    r'\b(?:budget[ -]friendly|beginner|recommendation|reasoning|trade[ -]off|base cost|'
    r'best value|size range|adult sizing|shipping cost|premium feel|gross margin|blank product|print.on.demand)\b',
    re.IGNORECASE,
)


def has_vietnamese(text: str) -> bool:
    text = unicodedata.normalize('NFC', text).casefold()
    if VIETNAMESE_MARKS.search(text) or VIETNAMESE_PLAIN.search(text):
        return True
    words = VIETNAMESE_WORDS.findall(text)
    return any(word != 'cho' for word in words)


def reply_language(message: str, previous=()) -> str:
    for text in (message, *reversed(previous)):
        text = text.strip().casefold()
        if has_vietnamese(text):
            return 'vi'
        if text in {'ok', 'okay', 'yes', 'no', 'm', 's', 'l', 'xl', '2xl', '3xl'}:
            continue
        words = re.findall(r'\b[a-z]+\b', text)
        if ENGLISH_MARKERS.search(text) or (len(words) >= 3 and not re.fullmatch(r'[\w-]+', text)):
            return 'en'
    return 'vi'


def language_instruction(language: str) -> str:
    if language == 'vi':
        return ('Ngôn ngữ trả lời bắt buộc: viết toàn bộ bằng tiếng Việt, gồm tiêu đề, lý do và câu hỏi. '
                'Dịch các từ như budget-friendly, beginner, Recommendation, Reasoning và Trade-off. '
                'Dùng biên lợi nhuận gộp, sản phẩm phôi, giá gốc và in theo yêu cầu cho các thuật ngữ tương ứng. '
                'Chỉ giữ tên sản phẩm, thương hiệu và mã SKU ở dạng gốc. Write the entire reply in Vietnamese.')
    return 'Required reply language: write entirely in English, including headings and follow-up questions.'


def matches_reply_language(text: str, language: str) -> bool:
    if not text.strip():
        return False
    # Codes and exact catalog names in code formatting are language neutral.
    prose = re.sub(r'`[^`]*`|https?://\S+', '', text)
    if language == 'en':
        return not has_vietnamese(prose)
    if ENGLISH_LABELS.search(prose) or UNTRANSLATED_VI_TERMS.search(prose) or not has_vietnamese(prose):
        return False
    sentences = re.split(r'(?<=[.!?])\s+|\n+', prose.casefold())
    return not any(not has_vietnamese(line) and len(ENGLISH_MARKERS.findall(line)) >= 2 for line in sentences)
