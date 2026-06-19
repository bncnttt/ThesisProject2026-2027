from fastapi import FastAPI, HTTPException
from atproto import Client

# Initialize the FastAPI application
app = FastAPI(
    title="Bluesky Disaster Monitoring PoC",
    description="Authenticated Search System: Dual Terminal & Browser Output."
)

# Initialize the official AT Protocol Client
client = Client()

# 🔑 ASSIGN THESIS CREDENTIALS HERE
# Replace with your actual Bluesky handle and generated App Password
BLUESKY_HANDLE = "centblsky.bsky.social" 
BLUESKY_PASSWORD = "a6pj-l7z4-i2jm-amza" 

# Target keywords established in the thesis filter scope
DISASTER_KEYWORDS = ["baha", "lindol", "bagyo", "sunog", "tulong"]

@app.on_event("startup")
def authenticate_session():
    """
    Executes secure session login on server boot to prevent 
    unauthenticated rate limiting or HTTP 401 exceptions.
    """
    try:
        print("\n🔒 Attempting safe authentication with Bluesky AppView...")
        client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
        print("✅ AUTHENTICATION SUCCESSFUL: Session tokens granted.")
    except Exception as e:
        print(f"❌ AUTHENTICATION CRITICAL ERROR: {e}")

@app.get("/disaster-alerts")
def get_disaster_posts(search_limit: int = 10):
    """
    Queries authenticated index search endpoint, prints target metrics 
    directly to terminal console, and serializes array data to browser.
    """
    try:
        results = []
        
        print("\n" + "="*70)
        print("🚨 WEB API REQUEST RECEIVED: QUERYING LIVE NETWORK REGISTRIES 🚨")
        print("="*70)
        
        for keyword in DISASTER_KEYWORDS:
            # Query the official validated post search lexicon method
            search_response = client.app.bsky.feed.search_posts({
                'q': keyword,
                'limit': search_limit
            })
            
            if not search_response or not hasattr(search_response, 'posts'):
                continue
                
            for post_view in search_response.posts:
                post_text = post_view.record.text
                
                # Verify lowercase pattern mapping accuracy
                if keyword in post_text.lower():
                    author_id = post_view.author.did          # 1. Author Cryptographic ID
                    timestamp = post_view.record.created_at    # 2. Server Timestamp
                    text_content = post_text                  # 3. Post Body Content
                    
                    results.append({
                        "matched_keyword": keyword,
                        "author_id": author_id,
                        "timestamp_utc": timestamp,
                        "text_content": text_content
                    })
                    
                    # DIRECT PRINT TO TERMINAL FIRST
                    print(f"KEYWORD     : {keyword.upper()}")
                    print(f"AUTHOR ID   : {author_id}")
                    print(f"TIMESTAMP    : {timestamp}")
                    print(f"TEXT CONTENT : {text_content}")
                    print("-" * 70)
                    
        print(f"✅ SUCCESS: Formatted {len(results)} matches. Sending to browser...\n")
        
        return {
            "status": "success",
            "total_matches_found": len(results),
            "filtered_data": results
        }

    except Exception as e:
        print(f"❌ TERMINAL RUNTIME EXCEPTION: {e}")
        raise HTTPException(status_code=400, detail=f"API Error: {str(e)}")
