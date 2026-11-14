import os
import re
import requests
from pathlib import Path
from flask import current_app

HEADERS = {
    'User-Agent': 'TanagerLibraryManager/1.0 (https://github.com/djbrowne/library-mgr)'
}

# Mapping patterns to normalize genre from subjects & categories
GENRE_PATTERNS = [
    (r'\b(computer|programming|software|coding|python|java|algorithm|developer|web development)\b', 'Technology & Engineering'),
    (r'\b(science fiction|sci-fi|space opera|cyberpunk|dystopi)\b', 'Science Fiction'),
    (r'\b(fantasy|magic|dragons|wizards|mythology)\b', 'Fantasy'),
    (r'\b(mystery|thriller|detective|crime|suspense|murder)\b', 'Mystery & Thriller'),
    (r'\b(biography|autobiography|memoir|diaries)\b', 'Biography & Memoir'),
    (r'\b(history|historical|ancient|civilization|war|military)\b', 'History'),
    (r'\b(philosophy|psychology|ethics|existential|meditation|self-help)\b', 'Philosophy & Psychology'),
    (r'\b(physics|biology|chemistry|mathematics|astronomy|nature|ecology)\b', 'Science & Nature'),
    (r'\b(art|photography|graphic design|music|cinema|architecture)\b', 'Arts & Photography'),
    (r'\b(juvenile|children|young adult|picture books)\b', "Children & Young Adult"),
    (r'\b(fiction|novel|stories|literature|drama)\b', 'Fiction'),
    (r'\b(non-fiction|nonfiction|essay|journalism)\b', 'Non-Fiction')
]

IGNORED_TAG_TOKENS = {
    'accessible book', 'protected daisy', 'in library', 'borrowable',
    'open_syllabus_project', 'internet archive', 'long now manual',
    'deposit libraries', 'lending library', 'nyt:paperback_nonfiction'
}

def clean_tag_name(raw: str) -> str:
    """Normalize a tag string into a clean, lowercased, slug-friendly tag."""
    if not raw:
        return ""
    # Strip parenthetical annotations like "(computer science)"
    tag = re.sub(r'\(.*?\)', '', str(raw)).strip().lower()
    tag = re.sub(r'[^a-z0-9\s\-]', '', tag).strip()
    tag = re.sub(r'[\s_]+', '-', tag)
    tag = re.sub(r'-+', '-', tag).strip('-')
    if len(tag) < 3 or len(tag) > 30:
        return ""
    return tag

def infer_genre_and_tags(categories=None, subjects=None, title=None, desc=None) -> tuple:
    """
    Examine subjects, categories, title, and description to infer
    best-effort standard genre and up to 6 free-form tags.
    """
    categories = categories or []
    subjects = subjects or []
    raw_candidates = []

    for c in categories:
        if isinstance(c, str):
            for part in c.split('/'):
                raw_candidates.append(part.strip())

    for s in subjects:
        if isinstance(s, str):
            raw_candidates.append(s.strip())
        elif isinstance(s, dict) and 'name' in s:
            raw_candidates.append(s['name'].strip())

    # Build searchable corpus for genre matching
    combined_corpus = " ".join([
        " ".join(raw_candidates),
        title or "",
        desc or ""
    ]).lower()

    inferred_genre = "General"
    for pattern, genre in GENRE_PATTERNS:
        if re.search(pattern, combined_corpus):
            inferred_genre = genre
            break

    # Extract distinct, cleaned tags
    seen_tags = set()
    tags = []
    for raw in raw_candidates:
        raw_low = raw.lower()
        if any(ignored in raw_low for ignored in IGNORED_TAG_TOKENS):
            continue
        cleaned = clean_tag_name(raw)
        if cleaned and cleaned not in seen_tags:
            seen_tags.add(cleaned)
            tags.append(cleaned)
        if len(tags) >= 6:
            break

    # If no tags extracted from subjects, generate initial tags from genre & key title terms
    if not tags and inferred_genre != "General":
        tags.append(clean_tag_name(inferred_genre))

    return inferred_genre, tags

def clean_isbn(raw_isbn: str) -> str:
    """Strip hyphens, spaces, and normalize ISBN string."""
    if not raw_isbn:
        return ""
    cleaned = re.sub(r'[^0-9Xx]', '', raw_isbn.strip()).upper()
    return cleaned

def clean_text(text: str) -> str:
    """Remove Markdown links, URLs, and excessive whitespace from descriptions."""
    if not text:
        return ""
    if isinstance(text, dict):
        text = text.get("value", "")
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    text = re.sub(r'[\r\n]+', '\n', text)
    return text.strip()

def fetch_work_description(work_key: str) -> str:
    """Fetch description from Open Library Work endpoint (e.g. /works/OL1234567W)."""
    if not work_key:
        return ""
    try:
        url = f"https://openlibrary.org{work_key}.json"
        resp = requests.get(url, headers=HEADERS, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            desc = data.get("description")
            cleaned = clean_text(desc)
            if cleaned:
                return cleaned
    except Exception:
        pass
    return ""

def fetch_wikipedia_summary(title: str, author: str = None) -> str:
    """Query Wikipedia REST/Search API for book or author summary."""
    if not title:
        return ""

    queries = []
    if author and author != "Unknown Author":
        queries.append(f'"{title}" {author} book')
    queries.append(f'"{title}" novel')
    queries.append(f'"{title}" book')
    queries.append(title)

    for q in queries:
        try:
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={requests.utils.quote(q)}&format=json"
            resp = requests.get(search_url, headers=HEADERS, timeout=4)
            if resp.status_code != 200:
                continue

            results = resp.json().get('query', {}).get('search', [])
            for item in results[:2]:
                page_title = item.get('title')
                if not page_title:
                    continue

                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(page_title.replace(' ', '_'))}"
                sum_resp = requests.get(summary_url, headers=HEADERS, timeout=4)
                if sum_resp.status_code == 200:
                    sum_data = sum_resp.json()
                    extract = sum_data.get('extract')
                    desc_type = sum_data.get('description', '').lower()
                    if extract:
                        ext_lower = extract.lower()
                        # Verify relevance to books/novels/authors
                        if ('book' in ext_lower or 'novel' in ext_lower or 'published' in ext_lower or
                            'author' in ext_lower or 'writer' in ext_lower or 'book' in desc_type or
                            'novel' in desc_type or title.lower() in page_title.lower()):
                            return clean_text(extract)
        except Exception:
            continue

    return ""

def fetch_book_description(isbn: str, title: str = None, authors: str = None, work_key: str = None, raw_data: dict = None) -> str:
    """
    Dedicated multi-source description resolver.
    If initial edition lookup lacks a description, resolves it via:
    1. Open Library Work record (/works/OL...json)
    2. Google Books API (with optional GOOGLE_BOOKS_API_KEY support)
    3. Wikipedia article summary for title/author
    4. Open Library subject/series/notes synthesis fallback
    """
    clean = clean_isbn(isbn)
    raw_data = raw_data or {}

    if not title or not raw_data:
        try:
            r = requests.get(f"https://openlibrary.org/isbn/{clean}.json", headers=HEADERS, timeout=4)
            if r.status_code == 200:
                raw_data = r.json()
                if not title:
                    title = raw_data.get("title")
        except Exception:
            pass

    # 1. Check Open Library Work record
    if not work_key and raw_data.get("works"):
        work_key = raw_data["works"][0].get("key")

    if work_key:
        work_desc = fetch_work_description(work_key)
        if work_desc:
            return work_desc

    # 2. Query Google Books API
    try:
        api_key = os.environ.get('GOOGLE_BOOKS_API_KEY', '').strip()
        gb_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean}"
        if api_key:
            gb_url += f"&key={api_key}"
        gb_resp = requests.get(gb_url, headers=HEADERS, timeout=4)
        if gb_resp.status_code == 200:
            gb_data = gb_resp.json()
            items = gb_data.get("items", [])
            if items:
                v_desc = items[0].get("volumeInfo", {}).get("description")
                if v_desc:
                    return clean_text(v_desc)
    except Exception:
        pass

    # If title is available, try Google Books by title and author
    if title and title != f"Book (ISBN: {clean})":
        try:
            api_key = os.environ.get('GOOGLE_BOOKS_API_KEY', '').strip()
            q_str = f"intitle:{title}"
            if authors and authors != "Unknown Author":
                q_str += f"+inauthor:{authors.split(',')[0].strip()}"
            gb_url2 = f"https://www.googleapis.com/books/v1/volumes?q={requests.utils.quote(q_str)}"
            if api_key:
                gb_url2 += f"&key={api_key}"
            gb_resp2 = requests.get(gb_url2, headers=HEADERS, timeout=4)
            if gb_resp2.status_code == 200:
                gb_data2 = gb_resp2.json()
                items2 = gb_data2.get("items", [])
                if items2:
                    v_desc2 = items2[0].get("volumeInfo", {}).get("description")
                    if v_desc2:
                        return clean_text(v_desc2)
        except Exception:
            pass

    # 3. Query Wikipedia for summary
    if title and title != f"Book (ISBN: {clean})":
        wiki_desc = fetch_wikipedia_summary(title, authors)
        if wiki_desc:
            return wiki_desc

    # 4. Open Library Subject & Scope Synthesis Fallback
    subjects = raw_data.get("subjects", [])
    if not subjects and work_key:
        try:
            w_resp = requests.get(f"https://openlibrary.org{work_key}.json", headers=HEADERS, timeout=3)
            if w_resp.status_code == 200:
                subjects = w_resp.json().get("subjects", [])
        except Exception:
            pass

    if subjects:
        subj_names = [s if isinstance(s, str) else s.get("name", "") for s in subjects]
        subj_names = [s for s in subj_names if s][:5]
        if subj_names:
            auth_str = f" by {authors}" if (authors and authors != "Unknown Author") else ""
            return f"A volume{auth_str} covering: {', '.join(subj_names)}."

    # 5. Open Library notes/first_sentence fallback
    notes = raw_data.get("notes")
    if notes:
        return clean_text(notes)

    first_sentence = raw_data.get("first_sentence")
    if first_sentence:
        return clean_text(first_sentence)

    return ""

def fetch_book_metadata(isbn: str) -> dict:
    """
    Lookup book metadata using Open Library and Google Books API.
    Downloads cover image to local static/covers/ directory.
    If description is missing from the initial edition, executes
    a dedicated multi-source description lookup.
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
    work_key = None
    raw_data = {}
    raw_subjects = []
    raw_categories = []

    # 1. Try Open Library direct endpoint
    try:
        url = f"https://openlibrary.org/isbn/{clean}.json"
        resp = requests.get(url, headers=HEADERS, timeout=4)
        if resp.status_code == 200:
            raw_data = resp.json()
            title = raw_data.get("title")
            publish_year = raw_data.get("publish_date")
            if raw_data.get("publishers"):
                publisher = ", ".join(raw_data.get("publishers"))
            
            # Extract subjects
            if raw_data.get("subjects"):
                raw_subjects.extend(raw_data.get("subjects"))

            # Extract work key
            if raw_data.get("works"):
                work_key = raw_data["works"][0].get("key")

            # Covers
            covers = raw_data.get("covers")
            if covers and len(covers) > 0 and covers[0] > 0:
                cover_url = f"https://covers.openlibrary.org/b/id/{covers[0]}-M.jpg"
            else:
                cover_url = f"https://covers.openlibrary.org/b/isbn/{clean}-M.jpg"

            # Check description on edition
            desc_field = raw_data.get("description")
            if desc_field:
                description = clean_text(desc_field)
    except Exception:
        pass

    # 2. Try Open Library Search endpoint to resolve authors or fill in missing fields
    if not title or not authors or not raw_subjects:
        try:
            search_url = f"https://openlibrary.org/search.json?q={clean}"
            s_resp = requests.get(search_url, headers=HEADERS, timeout=4)
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
                    if not work_key and doc.get("key"):
                        work_key = doc.get("key")
                    if doc.get("subject"):
                        raw_subjects.extend(doc.get("subject")[:10])
        except Exception:
            pass

    # 3. Fallback to Google Books for basic bibliographic info if still missing
    if not title or not authors or not cover_url or not raw_categories:
        try:
            api_key = os.environ.get('GOOGLE_BOOKS_API_KEY', '').strip()
            gb_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean}"
            if api_key:
                gb_url += f"&key={api_key}"
            gb_resp = requests.get(gb_url, headers=HEADERS, timeout=4)
            if gb_resp.status_code == 200:
                gb_data = gb_resp.json()
                items = gb_data.get("items", [])
                if items:
                    v_info = items[0].get("volumeInfo", {})
                    if not title:
                        title = v_info.get("title")
                    if not authors and v_info.get("authors"):
                        authors = ", ".join(v_info.get("authors"))
                    if not description and v_info.get("description"):
                        description = clean_text(v_info.get("description"))
                    if not publisher and v_info.get("publisher"):
                        publisher = v_info.get("publisher")
                    if not publish_year and v_info.get("publishedDate"):
                        publish_year = v_info.get("publishedDate")
                    if not cover_url and v_info.get("imageLinks"):
                        cover_url = v_info.get("imageLinks", {}).get("thumbnail")
                    if v_info.get("categories"):
                        raw_categories.extend(v_info.get("categories"))
        except Exception:
            pass

    # Fallback default title if nothing was found online
    if not title:
        title = f"Book (ISBN: {clean})"

    # 4. If description was NOT in the initial metadata, look it up separately!
    if not description:
        description = fetch_book_description(
            clean,
            title=title,
            authors=authors,
            work_key=work_key,
            raw_data=raw_data
        )

    # Infer best-effort genre and free-form tags
    inferred_genre, inferred_tags = infer_genre_and_tags(
        categories=raw_categories,
        subjects=raw_subjects,
        title=title,
        desc=description
    )

    # Save cover image locally if found
    local_cover_rel = save_cover_locally(clean, cover_url)

    return {
        "isbn": clean,
        "title": title,
        "authors": authors or "Unknown Author",
        "description": description or "",
        "publisher": publisher or "",
        "publish_year": publish_year or "",
        "cover_image_path": local_cover_rel,
        "genre": inferred_genre,
        "tags": inferred_tags
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
        resp = requests.get(image_url, headers=HEADERS, timeout=5)
        # Avoid Open Library 1x1 blank pixel placeholder
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return f"covers/{filename}"
    except Exception:
        pass

    return None
