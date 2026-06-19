from fastapi import FastAPI, HTTPException
from atproto import Client
from datetime import datetime, timedelta, timezone

app = FastAPI(
    title="Bluesky Disaster Monitoring PoC",
    description="Thesis Phase 1 Data Ingestion Engine: Verified Social Graph Mapping."
)

client = Client()

BLUESKY_HANDLE = "centblsky.bsky.social" 
BLUESKY_PASSWORD = "a6pj-l7z4-i2jm-amza" 

DISASTER_KEYWORDS = [
    "baha", "lindol", "linog", "bagyo", "sunog", 
    "tulong", "tabang", "rescue", "naghahanap ng pagkain", "kailangan ng tubig", 
    "walang kuryente", "nasira ang bahay", "stranded", "willing to donate", "may dalang pagkain", 
    "pwede tumulong", "libreng relief goods", "mayroon kaming gamot", "volunteer", "relief operations"
]

LOCATION_MARKERS = [
    "cebu", "manila", "davao", "iloilo", "bohol", "leyte", "samar", "negros", 
    "benguet", "albay", "cagayan", "pampanga", "bulacan", "cavite", "laguna", 
    "rizal", "batangas", "quezon", "mindoro", "palawan", "zamboanga", "misamis", 
    "surigao", "agata", "cotabato", "lanao", "brgy", "barangay", "sitio", "purok", 
    "kalye", "street", "st.", "ave", "avenue", "city", "provincial", "bayan"
]

@app.on_event("startup")
def authenticate_session():
    try:
        client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
    except Exception as e:
        pass

@app.get("/disaster-alerts")
def get_disaster_posts(search_limit: int = 5, days_back: int = 5):
    """
    Queries Bluesky registries, evaluates geographic references, pulls verified profile metrics,
    and returns accurately mapped relationships to the FastAPI web interface.
    """
    try:
        posts_collection = []
        users_collection = []
        seen_users = set()  
        
        pht_zone = timezone(timedelta(hours=8))
        
        current_time_utc = datetime.now(timezone.utc)
        since_date_boundary = (current_time_utc - timedelta(days=days_back)).date()
        since_date_str = since_date_boundary.isoformat()
        
        for keyword in DISASTER_KEYWORDS:
            optimized_query = f"{keyword} since:{since_date_str}"
            
            search_response = client.app.bsky.feed.search_posts({
                'q': optimized_query,
                'limit': search_limit
            })
            
            if not search_response or not hasattr(search_response, 'posts'):
                continue
                
            for post_view in search_response.posts:
                post_text = post_view.record.text
                
                if keyword in post_text.lower():
                    
                    author_did = post_view.author.did
                    author_handle = post_view.author.handle
                    display_name = getattr(post_view.author, 'display_name', author_handle)
                    
                    created_at_raw = post_view.record.created_at
                    
                    try:
                        clean_timestamp = created_at_raw.replace("Z", "+00:00")
                        if "." in clean_timestamp:
                            base_part, nano_part = clean_timestamp.split(".")
                            clean_timestamp = f"{base_part}.{nano_part[:3]}+00:00"
                            
                        created_dt_utc = datetime.fromisoformat(clean_timestamp)
                        created_dt_pht = created_dt_utc.astimezone(pht_zone)
                        collected_dt_pht = datetime.now(timezone.utc).astimezone(pht_zone)
                        
                        created_at_readable = created_dt_pht.strftime("%Y-%m-%d %I:%M %p")
                        collected_at_readable = collected_dt_pht.strftime("%Y-%m-%d %I:%M %p")
                    except Exception:
                        created_at_readable = created_at_raw
                        collected_at_readable = datetime.now(timezone.utc).astimezone(pht_zone).strftime("%Y-%m-%d %I:%M %p")
                    
                    has_location_clue = any(marker in post_text.lower() for marker in LOCATION_MARKERS)
                    
                    reply_count = getattr(post_view, 'reply_count', 0)
                    repost_count = getattr(post_view, 'repost_count', 0)
                    like_count = getattr(post_view, 'like_count', 0)
                    
                    lang_property = getattr(post_view.record, 'langs', ["fil"])
                    lang_str = lang_property if lang_property else "fil"
                    
                    official_follower_count = 0
                    official_following_count = 0
                    followers_list = []
                    following_list = []
                    mutual_ties = []
                    
                    try:
                        actor_profile = client.app.bsky.actor.get_profile({'actor': author_did})
                        official_follower_count = int(getattr(actor_profile, 'followers_count', 0))
                        official_following_count = int(getattr(actor_profile, 'follows_count', 0))
                    except Exception:
                        pass
                        
                    try:
                        follows_res = client.app.bsky.graph.get_follows({'actor': author_did, 'limit': 10})
                        following_list = [f.did for f in follows_res.follows]
                    except Exception:
                        pass
                        
                    try:
                        followers_res = client.app.bsky.graph.get_followers({'actor': author_did, 'limit': 10})
                        followers_list = [f.did for f in followers_res.followers]
                    except Exception:
                        pass
                        
                    if following_list and followers_list:
                        mutual_ties = list(set(following_list).intersection(set(followers_list)))

                    post_document = {
                        "_id": post_view.uri,
                        "author_did": author_did,
                        "author_handle": author_handle,
                        "text": post_text,
                        "created_at": created_at_readable,      
                        "collected_at": collected_at_readable,  
                        "keyword_matched": [keyword],
                        "lang": lang_str,
                        "reply_count": reply_count,
                        "repost_count": repost_count,
                        "like_count": like_count,
                        "has_location_clue": has_location_clue,  
                        "processed": False,
                        "social_graph": {
                            "follower_count": official_follower_count,   
                            "following_count": official_following_count, 
                            "followers": followers_list,
                            "following": following_list,
                            "mutual_ties": mutual_ties                   
                        }
                    }
                    posts_collection.append(post_document)
                    
                    if author_did not in seen_users:
                        user_document = {
                            "_id": author_did,
                            "handle": author_handle,
                            "display_name": display_name,
                            "follower_count": official_follower_count,
                            "following_count": official_following_count,
                            "mutual_tie_count": len(mutual_ties),
                            "followers": followers_list,
                            "following": following_list,
                            "mutual_ties": mutual_ties,
                            "fetched_at": collected_at_readable
                        }
                        users_collection.append(user_document)
                        seen_users.add(author_did)
                    
        return {
            "status": "success",
            "database_preview": {
                "date_filter_applied_since": since_date_str,
                "posts_collection_count": len(posts_collection),
                "users_collection_count": len(users_collection)
            },
            "posts_collection": posts_collection,
            "users_collection": users_collection
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"API Error: {str(e)}")
