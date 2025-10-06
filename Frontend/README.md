# Frontend — Transaction Tracker UI

## Overview
Next.js 15 + React 19 UI for viewing Bittensor transfer stats and triggering a summary tweet.
The app calls the backend FastAPI running at `http://localhost:8000` by default (see `lib/api.ts`).

## Requirements
- Node.js 20+
- npm (or yarn/pnpm/bun)
- Backend API running locally on port 8000 (see `Backend/README.md`)

## Install
```bash
# from repo root
cd Frontend
npm install
```

## Development
```bash
npm run dev
```
- App: `http://localhost:3000`
- Backend expected at: `http://localhost:8000`

If your backend runs elsewhere, update `Frontend/lib/api.ts`:
```ts
const API_URL = "http://localhost:8000"; // change to your backend URL
```

## Build & Start
```bash
npm run build
npm start
```

## Project Structure
- `app/` — Next.js App Router pages and layout
- `components/` — UI components
- `lib/api.ts` — API client pointing to the backend

## Features
- Fetches and displays:
  - Total after filter
  - Transfers In (Solana → Bittensor)
  - Transfers Out (Bittensor → Solana)
- Button to trigger `POST /tweet` on the backend

## Troubleshooting
- API errors: ensure backend is running and CORS allows `http://localhost:3000`
- Connection refused: verify `API_URL` in `lib/api.ts` and ports
- Type errors: ensure Node 20+ and TypeScript installed via `npm install`
