from fastapi import FastAPI, HTTPException
from atproto import Client
from datetime import datetime, timedelta, timezone
import re

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
    "cebu", "manila", "davao", "iloilo", "bohol", "leyte","negros", 
    "benguet", "albay", "cagayan", "pampanga", "bulacan", "cavite", "West Kelowna", 
    "rizal", "batangas", "quezon", "mindanao", "palawan", "zamboanga", "misamis", 
    "surigao", "agata", "cotabato", "lanao", "brgy", "barangay", "sitio", "purok", 
    "kalye", "street", "st.", "ave", "avenue", "city", "provincial", "bayan" , "sarangani"
]

GRAPH_PAGE_LIMIT = 50
DEFAULT_GRAPH_MEMBER_LIMIT = -1
AUTHOR_FEED_PAGE_LIMIT = 50


def get_attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def has_location_marker(text):
    normalized_text = text.lower()
    return any(
        re.search(rf"(?<!\w){re.escape(marker.lower())}(?!\w)", normalized_text)
        for marker in LOCATION_MARKERS
    )


def get_author_live_feed_posts(actor, max_posts):
    posts = []
    cursor = None

    while len(posts) < max_posts:
        params = {
            'actor': actor,
            'filter': 'posts_no_replies',
            'limit': min(AUTHOR_FEED_PAGE_LIMIT, max_posts - len(posts))
        }
        if cursor:
            params['cursor'] = cursor

        response = client.app.bsky.feed.get_author_feed(params)
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

    return posts


def collect_graph_members(fetch_method, actor, collection_name, max_members=DEFAULT_GRAPH_MEMBER_LIMIT):
    members = []
    cursor = None

    while True:
        params = {'actor': actor, 'limit': GRAPH_PAGE_LIMIT}
        if cursor:
            params['cursor'] = cursor

        response = fetch_method(params)
        page_members = get_attr(response, collection_name, []) or []

        for member in page_members:
            member_did = get_attr(member, 'did')
            member_handle = get_attr(member, 'handle')
            if member_did:
                members.append(member_did)
            elif member_handle:
                members.append(member_handle)

            if max_members is not None and len(members) >= max_members:
                return members

        cursor = get_attr(response, 'cursor')
        if not cursor or not page_members:
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

        try:
            actor_members = collect_graph_members(fetch_method, actor, collection_name, max_members)
        except Exception:
            continue

        for member in actor_members:
            if member not in seen_members:
                members.append(member)
                seen_members.add(member)

            if max_members is not None and len(members) >= max_members:
                return members

    return members

@app.on_event("startup")
def authenticate_session():
    try:
        client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
    except Exception as e:
        pass

@app.get("/disaster-alerts")
def get_disaster_posts(search_limit: int = 5, days_back: int = 5, graph_limit: int = DEFAULT_GRAPH_MEMBER_LIMIT):
    try:
        posts_collection = []
        users_collection = []
        seen_users = set()  
        seen_posts = set()
        graph_cache = {}
        
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
                
                    if not record or not post_text or keyword not in post_text.lower():
                        continue

                    seen_posts.add(post_uri)
                    
                    author = get_attr(post_view, 'author')
                    author_did = get_attr(author, 'did')
                    author_handle = get_attr(author, 'handle')
                    display_name = get_attr(author, 'display_name', author_handle)
                    
                    created_at_raw = get_attr(record, 'created_at')
                    
                    try:
                        clean_timestamp = created_at_raw.replace("Z", "+00:00")
                        if "." in clean_timestamp:
                            base_part, nano_part = clean_timestamp.split(".")
                            clean_timestamp = f"{base_part}.{nano_part[:3]}+00:00"
                            
                        created_dt_utc = datetime.fromisoformat(clean_timestamp)
                        collected_dt_utc = datetime.now(timezone.utc)

                        created_at_value = created_dt_utc.isoformat().replace("+00:00", "Z")
                        collected_at_value = collected_dt_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    except Exception:
                        created_at_value = created_at_raw
                        collected_at_value = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    
                    has_location_clue = has_location_marker(post_text)
                    
                    reply_count = get_attr(post_view, 'reply_count', 0)
                    repost_count = get_attr(post_view, 'repost_count', 0)
                    like_count = get_attr(post_view, 'like_count', 0)
                    
                    lang_property = get_attr(record, 'langs', ["fil"])
                    lang_str = lang_property[0] if isinstance(lang_property, list) and lang_property else lang_property or "fil"
                    
                    official_follower_count = 0
                    official_following_count = 0

                    if author_did in graph_cache:
                        graph_data = graph_cache[author_did]
                    else:
                        followers_list = []
                        following_list = []
                        mutual_ties = []

                        try:
                            actor_profile = client.app.bsky.actor.get_profile({'actor': author_did})
                            official_follower_count = int(get_attr(actor_profile, 'followers_count', 0))
                            official_following_count = int(get_attr(actor_profile, 'follows_count', 0))
                        except Exception:
                            pass

                        graph_member_limit = None if graph_limit < 0 else max(0, min(graph_limit, 500))

                        if graph_member_limit is None or graph_member_limit > 0:
                            try:
                                following_list = collect_graph_members_with_fallback(
                                    client.app.bsky.graph.get_follows,
                                    author_did,
                                    author_handle,
                                    'follows',
                                    graph_member_limit
                                )
                            except Exception:
                                pass

                            try:
                                followers_list = collect_graph_members_with_fallback(
                                    client.app.bsky.graph.get_followers,
                                    author_did,
                                    author_handle,
                                    'followers',
                                    graph_member_limit
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
                        "_id": get_attr(post_view, 'uri'),
                        "author_did": author_did,
                        "author_handle": author_handle,
                        "text": post_text,
                        "created_at": created_at_value,
                        "collected_at": collected_at_value,
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
                            "fetched_at": collected_at_value
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
