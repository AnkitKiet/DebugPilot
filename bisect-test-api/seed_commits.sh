#!/bin/bash

# Exit on error
set -e

if [ -d ".git" ]; then
    echo "Git repository already initialized. Skipping seeding."
    GOOD_HASH=$(git log --reverse --format="%H" | sed -n '4p')
    BAD_HASH=$(git log --reverse --format="%H" | sed -n '8p')
    echo "GOOD_COMMIT=$GOOD_HASH"
    echo "BAD_COMMIT=$BAD_HASH"
    exit 0
fi

# 1. git init
git init

# 2. git config
git config user.email "harness@test.com"
git config user.name "Test Harness"

commit_file() {
    local msg="$1"
    git add main.py
    if [ -f "README.md" ]; then
        git add README.md
    fi
    git commit -m "$msg"
}

# Commit 1
cat << 'EOF' > main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid

app = FastAPI()

orders = {}

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

@app.post("/api/order")
def create_order(order: dict):
    order_id = "order-123"
    unit_price = 10.0
    total_price = unit_price * order.get("quantity", 1)
    res = {
        "order_id": order_id,
        "product_id": order.get("product_id", ""),
        "quantity": order.get("quantity", 1),
        "unit_price": unit_price,
        "total_price": total_price,
        "status": "confirmed"
    }
    orders[order_id] = res
    return res

@app.get("/api/order/{order_id}")
def get_order(order_id: str):
    return orders.get(order_id)
EOF
commit_file "initial project setup"

# Commit 2
cat << 'EOF' > main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uuid

app = FastAPI()

orders = {}

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

@app.post("/api/order")
def create_order(order: OrderRequest):
    order_id = "order-123"
    unit_price = 10.0
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
    return orders.get(order_id)
EOF
commit_file "add input validation"

# Commit 3
cat << 'EOF' > main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uuid

app = FastAPI()

orders = {}

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

@app.post("/api/order")
def create_order(order: OrderRequest):
    order_id = str(uuid.uuid4())
    unit_price = 10.0
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
    return orders.get(order_id)
EOF
commit_file "add order id generation"

# Commit 4
cat << 'EOF' > main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uuid

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

@app.post("/api/order")
def create_order(order: OrderRequest):
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
    return orders.get(order_id)
EOF
commit_file "add unit price calculation"

# Commit 5
cat << 'EOF' > main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uuid

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
    # response.headers["X-Trace-Id"] = str(uuid.uuid4())  # BUG: accidentally removed trace ID header during middleware refactoring
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

@app.post("/api/order")
def create_order(order: OrderRequest):
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
    return orders.get(order_id)
EOF
commit_file "refactor response model — BUG COMMIT"

# Commit 6
cat << 'EOF' > main.py
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
    # response.headers["X-Trace-Id"] = str(uuid.uuid4())  # BUG: accidentally removed trace ID header during middleware refactoring
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
EOF
commit_file "add logging"

# Commit 7
cat << 'EOF' > main.py
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
    # response.headers["X-Trace-Id"] = str(uuid.uuid4())  # BUG: accidentally removed trace ID header during middleware refactoring
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
EOF
commit_file "add /health endpoint"

# Commit 8
echo "# Bisect Test API" > README.md
git add README.md
git commit -m "update readme"

GOOD_HASH=$(git log --reverse --format="%H" | sed -n '4p')
BAD_HASH=$(git log --reverse --format="%H" | sed -n '8p')

echo ""
echo "Seeding completed successfully!"
git log --oneline
echo ""
echo "GOOD_COMMIT=$GOOD_HASH"
echo "BAD_COMMIT=$BAD_HASH"
