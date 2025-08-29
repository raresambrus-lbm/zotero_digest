# zotero_daily_digest.py
import os
import json
import requests
import datetime
from zoneinfo import ZoneInfo

# ---------- Configuration via environment ----------
API_KEY        = os.environ["ZOTERO_API_KEY"]                # required
LIBRARY_TYPE   = os.environ.get("LIBRARY_TYPE", "groups")      # "users" or "groups"
LIBRARY_ID_ENV = os.environ.get("LIBRARY_ID")                 # optional, numeric
GROUP_NAME     = os.environ.get("GROUP_NAME")                 # optional, pick group by name
LOCAL_TZ       = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Los_Angeles"))
WINDOW_DAYS    = int(os.environ.get("WINDOW_DAYS", "1"))      # e.g., 2 for last 48h
COLLECTION_KEY = os.environ.get("ZOTERO_COLLECTION")          # optional 8-char collection key
DEBUG_FILTER   = os.environ.get("DEBUG_FILTER") == "1"        # show filtering debug info
# Time threshold in minutes to filter out auto-created annotations
AUTO_ANNOTATION_THRESHOLD = int(os.environ.get("AUTO_ANNOTATION_THRESHOLD", "1"))  # 1 minute default
# Optional: override the set of "paper" types (comma-separated)
PAPER_TYPES    = os.environ.get("PAPER_TYPES", "").strip()
# Slack webhook URL for posting digest
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")  # optional

# ---------- Helpers ----------
def _group_name(g):
    # Group name is usually nested under data.name
    return (g.get("data", {}).get("name")
            or g.get("name")
            or "").strip()

def resolve_library():
    """
    Resolve (lib_type, lib_id) using env or discovery.
    - If LIBRARY_ID is set, return it.
    - Otherwise, discover userID from /keys/current.
    - If LIBRARY_TYPE=groups, pick by GROUP_NAME, or the only group if just one.
    """
    lib_type = LIBRARY_TYPE
    lib_id = LIBRARY_ID_ENV

    # Who owns this API key?
    ki = requests.get(
        "https://api.zotero.org/keys/current",
        headers={"Zotero-API-Key": API_KEY},
        timeout=15,
    )
    ki.raise_for_status()
    user_data = ki.json()
    user_id = str(user_data["userID"])

    # Guard: don't pass a userID as a group ID
    if lib_type == "groups" and lib_id and str(lib_id) == user_id:
        raise SystemExit("LIBRARY_ID looks like your userID. For groups, set the group's numeric id or GROUP_NAME.")

    if lib_id:
        # Optional: verify group exists & access when targeting groups
        if lib_type == "groups":
            g = requests.get(f"https://api.zotero.org/groups/{lib_id}",
                             headers={"Zotero-API-Key": API_KEY}, timeout=15)
            if g.status_code == 404:
                raise SystemExit(f"Group {lib_id} not found.")
            if g.status_code == 403:
                raise SystemExit(f"No access to group {lib_id}. Edit your API key permissions on zotero.org.")
            g.raise_for_status()
        return lib_type, str(lib_id)

    # No LIBRARY_ID provided — auto-discover
    if lib_type == "users":
        return "users", user_id

    # lib_type == "groups": list groups and select
    gr = requests.get(
        f"https://api.zotero.org/users/{user_id}/groups",
        headers={"Zotero-API-Key": API_KEY},
        timeout=15,
    )
    gr.raise_for_status()
    groups_raw = gr.json()
    groups = [{"id": str(g.get("id") or g.get("data", {}).get("id")), "name": _group_name(g)} for g in groups_raw]

    if GROUP_NAME:
        for g in groups:
            if g["name"].lower() == GROUP_NAME.lower():
                return "groups", g["id"]
        raise SystemExit(
            f'GROUP_NAME="{GROUP_NAME}" not found. '
            "Available: " + ", ".join(f'{g["name"]}={g["id"]}' for g in groups)
        )

    if len(groups) == 1:
        return "groups", groups[0]["id"]

    if not groups:
        raise SystemExit("No groups available to this API key.")
    raise SystemExit(
        "Multiple groups found. Set LIBRARY_ID or GROUP_NAME. Choices: "
        + ", ".join(f'{g["name"]}={g["id"]}' for g in groups)
    )

# Get current user info and library details
ki = requests.get(
    "https://api.zotero.org/keys/current",
    headers={"Zotero-API-Key": API_KEY},
    timeout=15,
)
ki.raise_for_status()
CURRENT_USER_ID = str(ki.json()["userID"])

LIBRARY_TYPE, LIBRARY_ID = resolve_library()
STATE_PATH = os.environ.get("STATE_PATH", f"state_{LIBRARY_TYPE}_{LIBRARY_ID}.json")

BASE = f"https://api.zotero.org/{LIBRARY_TYPE}/{LIBRARY_ID}"
HEADERS = {"Zotero-API-Version": "3", "Zotero-API-Key": API_KEY}

print(f"Using Zotero library: {LIBRARY_TYPE}/{LIBRARY_ID}"
      + (f" (collection={COLLECTION_KEY})" if COLLECTION_KEY else "")
      + f" | window={WINDOW_DAYS}d")

# Which itemTypes count as "papers"
if PAPER_TYPES:
    BIBLIO_TYPES = {t.strip() for t in PAPER_TYPES.split(",") if t.strip()}
else:
    BIBLIO_TYPES = {
        "journalArticle", "conferencePaper", "preprint", "report",
        "book", "bookSection", "thesis", "manuscript", "blogPost"
    }

def now_window(days=1):
    end = datetime.datetime.now(tz=LOCAL_TZ)
    
    # Smart weekend logic: on Monday, check since Friday (3 days)
    if days == 1:  # Only apply weekend logic for default 1-day window
        current_weekday = end.weekday()  # Monday=0, Sunday=6
        if current_weekday == 0:  # Monday
            # Check since Friday (3 days ago)
            days = 3
            if DEBUG_FILTER:
                print(f"Debug: Monday detected - extending window to {days} days (since Friday)")
    
    start = end - datetime.timedelta(days=days)
    return start, end

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_version": 0}

def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)

def iso_to_dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))

def get_items(params, extra_headers=None):
    h = HEADERS.copy()
    if extra_headers:
        h.update(extra_headers)
    r = requests.get(f"{BASE}/items", params=params, headers=h, timeout=30)
    r.raise_for_status()
    return r

def get_item(key):
    r = requests.get(f"{BASE}/items/{key}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def zlink(it):
    return (it.get("links", {}).get("alternate", {}).get("href")
            or it.get("links", {}).get("self", {}).get("href")
            or "")

def title_for(it):
    d = it["data"]
    if d.get("title"):
        return d["title"]
    if d.get("note"):
        return d["note"].splitlines()[0][:80]
    return "(untitled)"

def digest(days=1):
    state = load_state()
    start_dt, end_dt = now_window(days)

    # Build base params — keep it simple and valid
    base_params = {"format": "json"}
    if COLLECTION_KEY:
        base_params["collection"] = COLLECTION_KEY

    # Always fetch the 100 most recently modified items
    r = get_items({**base_params, "sort": "dateModified", "direction": "desc", "limit": 100})

    changed = r.json()
    
    # Debug: show what we got from API
    if DEBUG_FILTER:
        print(f"Debug: API returned {len(changed)} items")
        if changed:
            item_types = {}
            for item in changed:
                item_type = item["data"]["itemType"]
                item_types[item_type] = item_types.get(item_type, 0) + 1
            print(f"Debug: Item types: {item_types}")
    
    # Track library version for next run (if present)
    lm = r.headers.get("Last-Modified-Version")
    if lm:
        try:
            state["last_version"] = max(int(lm), int(state.get("last_version", 0)))
        except (TypeError, ValueError):
            pass

    # Partition by type
    notes       = [it for it in changed if it["data"]["itemType"] == "note"]
    annotations = [it for it in changed if it["data"]["itemType"] == "annotation"]
    biblio      = [it for it in changed if it["data"]["itemType"] in BIBLIO_TYPES]

    # Filter by dateAdded inside the window
    def in_window(it):
        try:
            return start_dt <= iso_to_dt(it["data"]["dateAdded"]) <= end_dt
        except Exception:
            return False

    # Filter items (notes/annotations) to show meaningful activity from ALL group members (including current user)
    # Exclude only items created within 1 minute of paper upload (likely auto-generated)
    def is_meaningful_item(it):
        if LIBRARY_TYPE != "groups":
            return True  # For user libraries, show all items
        
        meta = it.get("meta", {})
        created_by_obj = meta.get("createdByUser", {})
        
        # Extract user ID from createdByUser object
        if isinstance(created_by_obj, dict):
            created_by_id = str(created_by_obj.get("id", ""))
        else:
            created_by_id = str(created_by_obj)
            
        # Must be created by someone (has createdByUser)
        if not created_by_id:
            return False
            
        # Check if this annotation was created shortly after its parent paper (likely auto-generated)
        try:
            parent_key = it["data"].get("parentItem")
            if parent_key:
                parent = get_item(parent_key)
                # If parent is attachment, get the actual paper
                if parent["data"]["itemType"] == "attachment":
                    grand_key = parent["data"].get("parentItem")
                    if grand_key:
                        paper = get_item(grand_key)
                    else:
                        paper = parent
                else:
                    paper = parent
                
                # Compare annotation creation time with paper creation time
                annotation_time = iso_to_dt(it["data"]["dateAdded"])
                paper_time = iso_to_dt(paper["data"]["dateAdded"])
                time_diff = (annotation_time - paper_time).total_seconds() / 60  # minutes
                
                is_not_auto = time_diff > AUTO_ANNOTATION_THRESHOLD
                
                if DEBUG_FILTER:
                    title = title_for(it)[:50]
                    paper_title = title_for(paper)[:30]
                    item_type = it["data"]["itemType"]
                    username = created_by_obj.get('username', created_by_id) if isinstance(created_by_obj, dict) else created_by_id
                    print(f"Debug: {item_type.capitalize()} '{title}' on '{paper_title}'")
                    print(f"  - createdBy: {username} ({created_by_id})")
                    print(f"  - time_diff: {time_diff:.1f}min, threshold: {AUTO_ANNOTATION_THRESHOLD}min")
                    print(f"  - include: {is_not_auto}")
                
                return is_not_auto
        except Exception as e:
            if DEBUG_FILTER:
                print(f"Debug: Error checking annotation timing: {e}")
            # If we can't determine timing, default to including group member annotations
            return True
        
        return True

    new_papers = [it for it in biblio if in_window(it)]
    # Filter notes and annotations by timing only (include all group members including current user)
    new_notes  = [it for it in notes if in_window(it) and is_meaningful_item(it)]
    new_annots = [it for it in annotations if in_window(it) and is_meaningful_item(it)]
    
    # Debug: show filtering results
    if DEBUG_FILTER:
        print(f"Debug: Before filtering - papers: {len(biblio)}, notes: {len(notes)}, annotations: {len(annotations)}")
        notes_after_time = [it for it in notes if in_window(it)]
        print(f"Debug: After time window filter - papers: {len(new_papers)}, notes: {len(notes_after_time)}, annotations: {len([it for it in annotations if in_window(it)])}")
        print(f"Debug: After timing filter (1min threshold) - notes: {len(new_notes)}, annotations: {len(new_annots)}")
        print(f"Debug: Time window: {start_dt} to {end_dt}")
        if annotations:
            print(f"Debug: Sample annotation dates:")
            for ann in annotations[:3]:
                date_added = ann["data"].get("dateAdded", "N/A")
                print(f"  - {title_for(ann)[:30]} - dateAdded: {date_added}")

    # Map notes/annotations back to top-level bibliographic parent
    def paper_for_child(child):
        parent_key = child["data"].get("parentItem")
        if not parent_key:
            return None
        parent = get_item(parent_key)
        # If the parent is an attachment (e.g., PDF), walk up one more level
        if parent["data"]["itemType"] == "attachment":
            grand = parent["data"].get("parentItem")
            return get_item(grand) if grand else None
        return parent

    parents = {}
    # Also include all notes/annotations (filtered by timing only) for "read papers" section
    all_meaningful_notes = [it for it in notes if is_meaningful_item(it)]
    all_meaningful_annotations = [it for it in annotations if is_meaningful_item(it)]
    
    for ch in (all_meaningful_notes + all_meaningful_annotations):
        try:
            p = paper_for_child(ch)
            if p and p["data"]["itemType"] in BIBLIO_TYPES:
                if DEBUG_FILTER:
                    ch_type = ch["data"]["itemType"]
                    ch_title = title_for(ch)[:30]
                    p_title = title_for(p)[:30]
                    print(f"Debug: {ch_type} '{ch_title}' linked to paper '{p_title}'")
                parents[p["key"]] = p
        except requests.RequestException:
            # Skip any lookup errors and keep going
            continue

    read_papers = list(parents.values())

    return {"new_papers": new_papers, "notes": new_notes, "read_papers": read_papers}, state

def print_digest(summary, days=1):
    start_dt, end_dt = now_window(days)
    actual_days = (end_dt - start_dt).days
    group_note = ""
    
    # Show actual window used (may be different from requested days due to weekend logic)
    if actual_days != days and days == 1:
        day_desc = f"last {actual_days} days (weekend extended)"
    else:
        day_desc = f"last {actual_days} day{'s' if actual_days != 1 else ''}"
    
    print(f"\nZotero daily digest — {start_dt.strftime('%b %d, %Y')} ({day_desc}){group_note}\n")

    def section(name, items):
        print(f"{name} ({len(items)})")
        if not items:
            print("  • None")
        else:
            for it in items[:20]:
                print(f"  • {title_for(it)}")
                ln = zlink(it)
                if ln:
                    print(f"    {ln}")
        print()

    section("New papers added", summary["new_papers"])
    section("Papers read (notes/annotations by all group members)", summary["read_papers"])
    # section("Notes added", summary["notes"])  # Keep functionality but don't print

def send_to_slack(summary, days=1):
    if not SLACK_WEBHOOK_URL:
        return
    
    start_dt, end_dt = now_window(days)
    actual_days = (end_dt - start_dt).days
    
    # Show actual window used (may be different from requested days due to weekend logic)
    if actual_days != days and days == 1:
        day_desc = f"last {actual_days} days (weekend extended)"
    else:
        day_desc = f"last {actual_days} day{'s' if actual_days != 1 else ''}"
    
    # Format message for Slack
    new_papers = summary["new_papers"]
    read_papers = summary["read_papers"]
    
    # Build Slack message
    text = f"*Zotero Daily Digest — {start_dt.strftime('%b %d, %Y')} ({day_desc})*\n\n"
    
    # New papers section
    text += f"*📚 New papers added ({len(new_papers)})*\n"
    if not new_papers:
        text += "• None\n"
    else:
        for paper in new_papers[:20]:  # Limit to avoid message length issues
            title = title_for(paper)
            link = zlink(paper)
            if link:
                text += f"• <{link}|{title}>\n"
            else:
                text += f"• {title}\n"
    
    text += "\n"
    
    # Read papers section
    text += f"*📖 Papers read (notes/annotations by all group members) ({len(read_papers)})*\n"
    if not read_papers:
        text += "• None\n"
    else:
        for paper in read_papers[:20]:  # Limit to avoid message length issues
            title = title_for(paper)
            link = zlink(paper)
            if link:
                text += f"• <{link}|{title}>\n"
            else:
                text += f"• {title}\n"
    
    # Send to Slack
    payload = {"text": text}
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        print("✓ Sent digest to Slack")
    except requests.RequestException as e:
        print(f"✗ Failed to send to Slack: {e}")

if __name__ == "__main__":
    # Skip execution on weekends (Saturday=5, Sunday=6) unless explicitly overridden
    current_weekday = datetime.datetime.now(tz=LOCAL_TZ).weekday()
    skip_weekends = os.environ.get("SKIP_WEEKENDS", "1") == "1"  # Default: skip weekends
    
    if skip_weekends and current_weekday in [5, 6]:  # Saturday or Sunday
        weekday_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][current_weekday]
        print(f"Weekend ({weekday_name}) - no digest generated. Run again on Monday for weekend summary.")
        print("To override: SKIP_WEEKENDS=0 python3 zotero_app_v3.py")
    else:
        try:
            summary, state = digest(days=WINDOW_DAYS)
            print_digest(summary, days=WINDOW_DAYS)
            send_to_slack(summary, days=WINDOW_DAYS)
            save_state(state)
        except requests.RequestException as e:
            print(f"Network error: {e}")
            raise

