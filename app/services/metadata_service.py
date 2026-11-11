import re
import requests
from pathlib import Path
from flask import current_app

def clean_isbn(raw_isbn: str) -> str:
    """Strip hyphens, spaces, and normalize ISBN string."""
    if not raw_isbn:
        return ""
    # Keep digits and 'X'/'x'
    cleaned = re.sub(r'[^0-9Xx]', '', raw_isbn.strip()).upper()
    return cleaned

def fetch_book_metadata(isbn: str) -> dict:
    """
    Lookup book metadata using Open Library and Google Books API.
    Downloads cover image to local static/covers/ directory.
    """
    clean = clean_isbn(isbn)
    if not clean:
        return {"error": "Invalid ISBN"}

    title = None
    authors = None
    description = None
    publisher = None
    publish_year = None
    cover_url = None

    # 1. Try Open Library direct endpoint
    try:
        url = f"https://openlibrary.org/isbn/{clean}.json"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title")
            publish_year = data.get("publish_date")
            if data.get("publishers"):
                publisher = ", ".join(data.get("publishers"))
            
            # Covers
            covers = data.get("covers")
            if covers and len(covers) > 0 and covers[0] > 0:
                cover_url = f"https://covers.openlibrary.org/b/id/{covers[0]}-M.jpg"
            else:
                cover_url = f"https://covers.openlibrary.org/b/isbn/{clean}-M.jpg"

            # Check description
            desc_field = data.get("description")
            if isinstance(desc_field, dict):
                description = desc_field.get("value")
            elif isinstance(desc_field, str):
                description = desc_field
    except Exception as e:
        pass

    # 2. Try Open Library Search endpoint to resolve authors or fill in missing fields
    if not title or not authors:
        try:
            search_url = f"https://openlibrary.org/search.json?q={clean}"
            s_resp = requests.get(search_url, timeout=4)
            if s_resp.status_code == 200:
                s_data = s_resp.json()
                docs = s_data.get("docs", [])
                if docs:
                    doc = docs[0]
                    if not title:
                        title = doc.get("title")
                    if not authors and doc.get("author_name"):
                        authors = ", ".join(doc.get("author_name"))
                    if not publisher and doc.get("publisher"):
                        publisher = ", ".join(doc.get("publisher")[:2])
                    if not publish_year and doc.get("first_publish_year"):
                        publish_year = str(doc.get("first_publish_year"))
                    if not cover_url and doc.get("cover_i"):
                        cover_url = f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-M.jpg"
        except Exception:
            pass

    # 3. Fallback to Google Books if still missing title or description
    if not title or not description or not cover_url:
        try:
            gb_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean}"
            gb_resp = requests.get(gb_url, timeout=4)
            if gb_resp.status_code == 200:
                gb_data = gb_resp.json()
                items = gb_data.get("items", [])
                if items:
                    v_info = items[0].get("volumeInfo", {})
                    if not title:
                        title = v_info.get("title")
                    if not authors and v_info.get("authors"):
                        authors = ", ".join(v_info.get("authors"))
                    if not description:
                        description = v_info.get("description")
                    if not publisher:
                        publisher = v_info.get("publisher")
                    if not publish_year and v_info.get("publishedDate"):
                        publish_year = v_info.get("publishedDate")
                    if not cover_url and v_info.get("imageLinks"):
                        cover_url = v_info.get("imageLinks", {}).get("thumbnail")
        except Exception:
            pass

    # Fallback default title if nothing was found online
    if not title:
        title = f"Book (ISBN: {clean})"

    # Save cover image locally if found
    local_cover_rel = save_cover_locally(clean, cover_url)

    return {
        "isbn": clean,
        "title": title,
        "authors": authors or "Unknown Author",
        "description": description or "",
        "publisher": publisher or "",
        "publish_year": publish_year or "",
        "cover_image_path": local_cover_rel
    }

def save_cover_locally(clean_isbn: str, image_url: str) -> str:
    """Download cover image and store it in static/covers/."""
    covers_dir = current_app.config['COVERS_DIR']
    covers_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{clean_isbn}.jpg"
    dest_path = covers_dir / filename

    if dest_path.exists() and dest_path.stat().st_size > 500:
        return f"covers/{filename}"

    if not image_url:
        return None

    try:
        # Download image with timeout
        resp = requests.get(image_url, timeout=5)
        # Avoid Open Library 1x1 blank pixel placeholder
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return f"covers/{filename}"
    except Exception:
        pass

    return None
