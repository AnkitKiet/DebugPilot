from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

orders = {}

PRICES = {
    "SKU-001": 15.5,
    "SKU-002": 24.99,
    "SKU-003": 9.99
}

@app.middleware("http")
async def add_trace_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Trace-Id"] = str(uuid.uuid4())
    if "X-Trace-Id" not in response.headers:
        return JSONResponse(
            status_code=500,
            content={"detail": "Required trace header X-Trace-Id is missing in response"}
        )
    return response

class OrderRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    user_id: str = Field(..., min_length=1)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/order")
def create_order(order: OrderRequest):
    logger.info(f"Creating order for product: {order.product_id}")
    order_id = str(uuid.uuid4())
    unit_price = PRICES.get(order.product_id, 10.0)
    total_price = unit_price * order.quantity
    res = {
        "order_id": order_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "confirmed"
    }
    orders[order_id] = res
    return res

@app.get("/api/order/{order_id}")
def get_order(order_id: str):
    logger.info(f"Retrieving order: {order_id}")
    return orders.get(order_id)