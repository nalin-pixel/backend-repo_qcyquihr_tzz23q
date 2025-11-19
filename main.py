import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from bson import ObjectId
import hashlib

from database import db, create_document, get_documents
from schemas import Product, Order, OrderItem, AuthUser

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()

@app.get("/")
def read_root():
    return {"message": "E-commerce API ready"}

# Utility to convert Mongo documents to JSON-friendly dicts

def serialize_doc(doc):
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

# Catalog endpoints

@app.get("/api/products")
def list_products(category: Optional[str] = None, q: Optional[str] = None, limit: int = 50):
    filter_dict = {}
    if category:
        filter_dict["category"] = category
    if q:
        filter_dict["title"] = {"$regex": q, "$options": "i"}
    docs = get_documents("product", filter_dict, limit)
    return [serialize_doc(d) for d in docs]

class ProductCreate(Product):
    pass

@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    try:
        doc = db["product"].find_one({"_id": ObjectId(product_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Product not found")
        return serialize_doc(doc)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")

@app.post("/api/products", status_code=201)
def create_product(product: ProductCreate):
    inserted_id = create_document("product", product)
    return {"id": inserted_id}

@app.post("/api/products/seed")
def seed_products():
    """Seed database with a small catalog for demo purposes"""
    demo = [
        {"title":"Wireless Headphones","description":"Noise-cancelling over-ear with 30h battery","price":129.99,"category":"Electronics","image":"https://images.unsplash.com/photo-1518440563236-3d487397c3e5?q=80&w=1200&auto=format&fit=crop","images":["https://images.unsplash.com/photo-1518440563236-3d487397c3e5?q=80&w=1200&auto=format&fit=crop","https://images.unsplash.com/photo-1517841905240-472988babdf9?q=80&w=1200&auto=format&fit=crop"]},
        {"title":"Smart Watch","description":"Fitness tracking, messages, and more","price":199.00,"category":"Electronics","image":"https://images.unsplash.com/photo-1519400197429-404ae1a05fa1?q=80&w=1200&auto=format&fit=crop","images":["https://images.unsplash.com/photo-1519400197429-404ae1a05fa1?q=80&w=1200&auto=format&fit=crop","https://images.unsplash.com/photo-1517433456452-f9633a875f6f?q=80&w=1200&auto=format&fit=crop"]},
        {"title":"Espresso Maker","description":"Barista-quality coffee at home","price":249.50,"category":"Home","image":"https://images.unsplash.com/photo-1503481766315-7a586b20f66b?q=80&w=1200&auto=format&fit=crop","images":["https://images.unsplash.com/photo-1503481766315-7a586b20f66b?q=80&w=1200&auto=format&fit=crop","https://images.unsplash.com/photo-1494314671902-399b18174975?q=80&w=1200&auto=format&fit=crop"]},
        {"title":"Running Shoes","description":"Lightweight and comfortable for daily runs","price":89.99,"category":"Fashion","image":"https://images.unsplash.com/photo-1542291026-7eec264c27ff?q=80&w=1200&auto=format&fit=crop","images":["https://images.unsplash.com/photo-1542291026-7eec264c27ff?q=80&w=1200&auto=format&fit=crop","https://images.unsplash.com/photo-1542291025-3f3f021d1a3a?q=80&w=1200&auto=format&fit=crop"]},
        {"title":"Backpack","description":"Durable everyday carry with 20L capacity","price":59.00,"category":"Accessories","image":"https://images.unsplash.com/photo-1514477917009-389c76a86b68?q=80&w=1200&auto=format&fit=crop","images":["https://images.unsplash.com/photo-1514477917009-389c76a86b68?q=80&w=1200&auto=format&fit=crop","https://images.unsplash.com/photo-1520975916090-3105956dac38?q=80&w=1200&auto=format&fit=crop"]},
        {"title":"LED Desk Lamp","description":"Adjustable brightness, warm/cool modes","price":34.95,"category":"Home","image":"https://images.unsplash.com/photo-1511255183209-e6f31b0289ea?q=80&w=1200&auto=format&fit=crop","images":["https://images.unsplash.com/photo-1511255183209-e6f31b0289ea?q=80&w=1200&auto=format&fit=crop","https://images.unsplash.com/photo-1509395176047-4a66953fd231?q=80&w=1200&auto=format&fit=crop"]}
    ]
    inserted = 0
    for d in demo:
        create_document("product", d)
        inserted += 1
    return {"inserted": inserted}

# Orders

class CreateOrder(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_address: str
    items: List[OrderItem]

@app.post("/api/orders", status_code=201)
def place_order(payload: CreateOrder):
    # Compute totals
    subtotal = sum(item.price * item.quantity for item in payload.items)
    tax = round(subtotal * 0.07, 2)
    total = round(subtotal + tax, 2)
    order = Order(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_address=payload.customer_address,
        items=payload.items,
        subtotal=subtotal,
        tax=tax,
        total=total,
    )
    inserted_id = create_document("order", order)
    return {"id": inserted_id, "subtotal": subtotal, "tax": tax, "total": total}

# Payments (mock)
class PaymentPayload(BaseModel):
    amount: float
    currency: str = "usd"
    card_last4: str

@app.post("/api/payments/charge")
def charge_payment(payload: PaymentPayload):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if len(payload.card_last4) != 4 or not payload.card_last4.isdigit():
        raise HTTPException(status_code=400, detail="Invalid card")
    # Mock charge id
    return {"status": "succeeded", "charge_id": "ch_mock_" + payload.card_last4}

# Basic auth (demo only)
class RegisterPayload(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

@app.post("/api/auth/register")
def register_user(payload: RegisterPayload):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    existing = db["authuser"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = AuthUser(email=payload.email, name=payload.name, password_hash=hash_password(payload.password))
    user_id = create_document("authuser", user)
    return {"id": user_id, "email": payload.email, "name": payload.name}

@app.post("/api/auth/login")
def login_user(credentials: HTTPBasicCredentials = Depends(security)):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    user = db["authuser"].find_one({"email": credentials.username})
    if not user or user.get("password_hash") != hash_password(credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"email": user["email"], "name": user.get("name")}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
