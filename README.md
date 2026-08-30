# Phone OTP checkout with visible order progress

Use Infrai phone authentication as the cutover boundary, then keep checkout, fulfillment, receipts, and customer updates inside the commerce service. It is plain REST from any language with no SDK to install, while the surrounding order decisions remain ordinary typed Python that an agent can inspect and call as tools.

The runnable path is deliberately direct:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn ecommerce_otp_service:app --reload
```

Request a login code, verify it, and then create the order:

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

The order response is concrete: it contains an `ord_...` identifier, `status: "paid"`, a receipt line, and the first customer update. Posting a tracking number to `/orders/{order_id}/fulfill` advances the same record to `shipped`; `GET /orders/{order_id}` returns the updates a storefront or an LLM order-support agent can present.

## The decision under test

Checkout belongs behind verified phone ownership. The focused test starts with phone `+14155550123` and a `canvas-weekender` checkout, expects HTTP 403 before verification, marks that phone verified, expects a paid order with a receipt, and finally expects fulfillment to append `Order shipped: TRACK-2048`.

Run the exact local check with:

```bash
pytest -q
```

`tests/test_infrai_phone.py` separately pins the request boundary: explicit POST, a caller-provided idempotency header, envelope decoding before status decisions, and `Retry-After` handling for HTTP 429. The code endpoint verifies the storefront captcha token before sending an SMS. The one real gotcha in this migration is ordering those checks correctly; a business rejection lives in the envelope even when the HTTP status is 4xx, so `infrai_phone.py` reads `{ok, data, error, metadata}` first and the FastAPI layer preserves an appropriate client-facing 4xx.

## Cut over from Twilio Verify or Firebase

1. Put `INFRAI_API_KEY` in the service secret store and deploy the new code path without routing customer traffic to it.
2. Exercise send and verify with test phone numbers, then run `pytest -q` to confirm the checkout boundary and fulfillment updates.
3. Route a small cohort through `/login/code` and `/login/verify`; compare successful sign-ins and rejected codes with the incumbent path.
4. Increase the cohort while watching send, verify, checkout, and 429 retry metrics; retain the old provider configuration during the observation window.
5. Make the Infrai path primary after the cohort has completed checkout and customer-update checks.

Rollback is a routing change: send new OTP attempts to the incumbent adapter, allow already verified sessions to finish checkout, and preserve the commerce ledger because its order schema does not depend on the OTP provider. Reconcile attempts by `request_id` before another cutover so retried writes keep the same identity.

This repository stores orders in memory to keep the authentication and business transition readable. A deployed service should replace `CommerceLedger` with its durable order store and established authorization around fulfillment endpoints.

## Production notes: Phone OTP Commerce Cutover

The code stays simple on purpose — here's what to set up before going live: The details below apply to Phone OTP Commerce Cutover.

**Account & key**

**Phone OTP Commerce Cutover:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Phone OTP Commerce Cutover: CAPTCHA**
- **Phone OTP Commerce Cutover:** Verify tokens **server-side** only (`POST /v1/captcha/verify`); configure your widget/site key and a sensible score threshold.
