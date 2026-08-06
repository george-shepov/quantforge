# London regional Bybit connector

The London connector is a read-only market-data edge service. It exposes only
`GET /health` and the authenticated `POST /v1/exchanges/bybit/kline` route. It
calls the fixed public endpoint `https://api.bybit.com/v5/market/kline`; it has
no order, account, or execution routes.

Requests from the main API use `X-QuantForge-Timestamp`,
`X-QuantForge-Nonce`, and `X-QuantForge-Signature`. The signature covers the
timestamp, nonce, method, path, and SHA-256 digest of the exact request body.
Nonces and expiry metadata are stored in SQLite only. The HMAC secret is never
written to SQLite or application logs.

The connector is deployed with `docker-compose.eu.yml` and binds only to
`127.0.0.1:8091`. Nginx publishes it at:

```text
https://eu.quantforge.giorgiy.org/api/edge/
```

The main Bybit adapter prefers the regional connector when configured. For
controlled fallback testing, `BYBIT_REGIONAL_CONNECTOR_PREFER=false` makes it
try direct Bybit first and retry through London only after a direct HTTP 403.
If both paths fail, the existing synthetic fallback remains the final option.
Testnet execution remains disabled by the existing QuantForge safety gates.
