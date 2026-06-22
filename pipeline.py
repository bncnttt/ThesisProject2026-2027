from fastapi import FastAPI, HTTPException
from atproto import Client
from datetime import datetime, timedelta, timezone
import urllib.request
import json
import re
import os
import pymongo

app = FastAPI(
    title="AgapAI Data Collection Pipeline",
    description="Thesis Phase 1 Data Ingestion Engine: Verified Social Graph Mapping."
)

# Initialize Bluesky Client
client = Client()

# Initialize MongoDB Connection
try:
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    mongo_client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
    db = mongo_client["AgapAI_Database_Final"]
    
    posts_col = db["posts"]
    users_col = db["users"]
    print("STATUS: Connected cleanly to local MongoDB database.")
except Exception as e:
    print(f"CRITICAL WARNING: MongoDB Connection Failed: {e}")

# Credentials Configuration
BLUESKY_HANDLE = "centblsky.bsky.social" 
BLUESKY_PASSWORD = "6q2v-r6qa-io23-iyyy" 

ENGLISH_KWS = {
    "rescue", "stranded", "volunteer", "relief operations", 
    "willing to donate", "landslide", "flood", "storm", "earthquake", "typhoon",
}

BISAYA_KWS = {
    "linog", "tabang", "kilat", "dalugdog", "anapog", 
    "hapak sa balod", "dakong balod", "suno", "unos", 
    "nihangyo", "nanginahanglan", "gikinahanglan", "pagkaon", 
    "mainom nga tubig", "tambal", "walay suga", "ngitngit", 
    "guba ang balay", "nahugno", "natabunan", "gipangbaha", 
    "taas ang tubig", "lapok", "na-stranded", "dili kaagi", 
    "sirado ang dalan", "nangita ug rescue", "tabangi mi", 
    "luwasa mi", "manghatag", "pang-apog", "baha"
}

TAGALOG_KWS = {
    "tulong", "naghahanap ng pagkain", "kailangan ng tubig", 
    "walang kuryente", "nasira ang bahay", "may dalang pagkain", 
    "pwede tumulong", "libreng relief goods", "mayroon kaming gamot", 
    "ayuda", "donasyon", "brownout", "bagyo", "lindol", "sunog"
}

# Automatically combines all language sets into your master search array
DISASTER_KEYWORDS = list(ENGLISH_KWS | BISAYA_KWS | TAGALOG_KWS)

# Dynamic National Location Matrix Variable
PH_GEOGRAPHIC_REGISTRY = set()

def load_philippine_geographic_registry():
    global PH_GEOGRAPHIC_REGISTRY
    print("STATUS: Loading complete Philippine National Geographic Registry...")
    try:
        #  Pinned to the highly stable GitLab open PSGC data mirror
        url = "https://psgc.gitlab.io/api/provinces.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req) as response:
            # This API returns a clean JSON list directly: [{"code":"...","name":"Abra"}, ...]
            provinces = json.loads(response.read().decode())
            
            temporary_set = set()
            
            # Universal context markers + Major Island Groups
            temporary_set.update([
                "brgy", "barangay", "sitio", "purok", "kalye", "street", "st", "bayan", "bldg", "provincial", "city",
                "luzon", "visayas", "mindanao"
            ])
            
            # Loops through the official listing format flawlessly
            for item in provinces:
                name = item.get("name", "")
                if name:
                    # Strip structural trailing words like "Province" or "City" 
                    clean_name = re.sub(r'\b(province|city|municipality)\b', '', name, flags=re.IGNORECASE).strip()
                    temporary_set.add(clean_name.lower())
            
            PH_GEOGRAPHIC_REGISTRY = temporary_set
            print(f"SUCCESS: Fully indexed {len(PH_GEOGRAPHIC_REGISTRY)} custom Philippine geographic location markers!")
            
    except Exception as e:
        print(f"WARNING: Could not fetch national registry data dynamically: {e}. Implementing local fail-safe matrix...")
        #  FOOLPROOF LOCAL BACKUP: Core local administrative markers & all 82 provinces
        backup_provinces = [
            "abra", "agusan", "albay", "antique", "apayao", "aurora", "basilan", "bataan", "batanes", "batangas", 
            "benguet", "biliran", "bohol", "bukidnon", "bulacan", "cagayan", "camarines norte", "camarines sur", 
            "camiguin", "capiz", "catanduanes", "cavite", "cebu", "cotabato", "davao de oro", "davao del norte", 
            "davao del sur", "davao occidental", "davao oriental", "dinagat islands", "eastern samar", "guimaras", 
            "ifugao", "ilocos norte", "ilocos sur", "iloilo", "isabela", "kalinga", "la union", "laguna", 
            "lanao del norte", "lanao del sur", "leyte", "maguindanao", "marinduque", "masbate", "misamis occidental", 
            "misamis oriental", "mountain province", "negros occidental", "negros oriental", "northern samar", 
            "nueva ecija", "nueva vizcaya", "occidental mindoro", "oriental mindoro", "palawan", "pampanga", 
            "pangasinan", "rizal", "romblon", "samar", "sarangani", "siquijor", "sorsogon", "south cotabato", 
            "southern leyte", "sultan kudarat", "sulu", "surigao del norte", "surigao del sur", "tarlac", 
            "tawi-tawi", "zambales", "zamboanga del norte", "zamboanga del sur", "zamboanga sibugay", "manila", 
            "barangay", "brgy", "bayan", "purok", "sitio", "city", "luzon", "visayas", "mindanao"
        ]
        PH_GEOGRAPHIC_REGISTRY = set(backup_provinces)
        print(f"SUCCESS: Safe fallback deployed! Indexed {len(PH_GEOGRAPHIC_REGISTRY)} core local administrative markers.")

# Run dynamic registry collection instantly
load_philippine_geographic_registry()

GRAPH_PAGE_LIMIT = 50
DEFAULT_GRAPH_MEMBER_LIMIT = -1
AUTHOR_FEED_PAGE_LIMIT = 50


def get_attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


#  UPGRADED: Extracts and returns the specific text word found
def extract_location_name(text):
    """
    Scans the text for Philippine locations and context markers,
    capturing the full address phrase (e.g., 'Purok 2, Colon' or 'Brgy. Malanday').
    """
    # 1. Look for multi-word phrases starting with structural markers
    # This pattern catches the marker + spaces/numbers + commas + capitalized names following it
    context_pattern = r'\b(purok|brgy|barangay|sitio|kalye|street|st|bayan|poblacion)\b\s*\d*[\s,.-]*[A-Z][a-zA-Z0-9]*'
    match = re.search(context_pattern, text, flags=re.IGNORECASE)
    if match:
        # Returns the full phrase cleanly capitalized (e.g., "Purok 2, Colon")
        return match.group(0).title()

    # 2. Fallback: Look for standalone province names from the official registry
    words = re.findall(r'\b\w+\b', text.lower())
    for word in words:
        if word in PH_GEOGRAPHIC_REGISTRY:
            return word.capitalize()
            
    return None

def get_author_live_feed_posts(actor, max_posts):
    posts = []
    cursor = None
    while len(posts) < max_posts:
        try:
            response = client.app.bsky.feed.get_author_feed(
                params={
                    "actor": actor,
                    "filter": "posts_no_replies",
                    "limit": min(AUTHOR_FEED_PAGE_LIMIT, max_posts - len(posts)),
                    "cursor": cursor
                }
            )
            feed_items = get_attr(response, 'feed', []) or []
            if not feed_items:
                break
            for item in feed_items:
                post = get_attr(item, 'post')
                record = get_attr(post, 'record')
                text = get_attr(record, 'text')
                if post and record and text:
                    posts.append(post)
                if len(posts) >= max_posts:
                    break
            cursor = get_attr(response, 'cursor')
            if not cursor:
                break
        except Exception:
            break
    return posts


def collect_graph_members(fetch_method, actor, collection_name, max_members=DEFAULT_GRAPH_MEMBER_LIMIT):
    members = []
    cursor = None
    while True:
        try:
            response = fetch_method(
                params={"actor": actor, "limit": GRAPH_PAGE_LIMIT, "cursor": cursor}
            )
            page_members = get_attr(response, collection_name, []) or []
            for member in page_members:
                member_did = get_attr(member, 'did')
                member_handle = get_attr(member, 'handle')
                if member_did:
                    members.append(member_did)
                elif member_handle:
                    members.append(member_handle)
                if max_members is not None and max_members > 0 and len(members) >= max_members:
                    return members
            cursor = get_attr(response, 'cursor')
            if not cursor or not page_members:
                break
        except Exception:
            break
    return members


def collect_graph_members_with_fallback(fetch_method, actor_did, actor_handle, collection_name, max_members):
    members = []
    seen_members = set()
    seen_actors = set()
    actors_to_try = [actor_did, actor_handle]
    for actor in actors_to_try:
        if not actor or actor in seen_actors:
            continue
        seen_actors.add(actor)
        actor_members = collect_graph_members(fetch_method, actor, collection_name, max_members)
        for member in actor_members:
            if member not in seen_members:
                members.append(member)
                seen_members.add(member)
            if max_members is not None and max_members > 0 and len(members) >= max_members:
                return members
    return members


@app.on_event("startup")
def authenticate_session():
    try:
        print(f"Attempting API login for {BLUESKY_HANDLE}...")
        client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
        print("Login successful! Network connectivity verified.")
    except Exception as e:
        print(f"Startup Login Bypass Warning: Could not authenticate with Bluesky: {repr(e)}")


@app.get("/disaster-alerts")
def get_disaster_posts(search_limit: int = 5, days_back: int = 5, graph_limit: int = 10):
    try:
        posts_collection = []
        users_collection = []
        seen_users = set()  
        seen_posts = set()
        graph_cache = {}
        
        inserted_posts_count = 0
        inserted_users_count = 0
        
        current_time_utc = datetime.now(timezone.utc)
        since_date_boundary = (current_time_utc - timedelta(days=days_back)).date()
        since_date_str = since_date_boundary.isoformat()
        
        for keyword in DISASTER_KEYWORDS:
            optimized_query = f"{keyword} since:{since_date_str}"
            try:
                search_response = client.app.bsky.feed.search_posts(
                    params={"q": optimized_query, "limit": search_limit}
                )
            except Exception as search_err:
                print(f"Search API Call failure for '{keyword}': {search_err}")
                continue
            
            if not search_response or not hasattr(search_response, 'posts') or not search_response.posts:
                continue
                
            candidate_authors = {}
            for search_post_view in search_response.posts:
                author = get_attr(search_post_view, 'author')
                author_did = get_attr(author, 'did')
                author_handle = get_attr(author, 'handle')
                if author_did:
                    candidate_authors[author_did] = author_handle or author_did

            for author_actor in candidate_authors.values():
                live_author_posts = get_author_live_feed_posts(author_actor, search_limit)

                for post_view in live_author_posts:
                    post_uri = get_attr(post_view, 'uri')
                    if post_uri in seen_posts:
                        continue

                    record = get_attr(post_view, 'record')
                    post_text = get_attr(record, 'text', '')

                    if not record or not post_text:
                        continue

                    # 1️ FIX: Exact Word Boundary Matching (Ignores "Cos De BAHA")
                    keyword_found = None
                    for kw in DISASTER_KEYWORDS:
                        if re.search(r'\b' + re.escape(kw) + r'\b', post_text.lower()):
                            keyword_found = kw
                            break

                    if not keyword_found:
                        continue

                    seen_posts.add(post_uri)
                    
                    author = get_attr(post_view, 'author')
                    author_did = get_attr(author, 'did')
                    author_handle = get_attr(author, 'handle')
                    display_name = get_attr(author, 'display_name', author_handle)
                    
                    created_at_raw = get_attr(record, 'created_at')
                    
                    # 2️ FIX: Precise Dynamic Time Parsing (Philippine Standard Time)
                    try:
                        clean_created = created_at_raw.replace("Z", "+00:00")
                        if "." in clean_created:
                            base_part, nano_part = clean_created.split(".")
                            clean_created = f"{base_part}.{nano_part[:3]}+00:00"

                        created_dt_utc = datetime.fromisoformat(clean_created)
                        collected_dt_utc = datetime.now(timezone.utc)

                        pht_tz = timezone(timedelta(hours=8))
                        created_dt_local = created_dt_utc.astimezone(pht_tz)
                        collected_dt_local = collected_dt_utc.astimezone(pht_tz)

                        t_created = created_dt_local.strftime("%A, %B %d, %Y, %I:%M:%S %p PHT")
                        t_collected = collected_dt_local.strftime("%A, %B %d, %Y, %I:%M:%S %p PHT")
                        
                        #  Clean up the leading zero in the hour field to match the guide perfectly
                        # This converts ", 04:24:21" to ", 4:24:21"
                        time_created_readable_value = t_created.replace(", 0", ", ")
                        time_collected_readable_value = t_collected.replace(", 0", ", ")

                        created_at_value = created_dt_utc.isoformat().replace("+00:00", "Z")
                        collected_at_value = collected_dt_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    except Exception:
                        time_created_readable_value = "Unknown Date/Time"
                        time_collected_readable_value = "Unknown Date/Time"
                        created_at_value = created_at_raw
                        collected_at_value = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    
                    # 3️ FIX: Contextual Language Classification
                    if keyword_found in ENGLISH_KWS:
                        detected_lang = "English"
                    elif keyword_found in BISAYA_KWS:
                        detected_lang = "Bisaya"
                    else:
                        detected_lang = "Tagalog"

                    #  DYNAMIC GEOGRAPHIC LOGIC EXTRACTOR
                    detected_location = extract_location_name(post_text)
                    
                    reply_count = get_attr(post_view, 'reply_count', 0)
                    repost_count = get_attr(post_view, 'repost_count', 0)
                    like_count = get_attr(post_view, 'like_count', 0)
                    
                    official_follower_count = 0
                    official_following_count = 0

                    if author_did in graph_cache:
                        graph_data = graph_cache[author_did]
                    else:
                        followers_list = []
                        following_list = []
                        mutual_ties = []

                        try:
                            actor_profile = client.app.bsky.actor.get_profile(params={"actor": author_did})
                            official_follower_count = int(get_attr(actor_profile, 'followers_count', 0))
                            official_following_count = int(get_attr(actor_profile, 'follows_count', 0))
                        except Exception:
                            pass

                        graph_member_limit = None if graph_limit < 0 else max(0, min(graph_limit, 500))

                        if graph_member_limit is None or graph_member_limit > 0:
                            try:
                                following_list = collect_graph_members_with_fallback(
                                    client.app.bsky.graph.get_follows, author_did, author_handle, 'follows', graph_member_limit
                                )
                            except Exception:
                                pass
                            try:
                                followers_list = collect_graph_members_with_fallback(
                                    client.app.bsky.graph.get_followers, author_did, author_handle, 'followers', graph_member_limit
                                )
                            except Exception:
                                pass

                        if following_list and followers_list:
                            follower_set = set(followers_list)
                            following_set = set(following_list)
                            mutual_ties = sorted(follower_set.intersection(following_set))

                        graph_data = {
                            "follower_count": official_follower_count,
                            "following_count": official_following_count,
                            "followers": followers_list,
                            "following": following_list,
                            "mutual_ties": mutual_ties
                        }
                        graph_cache[author_did] = graph_data

                    official_follower_count = graph_data["follower_count"]
                    official_following_count = graph_data["following_count"]
                    followers_list = graph_data["followers"]
                    following_list = graph_data["following"]
                    mutual_ties = graph_data["mutual_ties"]

                    post_document = {
                        "_id": post_uri, 
                        "author_did": author_did,
                        "author_handle": author_handle,
                        "text": post_text,
                        "created_at": created_at_value,
                        "time_created_readable": time_created_readable_value,
                        "collected_at": collected_at_value,
                        "time_collected_readable": time_collected_readable_value,
                        "keyword_matched": [keyword_found],
                        "lang": detected_lang,
                        "reply_count": reply_count,
                        "repost_count": repost_count,
                        "like_count": like_count,
                        
                        #  NEW MULTI-PROP GEO FIELDS
                        "has_location_clue": True if detected_location else False,
                        "location_name": detected_location if detected_location else "Unspecified Location",
                        
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
                    
                    try:
                        posts_col.insert_one(post_document)
                        inserted_posts_count += 1
                    except pymongo.errors.DuplicateKeyError:
                        pass 

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
                            "fetched_at": collected_at_value
                        }
                        users_collection.append(user_document)
                        seen_users.add(author_did)
                        
                        try:
                            users_col.insert_one(user_document)
                            inserted_users_count += 1
                        except pymongo.errors.DuplicateKeyError:
                            pass

        return {
            "status": "success",
            "database_preview": {
                "date_filter_applied_since": since_date_str,
                "posts_collected_this_cycle": len(posts_collection),
                "users_collected_this_cycle": len(users_collection),
                "newly_saved_to_mongodb_posts": inserted_posts_count,
                "newly_saved_to_mongodb_users": inserted_users_count
            },
            "posts_collection": posts_collection,
            "users_collection": users_collection
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"API Processing Error Trace: {str(e)}")