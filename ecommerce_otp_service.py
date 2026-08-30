"""Runnable phone-login checkout example: uvicorn ecommerce_otp_service:app."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrai_phone import InfraiError, InfraiPhoneClient


class OrderStatus(str, Enum):
    PAID = "paid"
    FULFILLING = "fulfilling"
    SHIPPED = "shipped"


class SendCodeRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    captcha_token: str = Field(min_length=8)
    request_id: str = Field(min_length=8)
    locale: str = "en-US"


class VerifyCodeRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    code: str = Field(min_length=4, max_length=10)
    request_id: str = Field(min_length=8)


class CheckoutRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    sku: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=20)
    amount: float = Field(gt=0)


class FulfillmentRequest(BaseModel):
    tracking_number: str = Field(min_length=3)


class OrderView(BaseModel):
    order_id: str
    phone: str
    sku: str
    quantity: int
    amount: float
    status: OrderStatus
    receipt: str
    updates: list[str]


@dataclass
class CommerceLedger:
    verified_phones: set[str] = field(default_factory=set)
    orders: dict[str, OrderView] = field(default_factory=dict)

    def mark_verified(self, phone: str) -> None:
        self.verified_phones.add(phone)

    def checkout(self, request: CheckoutRequest) -> OrderView:
        if request.phone not in self.verified_phones:
            raise PermissionError("phone verification is required before checkout")
        order_id = f"ord_{uuid4().hex[:12]}"
        receipt = f"Receipt {order_id}: {request.quantity} x {request.sku}"
        order = OrderView(
            order_id=order_id,
            phone=request.phone,
            sku=request.sku,
            quantity=request.quantity,
            amount=request.amount,
            status=OrderStatus.PAID,
            receipt=receipt,
            updates=["Payment accepted; receipt issued"],
        )
        self.orders[order_id] = order
        return order

    def fulfill(self, order_id: str, tracking_number: str) -> OrderView:
        order = self.orders[order_id]
        order.status = OrderStatus.SHIPPED
        order.updates.extend(
            ["Order entered fulfillment", f"Order shipped: {tracking_number}"]
        )
        return order


app = FastAPI(title="Phone OTP Commerce Migration")
ledger = CommerceLedger()


def phone_client() -> InfraiPhoneClient:
    return InfraiPhoneClient(os.environ.get("INFRAI_API_KEY"))


def public_error(error: InfraiError) -> HTTPException:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return HTTPException(status_code=status, detail={"code": error.code, "message": str(error)})


@app.post("/login/code", status_code=202)
def send_login_code(
    request: SendCodeRequest, client: InfraiPhoneClient = Depends(phone_client)
) -> dict[str, Any]:
    try:
        client.verify_captcha(
            request.captcha_token,
            f"{request.request_id}-captcha",
            widget_record_id=request.request_id,
        )
        result = client.send_code(request.phone, request.request_id, locale=request.locale)
        return {"accepted": True, "provider": result}
    except InfraiError as error:
        raise public_error(error) from error
    finally:
        client.close()


@app.post("/login/verify")
def verify_login_code(
    request: VerifyCodeRequest, client: InfraiPhoneClient = Depends(phone_client)
) -> dict[str, Any]:
    try:
        session = client.verify_code(request.phone, request.code, request.request_id)
        ledger.mark_verified(request.phone)
        return {"verified": True, "session": session}
    except InfraiError as error:
        raise public_error(error) from error
    finally:
        client.close()


@app.post("/orders", response_model=OrderView, status_code=201)
def create_order(request: CheckoutRequest) -> OrderView:
    try:
        return ledger.checkout(request)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


@app.post("/orders/{order_id}/fulfill", response_model=OrderView)
def fulfill_order(order_id: str, request: FulfillmentRequest) -> OrderView:
    try:
        return ledger.fulfill(order_id, request.tracking_number)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="order not found") from error


@app.get("/orders/{order_id}", response_model=OrderView)
def customer_order_update(order_id: str) -> OrderView:
    try:
        return ledger.orders[order_id]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="order not found") from error
