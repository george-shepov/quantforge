# Metered API access

QuantForge can require API keys for every `/api/*` endpoint except health, API documentation, and the admin key-creation endpoint.

## Enable

Store a strong admin token in the deployment vault and configure:

```env
QUANTFORGE_METERED_API_ENABLED=true
QUANTFORGE_METERING_ADMIN_TOKEN=<vault-managed-secret>
QUANTFORGE_METERING_DB=/data/quantforge/metering.sqlite3
```

Do not commit the admin token or issued API keys.

## Issue a key

```bash
curl -X POST https://quantforge.giorgiy.org/api/developer/keys \
  -H 'Content-Type: application/json' \
  -H 'X-QuantForge-Admin-Token: <admin-token>' \
  -d '{
    "name": "First developer",
    "plan": "developer",
    "monthly_quota": 10000,
    "rate_limit_per_minute": 60
  }'
```

The plaintext key is returned once. QuantForge persists only its SHA-256 hash.

## Call the API

```bash
curl https://quantforge.giorgiy.org/api/catalog \
  -H 'X-QuantForge-API-Key: qf_live_...'
```

Metered responses include:

- `X-QuantForge-Usage-Limit`
- `X-QuantForge-Usage-Remaining`
- `X-QuantForge-RateLimit-Minute`

## Read usage

```bash
curl https://quantforge.giorgiy.org/api/developer/usage \
  -H 'X-QuantForge-API-Key: qf_live_...'
```

The response reports the active UTC month, consumed units, remaining units, plan, quota, and per-minute limit.

## Charging model

The first release deliberately separates metering from payment. The `api_usage` ledger is the source for later Stripe usage aggregation. This prevents payment-provider failures from affecting research API availability and allows free, developer, partner, and internal plans to use the same access layer.
