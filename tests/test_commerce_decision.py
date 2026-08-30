from fastapi.testclient import TestClient

import ecommerce_otp_service as service


def test_checkout_requires_verified_phone_then_tracks_fulfillment() -> None:
    service.ledger = service.CommerceLedger()
    client = TestClient(service.app)
    checkout = {
        "phone": "+14155550123",
        "sku": "canvas-weekender",
        "quantity": 1,
        "amount": 84.0,
    }

    rejected = client.post("/orders", json=checkout)
    assert rejected.status_code == 403

    service.ledger.mark_verified(checkout["phone"])
    created = client.post("/orders", json=checkout)
    assert created.status_code == 201
    order = created.json()
    assert order["status"] == "paid"
    assert order["receipt"].startswith("Receipt ord_")

    shipped = client.post(
        f"/orders/{order['order_id']}/fulfill",
        json={"tracking_number": "TRACK-2048"},
    )
    assert shipped.status_code == 200
    assert shipped.json()["status"] == "shipped"
    assert shipped.json()["updates"][-1] == "Order shipped: TRACK-2048"
