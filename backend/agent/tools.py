from google.generativeai.types import FunctionDeclaration, Tool
import json

# =======================================================
# 1. search_products
# =======================================================
search_products_func = FunctionDeclaration(
    name="search_products",
    description="Tìm kiếm sản phẩm trong catalog dựa trên text query, danh mục, hoặc chất liệu. Tool này KHÔNG THỂ filter theo giá (price) hoặc thời gian ship. Nếu user yêu cầu tìm theo giá/ship, bạn vẫn chỉ có thể truyền query text (VD: 't-shirt') rồi SAU ĐÓ TỰ GỌI THÊM get_base_cost hoặc get_shipping_time để kiểm tra từng SKU.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "CÃ¢u query tÃ¬m kiáº¿m tá»± do (vÃ­ dá»¥: 'Ã¡o thun cotton mÃ¹a hÃ¨', 'premium mug')"
            },
            "category": {
                "type": "string",
                "description": "Danh má»¥c sáº£n pháº©m (vÃ­ dá»¥: 't-shirt', 'polo', 'hoodie', 'mug', 'poster', 'tote')"
            },
            "material": {
                "type": "string",
                "description": "Cháº¥t liá»‡u (vÃ­ dá»¥: 'cotton', 'polyester', 'ceramic')"
            }
        }
    }
)

# =======================================================
# 2. get_sku_info
# =======================================================
get_sku_info_func = FunctionDeclaration(
    name="get_sku_info",
    description="Láº¥y danh sÃ¡ch cÃ¡c SKUs (bao gá»“m mÃ u sáº¯c, kÃ­ch thÆ°á»›c, xÆ°á»Ÿng, mÃ£ sku_code) cá»§a má»™t product_id cá»¥ thá»ƒ.",
    parameters={
        "type": "object",
        "properties": {
            "sku_code": {
                "type": "string",
                "description": "Ma SKU cu the user dua, vi du USBG5000DTF-Black-S. Uu tien dung field nay khi user muon xem hoac dat mot SKU."
            },
            "product_id": {
                "type": "string",
                "description": "ID cá»§a sáº£n pháº©m (vÃ­ dá»¥: P1, P2)"
            }
        },
    }
)

# =======================================================
# 3. get_base_cost
# =======================================================
get_base_cost_func = FunctionDeclaration(
    name="get_base_cost",
    description="[REALTIME] Láº¥y giÃ¡ sáº£n xuáº¥t (base cost) cáº­p nháº­t nháº¥t cá»§a má»™t hoáº·c nhiá»u SKU codes. LuÃ´n gá»i hÃ m nÃ y Ä‘á»ƒ bÃ¡o giÃ¡ chÃ­nh xÃ¡c, khÃ´ng Ä‘Æ°á»£c Ä‘oÃ¡n.",
    parameters={
        "type": "object",
        "properties": {
            "sku_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch cÃ¡c mÃ£ SKU cáº§n láº¥y giÃ¡."
            }
        },
        "required": ["sku_codes"]
    }
)

# =======================================================
# 4. get_shipping_cost
# =======================================================
get_shipping_cost_func = FunctionDeclaration(
    name="get_shipping_cost",
    description="[REALTIME] Láº¥y phÃ­ váº­n chuyá»ƒn cáº­p nháº­t nháº¥t cá»§a SKU Ä‘áº¿n má»™t quá»‘c gia cá»¥ thá»ƒ.",
    parameters={
        "type": "object",
        "properties": {
            "sku_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch mÃ£ SKU."
            },
            "destination": {
                "type": "string",
                "description": "Quá»‘c gia Ä‘Ã­ch Ä‘áº¿n (vÃ­ dá»¥: US, EU, AU, CA, VN)."
            }
        },
        "required": ["sku_codes", "destination"]
    }
)

# =======================================================
# 5. get_production_time
# =======================================================
get_production_time_func = FunctionDeclaration(
    name="get_production_time",
    description="[REALTIME] Láº¥y thá»i gian sáº£n xuáº¥t Æ°á»›c tÃ­nh hiá»‡n táº¡i cá»§a SKU.",
    parameters={
        "type": "object",
        "properties": {
            "sku_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch mÃ£ SKU."
            }
        },
        "required": ["sku_codes"]
    }
)

# =======================================================
# 6. get_shipping_time
# =======================================================
get_shipping_time_func = FunctionDeclaration(
    name="get_shipping_time",
    description="[REALTIME] Láº¥y thá»i gian váº­n chuyá»ƒn Æ°á»›c tÃ­nh cá»§a SKU Ä‘áº¿n quá»‘c gia Ä‘Ã­ch.",
    parameters={
        "type": "object",
        "properties": {
            "sku_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch mÃ£ SKU."
            },
            "destination": {
                "type": "string",
                "description": "Quá»‘c gia Ä‘Ã­ch Ä‘áº¿n."
            }
        },
        "required": ["sku_codes", "destination"]
    }
)

# =======================================================
# 7. check_sku_availability
# =======================================================
check_sku_availability_func = FunctionDeclaration(
    name="check_sku_availability",
    description="[REALTIME] Kiá»ƒm tra tráº¡ng thÃ¡i tá»“n kho vÃ  hoáº¡t Ä‘á»™ng cá»§a SKU (active, inactive, discontinued). KhÃ´ng Ä‘Æ°á»£c recommend SKU inactive.",
    parameters={
        "type": "object",
        "properties": {
            "sku_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch mÃ£ SKU cáº§n check."
            }
        },
        "required": ["sku_codes"]
    }
)

# =======================================================
# 8. check_provider_status
# =======================================================
check_provider_status_func = FunctionDeclaration(
    name="check_provider_status",
    description="[REALTIME] Kiá»ƒm tra tráº¡ng thÃ¡i cá»§a xÆ°á»Ÿng (active, overload, maintenance). KhÃ´ng Ä‘Æ°á»£c recommend xÆ°á»Ÿng overload/maintenance.",
    parameters={
        "type": "object",
        "properties": {
            "provider_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch ID xÆ°á»Ÿng cáº§n check."
            }
        },
        "required": ["provider_ids"]
    }
)

# =======================================================
# 9. check_region_support
# =======================================================
check_region_support_func = FunctionDeclaration(
    name="check_region_support",
    description="[REALTIME] Kiá»ƒm tra xem SKU cÃ³ há»— trá»£ váº­n chuyá»ƒn Ä‘áº¿n quá»‘c gia Ä‘Ã­ch hay khÃ´ng (True/False).",
    parameters={
        "type": "object",
        "properties": {
            "sku_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Danh sÃ¡ch mÃ£ SKU."
            },
            "region": {
                "type": "string",
                "description": "Khu vá»±c/Quá»‘c gia Ä‘Ã­ch Ä‘áº¿n (US, EU, AU...)."
            }
        },
        "required": ["sku_codes", "region"]
    }
)

# =======================================================
# 10. prepare_order_review
# =======================================================
prepare_order_review_func = FunctionDeclaration(
    name="prepare_order_review",
    description="Bat buoc goi truoc khi yeu cau user xac nhan dat hang. Tool nay tao ban tom tat SKU, quantity, destination, gia, design; validate design_url_front; va tra order_review_token de create_order duoc phep chay.",
    parameters={
        "type": "object",
        "properties": {
            "sku": {"type": "string", "description": "Ma SKU can dat"},
            "quantity": {"type": "integer", "description": "So luong"},
            "address": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "zip": {"type": "string"},
                    "country": {"type": "string"}
                },
                "required": ["name", "street", "city", "state", "zip", "country"]
            },
            "design_url_front": {"type": "string", "description": "Public image URL dung de validate truoc khi order"},
            "mockup_url_front": {"type": "string", "description": "Mockup URL neu co"}
        },
        "required": ["sku", "quantity", "address", "design_url_front"]
    }
)

# =======================================================
# 11. create_order
# =======================================================
create_order_func = FunctionDeclaration(
    name="create_order",
    description="Táº¡o Ä‘Æ¡n hÃ ng fulfillment má»›i. Báº®T BUá»˜C: KhÃ´ng bao giá» thu tháº­p Ä‘á»‹a chá»‰ ngÆ°á»i nháº­n náº¿u chÆ°a gá»i tool check_sku_availability Ä‘á»ƒ Ä‘áº£m báº£o SKU tá»“n táº¡i. CHá»ˆ Gá»ŒI khi ngÆ°á»i dÃ¹ng gÃµ cÃ¢u lá»‡nh cÃ³ chá»©a chá»¯ 'xÃ¡c nháº­n'. Báº®T BUá»˜C pháº£i cÃ³ design_url_front lÃ  link áº£nh public http/https má»Ÿ Ä‘Æ°á»£c trÃªn internet, vÃ­ dá»¥ https://domain.com/design.png hoáº·c .jpg. KhÃ´ng dÃ¹ng file local, localhost, private Google Drive link, hoáº·c placeholder. Tuyá»‡t Ä‘á»‘i khÃ´ng tá»± chá»n ngáº«u nhiÃªn.",
    parameters={
        "type": "object",
        "properties": {
            "sku": {"type": "string", "description": "MÃ£ SKU Ä‘á»ƒ order"},
            "quantity": {"type": "integer", "description": "Sá»‘ lÆ°á»£ng (máº·c Ä‘á»‹nh 1)"},
            "address": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "zip": {"type": "string"},
                    "country": {"type": "string"}
                },
                "required": ["name", "street", "city", "state", "zip", "country"]
            },
            "design_url_front": {
                "type": "string",
                "description": "Bat buoc. Public http/https URL cua file design mat truoc, vi du https://domain.com/design-front.png hoac .jpg. Link phai mo duoc cong khai tren internet; khong dung file local, localhost, private link, hoac placeholder."
            },
            "mockup_url_front": {
                "type": "string",
                "description": "Public http/https URL cua mockup mat truoc neu co. Neu khong co se dung design_url_front."
            },
            "order_review_token": {
                "type": "string",
                "description": "Token tra ve tu prepare_order_review. Bat buoc de chung minh da hien summary cho user truoc khi xac nhan."
            },
            "shipping_method": {"type": "string", "description": "VÃ­ dá»¥: 'standard', 'express'"}
        },
        "required": ["sku", "quantity", "address", "design_url_front", "order_review_token"]
    }
)

get_order_creation_status_func = FunctionDeclaration(
    name="get_order_creation_status",
    description="Kiá»ƒm tra tráº¡ng thÃ¡i báº­t/táº¯t hiá»‡n táº¡i cá»§a tÃ­nh nÄƒng táº¡o Ä‘Æ¡n tá»« Harness. Pháº£i gá»i tool nÃ y thay vÃ¬ tá»± suy Ä‘oÃ¡n tráº¡ng thÃ¡i.",
    parameters={"type": "object", "properties": {}}
)

# Group all tools into a single Tool object
agent_tools = Tool(
    function_declarations=[
        search_products_func,
        get_sku_info_func,
        get_base_cost_func,
        get_shipping_cost_func,
        get_production_time_func,
        get_shipping_time_func,
        check_sku_availability_func,
        check_provider_status_func,
        check_region_support_func,
        get_order_creation_status_func,
        prepare_order_review_func,
        create_order_func
    ]
)
