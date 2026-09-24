"""
Công cụ tìm kiếm web, tra cứu DuckDuckGo, tìm & hiển thị hình ảnh, mở URL.
"""

import os
import re
import shutil
import urllib.parse
import subprocess
import requests
from ai_assistant.config import PICTURES_DIR, URL_SHORTCUTS

def search_duckduckgo_summary(query: str, max_results: int = 2) -> str:
    """Tra cứu tóm tắt thông tin thời gian thực từ DuckDuckGo."""
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=4)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        clean_snippets = []
        for s in snippets[:max_results]:
            clean = re.sub(r'<.*?>', '', s).strip()
            clean = re.sub(r'\s+', ' ', clean)
            if clean:
                clean_snippets.append(clean)
        return ' '.join(clean_snippets) if clean_snippets else ''
    except Exception:
        return ''

def search_and_display_image(query: str, download_dir: str = PICTURES_DIR) -> tuple[bool, str]:
    """Tìm kiếm hình ảnh trên web, tải về thư mục Pictures và mở hiển thị ngay trên màn hình."""
    clean_q = re.sub(r"^(?:tìm\s+)?(?:cho\s+tôi\s+)?(?:bức\s+|tấm\s+|hình\s+)?ảnh\s+(?:về\s+)?", "", query, flags=re.IGNORECASE)
    pattern = r'\s+(?:trên\s+(?:mạng|web|google|bing)|và\s+đưa\s+về\s+đây|về\s+đây|về\s+máy|cho\s+tôi|giùm\s+tôi|hộ\s+tôi)$'
    prev = ''
    while prev != clean_q:
        prev = clean_q
        clean_q = re.sub(pattern, '', clean_q, flags=re.IGNORECASE).strip()

    if not clean_q:
        return False, "Bạn muốn tôi tìm bức ảnh gì nào?"

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    img_url = None

    # 1. Thử Bing Images
    try:
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(clean_q)}&FORM=HDRSC2"
        resp = requests.get(url, headers=headers, timeout=5)
        murls = re.findall(r'murl&quot;:&quot;(http[^&]+)&quot;', resp.text)
        if murls:
            img_url = murls[0]
    except Exception:
        pass

    # 2. Thử Wikimedia Commons fallback
    if not img_url:
        try:
            wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrsearch={urllib.parse.quote(clean_q)}&gsrlimit=3&prop=imageinfo&iiprop=url&format=json"
            r = requests.get(wiki_url, headers={'User-Agent': 'VoiceAssistant/1.0'}, timeout=5)
            pages = r.json().get('query', {}).get('pages', {})
            for k, v in pages.items():
                info = v.get('imageinfo', [])
                if info and 'url' in info[0]:
                    img_url = info[0]['url']
                    break
        except Exception:
            pass

    if not img_url:
        return False, f"Tôi không tìm thấy bức ảnh nào về {clean_q} trên mạng."

    try:
        os.makedirs(download_dir, exist_ok=True)
        safe_name = re.sub(r'[^\w\-_]', '_', clean_q.lower())
        ext = ".png" if ".png" in img_url.lower() else (".webp" if ".webp" in img_url.lower() else ".jpg")
        save_path = os.path.join(download_dir, f"{safe_name}{ext}")

        img_bytes = requests.get(img_url, headers=headers, timeout=8).content
        if len(img_bytes) > 1024:
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            viewer = "viewnior" if shutil.which("viewnior") else "xdg-open"
            subprocess.Popen([viewer, save_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Đã tìm thấy và mở ảnh {clean_q} cho bạn rồi nhé."
    except Exception:
        pass
    return False, f"Không thể tải và hiển thị bức ảnh về {clean_q} lúc này."

def open_url(url: str):
    """Mở link URL trong trình duyệt mặc định."""
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def open_youtube_search(query: str = "") -> str:
    """Mở tìm kiếm YouTube."""
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}" if query else "https://www.youtube.com"
    open_url(url)
    return f"Đang mở {query} trên YouTube cho bạn." if query else "Đã mở YouTube cho bạn rồi nhé."

def open_google_search(query: str) -> str:
    """Mở tìm kiếm Google."""
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    open_url(url)
    return f"Đang tìm kiếm {query} trên Google cho bạn."
