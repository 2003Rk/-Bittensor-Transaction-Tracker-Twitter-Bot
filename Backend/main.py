# main.py (improvements)
import os
import uvicorn
import tweepy
import requests
import time
import asyncio
from typing import Optional, Union
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from config import API_KEY, ADDRESS, TREASURY, NETWORK, TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
from get_txs import get_all_transfers, classify_transactions

# Simple in-memory cache
cache = {
    "data": None,
    "timestamp": None,
    "cache_duration": 300  # 5 minutes cache
}

# Store last known transactions to detect new ones
last_known_transactions = {
    "transfers_in": [],
    "transfers_out": [],
    "last_check": None
}

# Store tweet history for debugging
tweet_history = []

# Auto-tweet settings
AUTO_TWEET_SETTINGS = {
    "enabled": True,
    "check_interval": 60,  # Check every 60 seconds for new transactions
    "min_amount_tao": 0,  # Tweet ALL transactions (including 0 TAO)
    "test_mode": False,  # Real tweets enabled - post to Twitter
    "tweet_existing_on_startup": False,  # Disable startup tweeting to avoid rate limits
}

# Twitter API v2 client with OAuth 2.0
twitter_client = tweepy.Client(
    bearer_token=None,  # We'll use OAuth 1.0a for now, but with v2 endpoints
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET,
    wait_on_rate_limit=True
)

# Keep the old API for backward compatibility testing
auth = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
)
twitter_api = tweepy.API(auth)

# Background task for monitoring
monitoring_task = None

def test_twitter_credentials():
    """Test Twitter API credentials"""
    try:
        # Test API v2
        print("🔍 Testing Twitter API v2 credentials...")
        response = twitter_client.get_me()
        print(f"✅ API v2 works! Response: {response}")
        return True
    except Exception as e:
        print(f"❌ API v2 failed: {e}")
    
    try:
        # Test API v1.1
        print("🔍 Testing Twitter API v1.1 credentials...")
        me = twitter_api.verify_credentials()
        if me:
            print(f"✅ API v1.1 works! Connected as: @{me.screen_name}")
            return True
        else:
            print("❌ API v1.1 failed: No user data returned")
    except Exception as e:
        print(f"❌ API v1.1 failed: {e}")
    
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitoring_task
    
    # Startup
    if AUTO_TWEET_SETTINGS["enabled"]:
        print("🚀 Starting automatic Twitter monitoring...")
        print(f"🔍 DEBUG: Current settings = {AUTO_TWEET_SETTINGS}")
        
        # Test Twitter credentials first
        print("🔐 Testing Twitter API credentials...")
        if not test_twitter_credentials():
            print("⚠️ Twitter credentials test failed - tweets may not work!")
        
        # Initialize with existing transactions (avoid tweeting on startup to prevent rate limits)
        try:
            print("� Initializing with existing transactions...")
            data = get_all_transfers(API_KEY, ADDRESS, NETWORK)
            filtered, transfers_in, transfers_out = classify_transactions(data, TREASURY, ADDRESS)
            
            # Initialize for future monitoring
            last_known_transactions["transfers_in"] = transfers_in.copy()
            last_known_transactions["transfers_out"] = transfers_out.copy()
            last_known_transactions["last_check"] = datetime.now()
            
            if AUTO_TWEET_SETTINGS.get("tweet_existing_on_startup", False):
                print("📱 Tweeting about existing transactions...")
                # Calculate daily totals once for all tweets
                daily_totals = get_daily_transfer_totals(data)
                
                # Tweet about existing incoming transactions (reduce to 2 to be very conservative)
                recent_in = transfers_in[:2] if len(transfers_in) > 2 else transfers_in
                for i, tx in enumerate(recent_in):
                    tweet_text = create_transaction_tweet(tx, "in", data, daily_totals)
                    if tweet_text:
                        print(f"🐦 Tweeting existing incoming transaction {i+1}/{len(recent_in)}...")
                        post_tweet(tweet_text)
                        await asyncio.sleep(10)  # Wait 10 seconds between tweets
                
                # Tweet about existing outgoing transactions (reduce to 2 to be very conservative)
                recent_out = transfers_out[:2] if len(transfers_out) > 2 else transfers_out
                for i, tx in enumerate(recent_out):
                    tweet_text = create_transaction_tweet(tx, "out", data, daily_totals)
                    if tweet_text:
                        print(f"🐦 Tweeting existing outgoing transaction {i+1}/{len(recent_out)}...")
                        post_tweet(tweet_text)
                        await asyncio.sleep(10)  # Wait 10 seconds between tweets
                
                print(f"✅ Tweeted about {len(recent_in)} incoming and {len(recent_out)} outgoing transactions")
            else:
                print(f"✅ Initialized with {len(transfers_in)} incoming and {len(transfers_out)} outgoing transactions (startup tweeting disabled)")
        except requests.exceptions.HTTPError as e:
            if "429" in str(e):
                print("⚠️ Rate limited during startup - will retry during normal operation")
            else:
                print(f"⚠️ Failed to initialize transactions: {e}")
        except Exception as e:
            print(f"⚠️ Failed to initialize transactions: {e}")
        
        # Start the background monitoring task
        monitoring_task = asyncio.create_task(auto_tweet_new_transactions())
    
    yield
    
    # Shutdown
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Transaction Tracker API with Twitter Bot", lifespan=lifespan)

# Allow frontend origin(s) — replace with your production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3002"],  # frontend dev origin(s)
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Transaction Tracker API is running"}

@app.get("/cache-status")
async def cache_status():
    """Get cache status information"""
    if cache["timestamp"] is None:
        return {
            "cached": False,
            "message": "No data cached yet"
        }
    
    cache_age = time.time() - cache["timestamp"]
    cache_valid = cache_age < cache["cache_duration"]
    last_updated = datetime.fromtimestamp(cache["timestamp"]).strftime('%Y-%m-%d %H:%M:%S')
    
    return {
        "cached": True,
        "cache_valid": cache_valid,
        "last_updated": last_updated,
        "cache_age_seconds": int(cache_age),
        "cache_duration_seconds": cache["cache_duration"],
        "next_refresh_in_seconds": max(0, int(cache["cache_duration"] - cache_age)) if cache_valid else 0
    }

class TxSummary(BaseModel):
    extrinsic_id: str | None
    from_ss58: str | None
    to_ss58: str | None
    amount: float | None
    timestamp: str | None

class TrackResponse(BaseModel):
    summary: dict
    solana_to_bittensor: list[TxSummary]
    bittensor_to_solana: list[TxSummary]

# convert internal structure into safe Pydantic-friendly dicts
async def format_tx(tx: dict):
    return {
        "extrinsic_id": tx.get("extrinsic_id"),
        "from_ss58": tx.get("from", {}).get("ss58") if tx.get("from") else None,
        "to_ss58": tx.get("to", {}).get("ss58") if tx.get("to") else None,
        "amount": round(int(tx["amount"]) / 1e9, 4) if tx.get("amount") is not None else None,
        "timestamp": tx.get("timestamp"),
    }

def is_cache_valid():
    """Check if cached data is still valid"""
    if cache["data"] is None or cache["timestamp"] is None:
        return False
    
    cache_age = time.time() - cache["timestamp"]
    return cache_age < cache["cache_duration"]

def get_cached_or_fresh_data(api_key: str, address: str, network: str, treasury: str):
    """Get data from cache if valid, otherwise fetch fresh data"""
    if is_cache_valid():
        print("✅ Returning cached data")
        return cache["data"]
    
    print("🔄 Cache expired or empty, fetching fresh data...")
    try:
        # Fetch fresh data
        data = get_all_transfers(api_key, address, network)
        filtered, transfers_in, transfers_out = classify_transactions(data, treasury, address)
        
        # Prepare the response
        fresh_data = {
            "summary": {
                "total_after_filter": len(filtered),
                "transfers_in": len(transfers_in),
                "transfers_out": len(transfers_out),
            },
            "transfers_in_raw": transfers_in,
            "transfers_out_raw": transfers_out,
        }
        
        # Update cache
        cache["data"] = fresh_data
        cache["timestamp"] = time.time()
        
        print(f"✅ Data cached at {datetime.now().strftime('%H:%M:%S')}")
        return fresh_data
        
    except requests.exceptions.HTTPError as e:
        if "429" in str(e):
            # If we have cached data and hit rate limit, return cached data with a warning
            if cache["data"] is not None:
                cache_age_minutes = int((time.time() - cache["timestamp"]) / 60)
                print(f"⚠️ Rate limited, returning cached data (age: {cache_age_minutes} minutes)")
                return cache["data"]
            raise HTTPException(status_code=429, detail="API rate limit exceeded. Auto-tweet monitoring is active and will continue in the background. Data will refresh when rate limits clear.")
        raise HTTPException(status_code=500, detail=f"API error: {str(e)}")

@app.get("/track", response_model=TrackResponse)
async def track_transactions(api_key: str = API_KEY, address: str = ADDRESS, network: str = NETWORK, treasury: str = TREASURY):
    try:
        cached_data = get_cached_or_fresh_data(api_key, address, network, treasury)
        
        return {
            "summary": cached_data["summary"],
            "solana_to_bittensor": [await format_tx(tx) for tx in cached_data["transfers_in_raw"]],
            "bittensor_to_solana": [await format_tx(tx) for tx in cached_data["transfers_out_raw"]],
        }
    except HTTPException:
        # Re-raise HTTP exceptions (like rate limit errors)
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

# Post tweet using Twitter API v2 with rate limiting
def post_tweet(tweet_text: str):
    try:
        print(f"🔍 DEBUG: test_mode setting = {AUTO_TWEET_SETTINGS.get('test_mode', False)}")
        if AUTO_TWEET_SETTINGS.get("test_mode", False):
            # Test mode - don't actually post to Twitter
            print(f"🧪 TEST MODE - Would post tweet:")
            print(f"   📝 {tweet_text}")
            tweet_entry = {
                "timestamp": datetime.now().isoformat(),
                "status": "test_success",
                "text": tweet_text,
                "preview": tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text
            }
        else:
            # Try Twitter API v2 first
            try:
                response = twitter_client.create_tweet(text=tweet_text)
                tweet_id = None
                # Handle tweepy v2 response format safely
                try:
                    tweet_id = getattr(getattr(response, 'data', {}), 'get', lambda x: None)('id')
                except:
                    try:
                        tweet_id = getattr(response, 'id', None)
                    except:
                        tweet_id = None
                
                tweet_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "status": "success_v2",
                    "text": tweet_text,
                    "preview": tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text,
                    "tweet_id": tweet_id
                }
                print(f"✅ Tweet posted successfully (API v2): {tweet_text[:50]}...")
            except Exception as v2_error:
                # Check if it's a rate limit error
                if "429" in str(v2_error) or "rate limit" in str(v2_error).lower():
                    print(f"🚫 Twitter rate limit reached, skipping tweet to avoid spam")
                    tweet_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "status": "rate_limited",
                        "text": tweet_text,
                        "preview": tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text,
                        "error": "Twitter rate limit reached"
                    }
                else:
                    # Try fallback to API v1.1 for other errors
                    try:
                        print(f"⚠️ API v2 failed, trying v1.1: {v2_error}")
                        twitter_api.update_status(tweet_text)
                        tweet_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "status": "success_v1",
                            "text": tweet_text,
                            "preview": tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text
                        }
                        print(f"✅ Tweet posted successfully (API v1.1): {tweet_text[:50]}...")
                    except Exception as v1_error:
                        # Both APIs failed
                        if "429" in str(v1_error) or "rate limit" in str(v1_error).lower():
                            print(f"🚫 Twitter rate limit reached on both APIs, skipping tweet")
                            tweet_entry = {
                                "timestamp": datetime.now().isoformat(),
                                "status": "rate_limited",
                                "text": tweet_text,
                                "preview": tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text,
                                "error": "Twitter rate limit reached on both APIs"
                            }
                        else:
                            raise v1_error
                print(f"✅ Tweet posted successfully (API v1.1): {tweet_text[:50]}...")
            
        tweet_history.append(tweet_entry)
        # Keep only last 20 tweets
        if len(tweet_history) > 20:
            tweet_history.pop(0)
            
    except Exception as e:
        tweet_entry = {
            "timestamp": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e),
            "text": tweet_text,
            "preview": tweet_text[:100] + "..." if len(tweet_text) > 100 else tweet_text
        }
        tweet_history.append(tweet_entry)
        # Keep only last 20 tweets
        if len(tweet_history) > 20:
            tweet_history.pop(0)
        print(f"❌ Failed to post tweet: {e}")

def get_transaction_id(tx):
    """Generate a unique ID for a transaction"""
    return f"{tx.get('extrinsic_id', '')}_{tx.get('from', {}).get('ss58', '')}_{tx.get('to', {}).get('ss58', '')}_{tx.get('amount', '')}"

def detect_new_transactions(current_transfers_in, current_transfers_out):
    """Compare current transactions with last known transactions to find new ones"""
    global last_known_transactions
    
    new_transfers_in = []
    new_transfers_out = []
    
    # Get IDs of last known transactions
    last_in_ids = set(get_transaction_id(tx) for tx in last_known_transactions["transfers_in"])
    last_out_ids = set(get_transaction_id(tx) for tx in last_known_transactions["transfers_out"])
    
    # Find new incoming transfers
    for tx in current_transfers_in:
        tx_id = get_transaction_id(tx)
        if tx_id not in last_in_ids:
            new_transfers_in.append(tx)
    
    # Find new outgoing transfers
    for tx in current_transfers_out:
        tx_id = get_transaction_id(tx)
        if tx_id not in last_out_ids:
            new_transfers_out.append(tx)
    
    # Update last known transactions
    last_known_transactions["transfers_in"] = current_transfers_in.copy()
    last_known_transactions["transfers_out"] = current_transfers_out.copy()
    last_known_transactions["last_check"] = datetime.now()
    
    return new_transfers_in, new_transfers_out

def get_daily_transfer_totals(existing_data=None):
    """Calculate today's total transfer amounts for both directions"""
    try:
        # Use existing data if provided to avoid additional API calls
        if existing_data:
            data = existing_data
        elif cache["data"] and cache["timestamp"] and (time.time() - cache["timestamp"] < 300):
            data = cache["data"]
        else:
            # This should rarely happen now since we'll pass existing data
            print("⚠️ Making additional API call for daily totals - consider optimizing")
            return {'tao_in': 0, 'tao_out': 0}
        
        filtered, transfers_in, transfers_out = classify_transactions(data, TREASURY, ADDRESS)
        
        # Calculate totals for each direction
        daily_in_tao = 0
        daily_out_tao = 0
        
        for tx in transfers_in:
            tx_amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
            daily_in_tao += tx_amount
            
        for tx in transfers_out:
            tx_amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
            daily_out_tao += tx_amount
        
        return {
            'tao_in': round(daily_in_tao, 4),
            'tao_out': round(daily_out_tao, 4)
        }
    except Exception as e:
        print(f"⚠️ Error calculating daily totals: {e}")
        return {'tao_in': 0, 'tao_out': 0}

def create_transaction_tweet(tx, direction, existing_data=None, daily_totals=None):
    """Create a stylish and eye-catching tweet for a new transaction"""
    try:
        # Get transaction details
        amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
        extrinsic_id = tx.get('extrinsic_id', '')
        block_number = tx.get('block_number', '')
        
        # Get daily totals (use provided data to avoid extra API calls)
        if daily_totals is None:
            daily_totals = get_daily_transfer_totals(existing_data)
        
        # Get addresses for path display
        from_addr = tx.get('from', {}).get('ss58', 'Unknown')
        to_addr = tx.get('to', {}).get('ss58', 'Unknown')
        
        # Format addresses for display (first 6 + last 6 characters)
        from_display = f"{from_addr[:6]}...{from_addr[-6:]}" if len(from_addr) > 12 else from_addr
        to_display = f"{to_addr[:6]}...{to_addr[-6:]}" if len(to_addr) > 12 else to_addr
        
        # Get current time for timestamp
        current_time = datetime.now().strftime('%H:%M:%S UTC')
        
        # Determine direction and create stylish path
        if direction == "in":
            path_direction = "Solana → Bittensor"
            direction_emoji = "📥"
        else:
            path_direction = "Bittensor → Solana" 
            direction_emoji = "📤"
        
        # Create transaction link
        tx_link = ""
        if extrinsic_id:
            tx_link = f"🔗 **Transaction:** https://taostats.io/extrinsic/{extrinsic_id}\n\n"
        elif block_number:
            tx_link = f"🔗 **Block:** https://taostats.io/block/{block_number}\n\n"
        
        # Create the stylish tweet format
        tweet = (
            f"🚀 **VoidAi [ SN106 (Bittensor) ] Tracker** 🚀\n\n"
            f"📊 **Daily Totals:**\n"
            f"   • Bittensor → Solana: {daily_totals['tao_out']} TAO\n"
            f"   • Solana → Bittensor: {daily_totals['tao_in']} TAO\n\n"
            f"{direction_emoji} **New Transfer Detected:** {amount} TAO 🟡\n\n"
            f"🔗 **Path:**\n"
            f"   {from_display} → {to_display}\n"
            f"   ({path_direction})\n\n"
            f"{tx_link}"
            f"⏰ **Time:** {current_time}\n\n"
            f"#Bittensor #TAO #DeFi #Blockchain #SN106"
        )
        
        return tweet
    except Exception as e:
        print(f"❌ Error creating tweet: {e}")
        return None

async def auto_tweet_new_transactions():
    """Automatically check for and tweet new transactions"""
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while AUTO_TWEET_SETTINGS["enabled"]:
        try:
            print("🔍 Checking for new transactions...")
            
            # Get current transactions
            data = get_all_transfers(API_KEY, ADDRESS, NETWORK)
            filtered, transfers_in, transfers_out = classify_transactions(data, TREASURY, ADDRESS)
            
            # Reset error counter on success
            consecutive_errors = 0
            
            # Detect new transactions
            new_in, new_out = detect_new_transactions(transfers_in, transfers_out)
            
            print(f"📊 Transaction check complete:")
            print(f"   • Total transactions found: {len(transfers_in)} in, {len(transfers_out)} out")
            print(f"   • New transactions detected: {len(new_in)} in, {len(new_out)} out")
            
            # Calculate daily totals once for all tweets
            daily_totals = get_daily_transfer_totals(data)
            
            # Tweet about existing transactions if no new ones found (for testing purposes)
            if not new_in and not new_out and len(transfers_in) > 0 or len(transfers_out) > 0:
                print("📱 No new transactions - tweeting about existing transactions for testing...")
                
                # Tweet about first 3 existing incoming transactions
                existing_in = transfers_in[:3] if len(transfers_in) > 3 else transfers_in
                for i, tx in enumerate(existing_in):
                    tweet_text = create_transaction_tweet(tx, "in", data, daily_totals)
                    if tweet_text:
                        print(f"🐦 Tweeting existing incoming transaction {i+1}/{len(existing_in)}...")
                        post_tweet(tweet_text)
                        await asyncio.sleep(10)  # Wait 10 seconds between tweets
                
                # Tweet about first 3 existing outgoing transactions
                existing_out = transfers_out[:3] if len(transfers_out) > 3 else transfers_out
                for i, tx in enumerate(existing_out):
                    tweet_text = create_transaction_tweet(tx, "out", data, daily_totals)
                    if tweet_text:
                        print(f"🐦 Tweeting existing outgoing transaction {i+1}/{len(existing_out)}...")
                        post_tweet(tweet_text)
                        await asyncio.sleep(10)  # Wait 10 seconds between tweets
            
            # Tweet new incoming transactions (if any)
            for i, tx in enumerate(new_in):
                tweet_text = create_transaction_tweet(tx, "in", data, daily_totals)
                if tweet_text:
                    print(f"🐦 Tweeting NEW incoming transaction {i+1}/{len(new_in)}...")
                    post_tweet(tweet_text)
                    await asyncio.sleep(5)  # Wait 5 seconds between tweets
            
            # Tweet new outgoing transactions (if any)
            for i, tx in enumerate(new_out):
                tweet_text = create_transaction_tweet(tx, "out", data, daily_totals)
                if tweet_text:
                    print(f"🐦 Tweeting NEW outgoing transaction {i+1}/{len(new_out)}...")
                    post_tweet(tweet_text)
                    await asyncio.sleep(5)  # Wait 5 seconds between tweets
            
            if new_in or new_out:
                print(f"✅ Successfully processed {len(new_in)} incoming and {len(new_out)} outgoing transactions")
            else:
                print("📊 No new transactions found - monitoring continues...")
                
        except requests.exceptions.HTTPError as e:
            consecutive_errors += 1
            if "429" in str(e):
                wait_time = min(300, 60 * consecutive_errors)  # Wait longer on consecutive rate limits, max 5 minutes
                print(f"⚠️ Rate limited, waiting {wait_time} seconds before retry (attempt {consecutive_errors})")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"❌ HTTP Error in auto-tweet checker: {e}")
        except Exception as e:
            consecutive_errors += 1
            print(f"❌ Error in auto-tweet checker: {e}")
            
        # If too many consecutive errors, disable auto-tweeting
        if consecutive_errors >= max_consecutive_errors:
            print(f"⚠️ Too many consecutive errors ({consecutive_errors}), disabling auto-tweeting")
            AUTO_TWEET_SETTINGS["enabled"] = False
            break
        
        # Wait before next check (longer wait on errors)
        wait_time = AUTO_TWEET_SETTINGS["check_interval"] + (30 * consecutive_errors)
        await asyncio.sleep(wait_time)



@app.get("/auto-tweet/status")
async def auto_tweet_status():
    """Get the current auto-tweet settings and status"""
    return {
        "enabled": AUTO_TWEET_SETTINGS["enabled"],
        "check_interval_seconds": AUTO_TWEET_SETTINGS["check_interval"],
        "min_amount_tao": AUTO_TWEET_SETTINGS["min_amount_tao"],
        "last_check": last_known_transactions["last_check"].isoformat() if last_known_transactions["last_check"] else None,
        "known_transactions": {
            "transfers_in": len(last_known_transactions["transfers_in"]),
            "transfers_out": len(last_known_transactions["transfers_out"])
        },
        "recent_tweets": len(tweet_history),
        "last_tweet": tweet_history[-1] if tweet_history else None
    }

@app.get("/auto-tweet/history")
async def auto_tweet_history():
    """Get recent tweet history for debugging"""
    return {
        "total_tweets": len(tweet_history),
        "history": tweet_history
    }

@app.get("/auto-tweet/test-connection")
async def test_twitter_connection_get():
    """Test Twitter API connection (GET request) - just checks credentials"""
    try:
        # Test by getting user info instead of posting
        user = twitter_api.verify_credentials()
        return {
            "status": "success",
            "message": "Twitter API connection successful!",
            "twitter_user": user.screen_name,
            "test_mode": AUTO_TWEET_SETTINGS.get("test_mode", False)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Twitter API connection failed: {str(e)}"
        }

@app.post("/auto-tweet/test")
async def test_twitter_post():
    """Test Twitter API connection with a simple tweet"""
    try:
        test_tweet = f"🤖 Auto-tweet system test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} #BittensorTracker"
        
        if AUTO_TWEET_SETTINGS.get("test_mode", False):
            return {
                "status": "test_mode", 
                "message": "Test mode enabled - would post: " + test_tweet
            }
        else:
            twitter_api.update_status(test_tweet)
            return {
                "status": "success", 
                "message": "Test tweet posted successfully!",
                "tweet": test_tweet
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Twitter API test failed: {str(e)}"
        }

@app.post("/auto-tweet/toggle")
async def toggle_auto_tweet():
    """Enable or disable automatic tweeting"""
    global monitoring_task
    
    AUTO_TWEET_SETTINGS["enabled"] = not AUTO_TWEET_SETTINGS["enabled"]
    status = "enabled" if AUTO_TWEET_SETTINGS["enabled"] else "disabled"
    
    if AUTO_TWEET_SETTINGS["enabled"]:
        # Start a new monitoring task if not already running
        if monitoring_task is None or monitoring_task.done():
            monitoring_task = asyncio.create_task(auto_tweet_new_transactions())
            print("🚀 Auto-tweet monitoring restarted")
    else:
        # Cancel the existing task
        if monitoring_task and not monitoring_task.done():
            monitoring_task.cancel()
            print("⏹ Auto-tweet monitoring stopped")
        
    return {"status": f"Auto-tweeting {status}", "enabled": AUTO_TWEET_SETTINGS["enabled"]}

@app.post("/auto-tweet/settings")
async def update_auto_tweet_settings(check_interval: Optional[int] = None, min_amount_tao: Optional[float] = None, test_mode: Optional[bool] = None):
    """Update auto-tweet settings"""
    if check_interval is not None and check_interval >= 30:  # Minimum 30 seconds
        AUTO_TWEET_SETTINGS["check_interval"] = check_interval
    
    if min_amount_tao is not None and min_amount_tao >= 0:
        AUTO_TWEET_SETTINGS["min_amount_tao"] = min_amount_tao
        
    if test_mode is not None:
        AUTO_TWEET_SETTINGS["test_mode"] = test_mode
    
    return {
        "message": "Settings updated successfully",
        "settings": AUTO_TWEET_SETTINGS
    }

@app.post("/tweet")
async def tweet_summary(background_tasks: BackgroundTasks, api_key: str = API_KEY, address: str = ADDRESS, network: str = NETWORK, treasury: str = TREASURY):
    try:
        data = get_all_transfers(api_key, address, network) if callable(get_all_transfers) else get_all_transfers(api_key, address, network)
        filtered, transfers_in, transfers_out = classify_transactions(data, treasury, address)

        tweet = (
            f"📊 Transaction Tracker Update\n"
            f"✔ After filtering: {len(filtered)} txs\n"
            f"➡ In (Bittensor→Solana): {len(transfers_in)}\n"
            f"⬅ Out (Solana→Bittensor): {len(transfers_out)}"
        )

        if transfers_in:
            tx = transfers_in[0]
            tweet += f"\n\nExample IN:\n{tx['from']['ss58'][:6]}... → {tx['to']['ss58'][:6]}... | {round(int(tx['amount'])/1e9,4)} TAO"
        if transfers_out:
            tx = transfers_out[0]
            tweet += f"\n\nExample OUT:\n{tx['from']['ss58'][:6]}... → {tx['to']['ss58'][:6]}... | {round(int(tx['amount'])/1e9,4)} TAO"

        # background post
        background_tasks.add_task(post_tweet, tweet)
        return {"status": "Tweet scheduled", "tweet_preview": tweet}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auto-tweet/force-tweet-recent")
async def force_tweet_recent_transactions():
    """Force tweet about the most recent transactions for testing"""
    try:
        print("🔍 Forcing tweet about recent transactions...")
        
        # Get current transactions
        data = get_all_transfers(API_KEY, ADDRESS, NETWORK)
        filtered, transfers_in, transfers_out = classify_transactions(data, TREASURY, ADDRESS)
        
        tweets_sent = 0
        
        # Tweet about the most recent incoming transaction
        if transfers_in:
            recent_tx = transfers_in[0]  # Most recent
            tweet_text = create_transaction_tweet(recent_tx, "in")
            if tweet_text:
                post_tweet(tweet_text)
                tweets_sent += 1
                print(f"🐦 Posted tweet about recent incoming transaction")
        
        # Tweet about the most recent outgoing transaction  
        if transfers_out:
            recent_tx = transfers_out[0]  # Most recent
            tweet_text = create_transaction_tweet(recent_tx, "out")
            if tweet_text:
                post_tweet(tweet_text)
                tweets_sent += 1
                print(f"🐦 Posted tweet about recent outgoing transaction")
        
        return {
            "status": "success",
            "message": f"Force-tweeted {tweets_sent} recent transactions",
            "tweets_sent": tweets_sent,
            "total_transactions": {
                "incoming": len(transfers_in),
                "outgoing": len(transfers_out)
            }
        }
        
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Failed to force tweet: {str(e)}"
        }

@app.get("/twitter/test-credentials")
async def test_twitter_credentials_endpoint():
    """Test Twitter API credentials via endpoint"""
    success = test_twitter_credentials()
    return {
        "credentials_valid": success,
        "message": "Check server logs for detailed results"
    }

@app.post("/twitter/test-single-tweet")
async def test_single_tweet():
    """Post a single test tweet about the most recent transaction"""
    try:
        # Get most recent transaction
        data = get_all_transfers(API_KEY, ADDRESS, NETWORK)
        filtered, transfers_in, transfers_out = classify_transactions(data, TREASURY, ADDRESS)
        
        if not transfers_in and not transfers_out:
            return {"error": "No transactions found"}
        
        # Get daily totals
        daily_totals = get_daily_transfer_totals(data)
        
        # Use the most recent transaction (preferably one with 0 value for testing)
        test_tx = None
        if transfers_in:
            # Look for a zero-value transaction first
            for tx in transfers_in:
                amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
                if amount == 0:
                    test_tx = tx
                    direction = "in"
                    break
            
            # If no zero-value, use the first one
            if not test_tx:
                test_tx = transfers_in[0]
                direction = "in"
        elif transfers_out:
            # Look for a zero-value transaction first
            for tx in transfers_out:
                amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
                if amount == 0:
                    test_tx = tx
                    direction = "out"
                    break
            
            # If no zero-value, use the first one
            if not test_tx:
                test_tx = transfers_out[0]
                direction = "out"
        
        if test_tx:
            tweet_text = create_transaction_tweet(test_tx, direction, data, daily_totals)
            if tweet_text:
                post_tweet(tweet_text)
                
                amount = round(int(test_tx.get('amount', 0)) / 1e9, 4) if test_tx.get('amount') else 0
                return {
                    "success": True,
                    "message": f"Test tweet posted for {amount} TAO transaction",
                    "tweet_preview": tweet_text[:200] + "..." if len(tweet_text) > 200 else tweet_text,
                    "direction": direction
                }
            else:
                return {"error": "Failed to create tweet text"}
        else:
            return {"error": "No suitable transaction found"}
            
    except Exception as e:
        return {"error": f"Failed to post test tweet: {str(e)}"}

@app.post("/twitter/post-zero-transactions")
async def post_zero_transactions():
    """Post tweets about existing zero-value transactions"""
    try:
        # Get all transactions
        data = get_all_transfers(API_KEY, ADDRESS, NETWORK)
        filtered, transfers_in, transfers_out = classify_transactions(data, TREASURY, ADDRESS)
        
        # Get daily totals
        daily_totals = get_daily_transfer_totals(data)
        
        tweets_posted = 0
        
        # Find and tweet zero-value incoming transactions (first 3)
        zero_in = []
        for tx in transfers_in:
            amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
            if amount == 0:
                zero_in.append(tx)
            if len(zero_in) >= 3:
                break
        
        # Find and tweet zero-value outgoing transactions (first 3) 
        zero_out = []
        for tx in transfers_out:
            amount = round(int(tx.get('amount', 0)) / 1e9, 4) if tx.get('amount') else 0
            if amount == 0:
                zero_out.append(tx)
            if len(zero_out) >= 3:
                break
        
        # Post tweets for zero-value incoming
        for i, tx in enumerate(zero_in):
            tweet_text = create_transaction_tweet(tx, "in", data, daily_totals)
            if tweet_text:
                post_tweet(tweet_text)
                tweets_posted += 1
                print(f"🐦 Posted zero-value incoming tweet {i+1}")
                await asyncio.sleep(15)  # 15 seconds between tweets to be safe
        
        # Post tweets for zero-value outgoing
        for i, tx in enumerate(zero_out):
            tweet_text = create_transaction_tweet(tx, "out", data, daily_totals)
            if tweet_text:
                post_tweet(tweet_text)
                tweets_posted += 1
                print(f"🐦 Posted zero-value outgoing tweet {i+1}")
                await asyncio.sleep(15)  # 15 seconds between tweets to be safe
        
        return {
            "success": True,
            "message": f"Posted {tweets_posted} zero-value transaction tweets",
            "zero_incoming_found": len(zero_in),
            "zero_outgoing_found": len(zero_out),
            "tweets_posted": tweets_posted
        }
        
    except Exception as e:
        return {"error": f"Failed to post zero-value tweets: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
