# 🧠 Bittensor Transaction Tracker & Twitter Bot

A **full-stack transaction monitoring system** for **Bittensor (TAO)** that tracks transfers between **Bittensor and Solana networks** and automatically posts real-time updates to **Twitter (X)**.

Built with **FastAPI (Python)** on the backend and **Next.js (TypeScript)** on the frontend, this system enables seamless real-time monitoring, analytics, and automated social media updates.

---

## 🚀 Key Features

### 🧩 Backend (FastAPI + Python)
- Real-time Transaction Monitoring using **Taostats API**
- Automated Twitter Bot with **Tweepy**
- Smart 5-minute Caching System to prevent rate limits
- Transaction Classification for Solana ↔ Bittensor transfers
- Background Processing with configurable intervals
- Rate Limit Handling and intelligent retry logic

### 💻 Frontend (Next.js + TypeScript)
- Clean and responsive **React Dashboard**
- Real-time updates with **auto-refresh**
- Twitter Bot Control Panel (enable/disable auto-tweeting, view tweet history)
- Transaction Analytics (daily totals, summaries)
- User-friendly error and loading states

---

## 🧰 Tech Stack

**Backend**
- FastAPI
- Tweepy
- Asyncio
- Pydantic

**Frontend**
- Next.js 15
- TypeScript
- Tailwind CSS
- Lucide React

---

## 📈 What It Tracks
- VoidAi SN106 Bittensor Network transactions  
- Bidirectional transfers between **Bittensor ↔ Solana**  
- Daily transaction totals and token amounts  
- Real-time Twitter notifications  
- Historical transaction analytics  

---

## 🎯 Use Cases
- 🪙 DeFi Monitoring — Track large TAO token movements  
- 📊 Network Analytics — Monitor Bittensor ecosystem activity  
- 🤖 Social Media Automation — Auto-tweet updates for transparency  
- 💼 Investment Tracking — Watch specific wallet activity  

---

## 🛡️ Advanced Features
- Enterprise-grade error handling  
- API rate limit protection  
- Configurable monitoring intervals  
- Test mode for development  
- Tweet history and debugging logs  
- CORS-enabled for frontend integration  



