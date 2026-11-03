import re
import unicodedata
from typing import Dict, List


DOMAIN_RULES: Dict[str, Dict[str, object]] = {
    "marketplace.etsy": {
        "title": "Etsy marketplace",
        "guidance": [
            "Etsy buyers often value niche positioning, giftability, personalization, premium feel, and trustworthy customer experience.",
            "For Etsy US, US fulfillment is usually preferred when speed/customer experience matters.",
            "Bella + Canvas is a good premium-feel tee candidate; Gildan 5000 is a good budget/margin candidate.",
            "If the seller did not explicitly ask for kids, baby, youth, or family apparel, prioritize adult/unisex core products before kids/baby products.",
        ],
    },
    "marketplace.amazon": {
        "title": "Amazon marketplace",
        "guidance": [
            "Amazon buyers usually prioritize delivery speed, reliability, and competitive pricing.",
            "For US customers, prefer US fulfillment when possible.",
        ],
    },
    "marketplace.tiktok": {
        "title": "TikTok Shop marketplace",
        "guidance": [
            "TikTok Shop is trend-driven and price-sensitive.",
            "Prioritize products with low cost, fast testing, and simple clear positioning.",
        ],
    },
    "marketplace.shopify": {
        "title": "Shopify marketplace",
        "guidance": [
            "Shopify is better for brand building and controlled customer experience.",
            "Premium materials can make sense if the brand positioning supports a higher selling price.",
        ],
    },
    "finance.margin": {
        "title": "Margin target",
        "guidance": [
            "Gross margin should use fulfillment cost: base cost + shipping cost + known fees.",
            "For a target margin above 40%, budget-friendly blanks and US fulfillment for US customers are often good starting points.",
            "Do not claim exact margin unless price/cost data is available; frame it as an estimate or ask for selling price if needed.",
        ],
    },
    "goal.premium": {
        "title": "Premium positioning",
        "guidance": [
            "Premium usually means softer material, better fit, better perceived value, and often higher base cost.",
            "Premium is useful for Etsy/Shopify positioning but can reduce margin unless selling price is higher.",
        ],
    },
    "goal.budget": {
        "title": "Budget positioning",
        "guidance": [
            "Budget-friendly products are useful for testing niches, protecting margin, and price-sensitive channels.",
            "Trade-off: lower premium feel and weaker differentiation versus premium blanks.",
        ],
    },
    "product.tshirt": {
        "title": "T-shirt strategy",
        "guidance": [
            "T-shirts are a strong starting point for POD sellers because cost is lower, demand is broad, and niche testing is easy.",
            "Gildan 5000 is a budget-friendly tee candidate; Bella + Canvas 3001 is a premium-feel tee candidate.",
        ],
    },
    "product.hoodie": {
        "title": "Hoodie strategy",
        "guidance": [
            "Hoodies can support higher AOV and premium positioning, especially in Q4/cold seasons.",
            "Trade-off: base cost and shipping cost are usually higher than T-shirts.",
        ],
    },
    "conflict.premium_low_cost": {
        "title": "Premium + lowest cost conflict",
        "guidance": [
            "Premium feel and lowest cost are partially conflicting goals.",
            "Explain the trade-off, then suggest balanced alternatives: premium-balanced, budget-safe, or fast-shipping option.",
        ],
    },
    "shipping.us": {
        "title": "US fulfillment",
        "guidance": [
            "For customers in the US, US fulfillment usually improves shipping speed and customer experience.",
            "Still compare cost and catalog availability before making a final recommendation.",
            "For broad Etsy US apparel recommendations, start from adult/unisex US blanks unless the user explicitly asks for kids/baby/youth.",
        ],
    },
    "season.q4": {
        "title": "Q4 risk",
        "guidance": [
            "Q4 can increase fulfillment delay risk because providers may be overloaded.",
            "For Q4/gift orders, prioritize reliable fulfillment, shorter processing time, and shipping buffer.",
        ],
    },
    "compatibility.sublimation": {
        "title": "Sublimation compatibility",
        "guidance": [
            "Do not suggest Sublimation for non-Polyester products.",
        ],
    },
    "time.processing_vs_shipping": {
        "title": "Processing vs Shipping time",
        "guidance": [
            "Processing Time ≠ Shipping Time. Total estimated delivery = Processing Time + Shipping Time.",
        ],
    },
}


TOPIC_PATTERNS = {
    "marketplace.etsy": [r"\betsy\b"],
    "marketplace.amazon": [r"\bamazon\b"],
    "marketplace.tiktok": [r"\btiktok\b", r"tik tok"],
    "marketplace.shopify": [r"\bshopify\b"],
    "finance.margin": [r"\bmargin\b", r"loi nhuan", r"bien loi nhuan", r"40%"],
    "goal.premium": [r"\bpremium\b", r"cao cap", r"chat luong cao", r"mem"],
    "goal.budget": [r"\bbudget\b", r"gia re", r"re nhat", r"cost thap", r"tiet kiem"],
    "product.tshirt": [r"t-?shirt", r"ao thun", r"\btee\b"],
    "product.hoodie": [r"\bhoodie\b", r"ao hoodie", r"ao ni"],
    "shipping.us": [r"\bus\b", r"united states", r"\bmy\b", r"\busa\b"],
    "season.q4": [r"\bq4\b", r"mua le", r"christmas", r"holiday", r"qua tang"],
    "compatibility.sublimation": [r"\bsublimation\b", r"\bsublimate\b"],
    "time.processing_vs_shipping": [r"processing time", r"shipping time", r"thoi gian san xuat", r"thoi gian ship", r"bao lau", r"may ngay"],
}


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    decomposed = unicodedata.normalize("NFD", normalized)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d")


def detect_domain_topics(message: str) -> List[str]:
    text = _normalize(message)
    topics: List[str] = []
    for topic, patterns in TOPIC_PATTERNS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            topics.append(topic)

    if "goal.premium" in topics and "goal.budget" in topics:
        topics.append("conflict.premium_low_cost")

    return topics


def build_domain_context(message: str, max_topics: int = 5) -> str:
    topics = detect_domain_topics(message)[:max_topics]
    if not topics:
        return ""

    lines = [
        "DOMAIN KNOWLEDGE CONTEXT:",
        "Use this as consultant guidance only. Do not dump it to the user; turn it into concise reasoning/trade-offs.",
    ]
    for topic in topics:
        rule = DOMAIN_RULES.get(topic)
        if not rule:
            continue
        lines.append(f"- {rule['title']}:")
        for item in rule["guidance"]:
            lines.append(f"  - {item}")
    return "\n".join(lines)
