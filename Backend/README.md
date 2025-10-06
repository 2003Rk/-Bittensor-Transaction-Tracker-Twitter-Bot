# Backend — Transaction Tracker API

## Overview
FastAPI service that fetches Bittensor transfer data from Taostats and provides two endpoints:
- `GET /track` — returns filtered and classified transactions
- `POST /tweet` — posts a summary to Twitter in the background

CORS is enabled for `http://localhost:3000` to allow the Next.js frontend to call the API during development.

## Requirements
- Python 3.10+
- Taostats API key
- (Optional) Twitter API credentials if you plan to use `POST /tweet`

## Install
```bash
# from repo root
cd Backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn requests tweepy pydantic
```

## Configuration
Configuration lives in `Backend/config.py`.

Edit the following values as needed:
- `API_KEY`: Taostats API key (secret)
- `ADDRESS`: Bittensor wallet address to track
- `TREASURY`: Treasury address to exclude from results
- `NETWORK`: Network name (default: `finney`)
- `LIMIT`: Page size for Taostats requests (default: `200`)
- `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`: required for tweeting

Security note: Do not commit real secrets. Consider using environment variables and loading them in `config.py` if deploying.

## Run (development)
```bash
# from Backend directory with venv activated
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

## API
### GET /track
Fetch and classify transactions for the configured address.

Query params (all optional, default to values in `config.py`):
- `api_key`: string
- `address`: string
- `network`: string
- `treasury`: string

Example:
```bash
curl "http://localhost:8000/track"
```

Response (shape):
```json
{
  "summary": {
    "total_after_filter": 12,
    "transfers_in": 7,
    "transfers_out": 5
  },
  "solana_to_bittensor": [
    { "extrinsic_id": "...", "from_ss58": "...", "to_ss58": "...", "amount": 1.2345, "timestamp": "..." }
  ],
  "bittensor_to_solana": [
    { "extrinsic_id": "...", "from_ss58": "...", "to_ss58": "...", "amount": 0.9876, "timestamp": "..." }
  ]
}
```

Notes:
- Amounts are converted from planck to TAO by dividing by `1e9`.
- Pagination in `get_txs.py` currently fetches up to 5 pages (`LIMIT` per page).
- Transactions involving the configured `TREASURY` address are filtered out.

### POST /tweet
Create a summary tweet based on the latest fetch and schedule posting in a background task.

Requires valid Twitter API credentials in `config.py`.

Example:
```bash
curl -X POST "http://localhost:8000/tweet"
```

Response:
```json
{ "status": "Tweet scheduled", "tweet_preview": "..." }
```

## CORS
CORS is configured to allow `http://localhost:3000`. Update this in `main.py` (`allow_origins`) for your deployment.

## Troubleshooting
- 401/403 from Taostats: verify `API_KEY` and rate limits.
- Empty results: confirm `ADDRESS`, `NETWORK`, and that recent txs exist.
- Twitter errors: ensure all four Twitter credentials are set and valid.
- CORS errors in frontend: confirm backend runs on `8000` and origins match. 