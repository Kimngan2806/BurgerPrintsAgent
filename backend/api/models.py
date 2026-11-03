from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Product(BaseModel):
    id: str
    name: str
    category: str
    description: Optional[str] = ""
    material: Optional[str] = ""
    style: Optional[str] = ""
    print_techniques: List[str] = []
    display_name: Optional[str] = ""
    catalog_id: Optional[str] = ""
    html_desc: Optional[str] = ""
    url: Optional[str] = ""
    design_type: Optional[str] = ""
    design_url: Optional[str] = None
    available_sizes: List[Dict[str, Any]] = []
    available_colors: List[Dict[str, Any]] = []
    raw_json: Dict[str, Any] = {}

class SKU(BaseModel):
    sku_code: str
    product_id: str
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    provider_id: str = ""
    size_id: Optional[str] = None
    color_id: Optional[str] = None
    color_hex: Optional[str] = None
    price: Optional[str] = None
    second_price: Optional[str] = None
    addition_price: Optional[str] = None
    provider_name: Optional[str] = None
    raw_json: Dict[str, Any] = {}

class Provider(BaseModel):
    id: str
    name: str
    location: Optional[str] = None
    countries_served: List[str] = []

class OrderAddress(BaseModel):
    name: str
    street: str
    city: str
    state: str
    zip: str
    country: str

class OrderRequest(BaseModel):
    sku: str
    quantity: int = Field(default=1, gt=0)
    address: OrderAddress
    shipping_method: str = "standard"
    design_url_front: str
    mockup_url_front: Optional[str] = None

class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    reference_order_id: Optional[str] = None
    sku: Optional[str] = None
    quantity: Optional[int] = None
    destination: Optional[Dict[str, Any]] = None
    design: Optional[Dict[str, Any]] = None
    shipping_services: List[Dict[str, Any]] = []
    order_details: Dict[str, Any] = {}
    api_response: Dict[str, Any] = {}
    normalized_error: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    message: str
    session_id: str

class ChatResponse(BaseModel):
    response: str
    session_id: str
