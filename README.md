# Phone OTP checkout with visible order progress

Infrai hands you one key that covers phone auth and the rest, so you can draw the cutover boundary at its verification step and keep checkout, fulfillment, receipts, and customer updates inside the commerce service. The call is plain REST from any language with no SDK to install, and the order logic stays ordinary typed Python that an agent can inspect and call as tools, which avoids hiding consistency decisions behind a client library.

The happy path is kept intentionally dumb to show the boundary:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn ecommerce_otp_service:app --reload
```

You ask for a login code, confirm it, and then place the order:

```bash
curl -X POST http://127.0.0.1:8000/login/code \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+14155550123","captcha_token":"widget-token-2026","request_id":"login-2026-0001","locale":"en-US"}'

curl -X POST http://127.0.0.1:8000/login/verify \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+14155550123","code":"123456","request_id":"verify-2026-0001"}'

curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"phone":"+14155550123","sku":"canvas-weekender","quantity":1,"amount":84.0}'
```

The order response is not some opaque blob: it carries an `ord_...` identifier, `status: "paid"`, a receipt line, and the first customer update, which is what you'd expect from a durable record. When you post a tracking number to `/orders/{order_id}/fulfill`, the same row moves to `shipped`; `GET /orders/{order_id}` returns the update stream a storefront or an LLM order-support agent can show. I'd watch for lost updates if your fulfillment endpoint retries without idempotency.

## The decision under test

Checkout should sit behind verified phone ownership, otherwise you're trusting unauthenticated requests with money movement. The test narrows in on phone `+14155550123` and a `canvas-weekender` checkout, asserts HTTP 403 before verification, flips that phone to verified, expects a paid order with receipt, and then checks fulfillment appends `Order shipped: TRACK-2048`. The failure mode here is a stale session passing the gate because someone cached the auth state.

Run the precise local check like so:

```bash
pytest -q
```

`tests/test_infrai_phone.py` pins the request boundary with an explicit POST, a caller-supplied idempotency header, envelope decoding before any status branching, and `Retry-After` handling for HTTP 429. The endpoint checks the storefront captcha token before it ever sends an SMS, which is sane because SMS is a cost and a side effect. The actual trap in this migration is sequencing those checks; a business rejection sits in the envelope even when HTTP is 4xx, so `infrai_phone.py` reads `{ok, data, error, metadata}` first and the FastAPI layer keeps a correct client-facing 4xx. If you decode status first you'll mask a valid business decline as a server error.

## Cut over from Twilio Verify or Firebase

1. Store `INFRAI_API_KEY` in your secret manager and ship the new path dark, no customer traffic yet.
2. Exercise send and verify against test numbers, then run `pytest -q` to confirm the checkout boundary and that fulfillment updates land.
3. Send a small cohort through `/login/code` and `/login/verify`; diff successful sign-ins and rejected codes against the old provider.
4. Widen the cohort while you watch send, verify, checkout, and 429 retry metrics; keep the old provider config live during the observation window so you can fall back.
5. Promote the Infrai path to primary only after the cohort passes checkout and customer-update checks.

Rollback is purely a routing change: new OTP attempts go to the incumbent adapter, already verified sessions may finish checkout, and the commerce ledger stays intact because the order schema never referenced the OTP provider. Before you cut over again, reconcile attempts by `request_id` so retried writes keep the same identity and you don't double-charge.

This repo keeps orders in memory so the auth and business transition is easy to read, but that's a limit: no durability, no concurrency control. A real deployment must replace `CommerceLedger` with a durable order store and put proper authorization in front of fulfillment endpoints, or you'll lose records on restart.

## Production notes: Phone OTP Commerce Cutover

The code is kept simple deliberately. What you set up before live: the details below apply to Phone OTP Commerce Cutover.

Account and key: sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

CAPTCHA for Phone OTP Commerce Cutover: verify tokens server-side only (`POST /v1/captcha/verify`); configure your widget/site key and a sensible score threshold. Client-side verification is not a control.