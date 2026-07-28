"""Curated-deep research crawler → Smart-Library (:8000).

GPU-safe by design, two stages:
  fetch  — pull curated GitHub READMEs (raw.githubusercontent, no API rate limit) + arXiv
           abstracts to ./staged as JSON. Pure network + disk; no Ollama, no GPU.
  ingest — POST each staged record to Smart-Library /seed (MiniLM CPU embedding; safe to run
           while the GPU is busy with the 14B). Idempotent via a manifest.

Usage (from this directory):
    python crawl.py fetch                 # stage every curated source
    python crawl.py fetch --only open-endedness
    python crawl.py ingest                # push ./staged into Smart-Library
    python crawl.py both
    python crawl.py status                # what's staged / ingested

Env:
    SMART_LIBRARY_URL   default http://localhost:8000
    GITHUB_TOKEN        optional; raises GitHub API limit 60->5000/hr and enables metadata
    MAX_SEED_BYTES      default 48000 (server hard cap is 65536 UTF-8)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import sources

# Windows consoles default to cp1252; force UTF-8 so no log glyph can crash the run.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
STAGED = os.path.join(HERE, "staged")
MANIFEST = os.path.join(STAGED, ".ingested.json")
SL_URL = os.environ.get("SMART_LIBRARY_URL", "http://localhost:8000").rstrip("/")
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
MAX_SEED_BYTES = int(os.environ.get("MAX_SEED_BYTES", "48000"))
UA = "wpai-research-crawler/1.0 (+local)"

# polite pacing (seconds)
GAP_RAW = 0.6
GAP_GH_API = 1.5
GAP_ARXIV = 3.1


def log(msg: str) -> None:
    print(msg, flush=True)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-").lower()
    return s[:120] or "item"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_get(url: str, headers: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    """GET returning (status_code, body). HTTP errors return their real code, not an exception."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:  # noqa: BLE001
            body = b""
        return e.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"    ! network error {url}: {e}")
        return 0, b""


def http_post_json(url: str, payload: dict, timeout: int = 60) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e)


# ───────────────────────── staging ─────────────────────────

def staged_dir(focus: str, source: str) -> str:
    d = os.path.join(STAGED, focus, source)
    os.makedirs(d, exist_ok=True)
    return d


def write_record(focus: str, source: str, slug: str, record: dict) -> str:
    path = os.path.join(staged_dir(focus, source), f"{slug}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path


def record_exists(focus: str, source: str, slug: str) -> bool:
    return os.path.isfile(os.path.join(staged_dir(focus, source), f"{slug}.json"))


# ───────────────────────── GitHub ─────────────────────────

_README_CANDIDATES = ["README.md", "readme.md", "README.rst", "README.markdown", "Readme.md", "README"]
_GH_REFS = ["main", "master"]


def fetch_github_readme(repo: str) -> tuple[str | None, str | None]:
    """Raw README (no API limit). Falls back to the API readme endpoint once if raw misses."""
    for ref in _GH_REFS:
        for name in _README_CANDIDATES:
            code, body = http_get(f"https://raw.githubusercontent.com/{repo}/{ref}/{name}")
            time.sleep(GAP_RAW)
            if code == 200 and body.strip():
                return body.decode("utf-8", "replace"), f"{ref}/{name}"
    # single API fallback
    headers = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    code, body = http_get(f"https://api.github.com/repos/{repo}/readme", headers=headers)
    time.sleep(GAP_GH_API)
    if code == 200:
        try:
            j = json.loads(body)
            return base64.b64decode(j.get("content", "")).decode("utf-8", "replace"), j.get("path", "api")
        except Exception:  # noqa: BLE001
            return None, None
    return None, None


def fetch_github_meta(repo: str, state: dict) -> dict:
    """Best-effort stars/description/language. Stops trying after the first rate-limit (403)."""
    if not state.get("gh_api_ok", True):
        return {}
    headers = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        headers["Authorization"] = f"Bearer {GH_TOKEN}"
    code, body = http_get(f"https://api.github.com/repos/{repo}", headers=headers)
    time.sleep(GAP_GH_API)
    if code == 403:
        state["gh_api_ok"] = False
        log("    (github API rate-limited — continuing with raw READMEs only; set GITHUB_TOKEN for metadata)")
        return {}
    if code == 200:
        try:
            j = json.loads(body)
            return {
                "stars": j.get("stargazers_count"),
                "description": j.get("description"),
                "language": j.get("language"),
                "topics": j.get("topics", []),
            }
        except Exception:  # noqa: BLE001
            return {}
    return {}


def fetch_repos(focus: str, repos: list[tuple[str, str]], state: dict, force: bool) -> tuple[int, int]:
    got, skipped = 0, 0
    for repo, why in repos:
        slug = slugify(repo.replace("/", "-"))
        if not force and record_exists(focus, "github", slug):
            skipped += 1
            continue
        log(f"  gh  {repo}")
        readme, ref = fetch_github_readme(repo)
        if not readme:
            log(f"    ! no README found for {repo}")
            continue
        meta = fetch_github_meta(repo, state)
        write_record(focus, "github", slug, {
            "source": "github", "focus": focus, "category": f"research-{focus}",
            "language": meta.get("language") or "All",
            "title": repo, "url": f"https://github.com/{repo}", "why": why,
            "ref": ref, "meta": meta, "content": readme, "fetched_at": now_iso(),
        })
        got += 1
    return got, skipped


# ───────────────────────── arXiv ─────────────────────────

_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_arxiv_atom(xml_bytes: bytes) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log(f"    ! arxiv parse error: {e}")
        return out
    for entry in root.findall(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip().replace("\n", " ")
        summary = (entry.findtext(f"{_ATOM}summary") or "").strip()
        aid = (entry.findtext(f"{_ATOM}id") or "").strip()
        published = (entry.findtext(f"{_ATOM}published") or "").strip()
        authors = [a.findtext(f"{_ATOM}name") or "" for a in entry.findall(f"{_ATOM}author")]
        if title and summary:
            out.append({"title": title, "summary": summary, "id": aid,
                        "published": published, "authors": authors})
    return out


def fetch_arxiv(focus: str, query: str, max_results: int, force: bool) -> tuple[int, int]:
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}", "start": 0, "max_results": max_results,
        "sortBy": "relevance", "sortOrder": "descending",
    })
    code, body = http_get(f"http://export.arxiv.org/api/query?{params}", timeout=40)
    time.sleep(GAP_ARXIV)
    if code != 200 or not body:
        log(f"    ! arxiv query failed ({code}): {query}")
        return 0, 0
    got, skipped = 0, 0
    for e in parse_arxiv_atom(body):
        arxiv_no = e["id"].rstrip("/").split("/")[-1]
        slug = slugify(arxiv_no + "-" + e["title"][:60])
        if not force and record_exists(focus, "arxiv", slug):
            skipped += 1
            continue
        content = (
            f"{e['title']}\n\nAuthors: {', '.join(a for a in e['authors'] if a)}\n"
            f"Published: {e['published']}\narXiv: {e['id']}\n\nAbstract:\n{e['summary']}"
        )
        write_record(focus, "arxiv", slug, {
            "source": "arxiv", "focus": focus, "category": f"research-{focus}",
            "language": "All", "title": e["title"], "url": e["id"],
            "why": f"arXiv match: {query}", "meta": {"authors": e["authors"], "published": e["published"]},
            "content": content, "fetched_at": now_iso(),
        })
        got += 1
    return got, skipped


# ───────────────────────── ingest ─────────────────────────

def load_manifest() -> set[str]:
    if os.path.isfile(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:  # noqa: BLE001
            return set()
    return set()


def save_manifest(done: set[str]) -> None:
    os.makedirs(STAGED, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f, indent=0)


def chunk_text(text: str, max_bytes: int) -> list[str]:
    """Split on paragraph boundaries so each chunk stays under the server's UTF-8 byte cap."""
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        candidate = (cur + "\n\n" + para) if cur else para
        if len(candidate.encode("utf-8")) > max_bytes and cur:
            chunks.append(cur)
            cur = para
        else:
            cur = candidate
        # a single monster paragraph: hard-split by bytes
        while len(cur.encode("utf-8")) > max_bytes:
            b = cur.encode("utf-8")[:max_bytes]
            chunks.append(b.decode("utf-8", "ignore"))
            cur = cur[len(chunks[-1]):]
    if cur:
        chunks.append(cur)
    return chunks


def build_seed_body(rec: dict) -> str:
    m = rec.get("meta") or {}
    head = [f"[{rec['source'].upper()}] {rec['title']}", f"URL: {rec['url']}",
            f"Focus: {rec['focus']} — {sources.FOCUS_BLURB.get(rec['focus'], '')}"]
    if rec.get("why"):
        head.append(f"Why: {rec['why']}")
    if m.get("stars") is not None:
        head.append(f"Stars: {m['stars']} | Lang: {m.get('language')}")
    return "\n".join(head) + "\n\n---\n\n" + rec["content"]


def iter_staged() -> list[str]:
    paths = []
    for focus in os.listdir(STAGED) if os.path.isdir(STAGED) else []:
        fdir = os.path.join(STAGED, focus)
        if not os.path.isdir(fdir) or focus.startswith("."):
            continue
        for source in os.listdir(fdir):
            sdir = os.path.join(fdir, source)
            if not os.path.isdir(sdir):
                continue
            for name in os.listdir(sdir):
                if name.endswith(".json"):
                    paths.append(os.path.join(sdir, name))
    return sorted(paths)


def ingest_all(only: str | None, force: bool) -> None:
    done = set() if force else load_manifest()
    paths = iter_staged()
    seeded_files, seeded_chunks, failed, skipped = 0, 0, 0, 0
    for path in paths:
        rel = os.path.relpath(path, STAGED)
        if only and not rel.startswith(only + os.sep):
            continue
        if rel in done:
            skipped += 1
            continue
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception as e:  # noqa: BLE001
            log(f"  ! bad staged file {rel}: {e}")
            failed += 1
            continue
        body = build_seed_body(rec)
        chunks = chunk_text(body, MAX_SEED_BYTES)
        ok = True
        for i, ch in enumerate(chunks):
            tag = rec["category"] + (f" [part {i+1}/{len(chunks)}]" if len(chunks) > 1 else "")
            code, msg = http_post_json(f"{SL_URL}/seed", {
                "content": ch, "category": tag, "language": rec.get("language", "All"),
            })
            if code == 200:
                seeded_chunks += 1
            else:
                ok = False
                log(f"  ! seed failed ({code}) {rel} part {i+1}: {msg[:120]}")
                break
        if ok:
            done.add(rel)
            seeded_files += 1
            log(f"  + {rel}  ({len(chunks)} chunk{'s' if len(chunks) > 1 else ''})")
            save_manifest(done)  # persist as we go so a crash never re-seeds
        else:
            failed += 1
    log(f"\nINGEST DONE — files seeded={seeded_files} chunks={seeded_chunks} "
        f"skipped(already)={skipped} failed={failed}  (SL={SL_URL})")


# ───────────────────────── commands ─────────────────────────

def cmd_fetch(args) -> None:
    focuses = [args.only] if args.only else list(sources.GITHUB_REPOS.keys())
    state = {"gh_api_ok": True}
    tot_new, tot_skip = 0, 0
    for focus in focuses:
        log(f"\n=== FETCH focus: {focus} ===")
        g_new, g_skip = fetch_repos(focus, sources.GITHUB_REPOS.get(focus, []), state, args.force)
        a_new, a_skip = 0, 0
        for query, n in sources.ARXIV_QUERIES.get(focus, []):
            log(f"  arxiv \"{query}\"")
            n2, s2 = fetch_arxiv(focus, query, n, args.force)
            a_new += n2
            a_skip += s2
        log(f"  focus {focus}: github +{g_new} (skip {g_skip}), arxiv +{a_new} (skip {a_skip})")
        tot_new += g_new + a_new
        tot_skip += g_skip + a_skip
    log(f"\nFETCH DONE — new staged={tot_new}, already-staged skipped={tot_skip}, dir={STAGED}")


def cmd_ingest(args) -> None:
    log(f"=== INGEST -> {SL_URL}/seed  (max {MAX_SEED_BYTES}B/seed) ===")
    ingest_all(args.only, args.force)


def cmd_status(args) -> None:
    paths = iter_staged()
    done = load_manifest()
    by_focus: dict[str, dict[str, int]] = {}
    for p in paths:
        rel = os.path.relpath(p, STAGED)
        focus = rel.split(os.sep)[0]
        source = rel.split(os.sep)[1]
        by_focus.setdefault(focus, {}).setdefault(source, 0)
        by_focus[focus][source] += 1
    log(f"STAGED under {STAGED}:")
    for focus, srcs in sorted(by_focus.items()):
        log(f"  {focus}: " + ", ".join(f"{s}={n}" for s, n in sorted(srcs.items())))
    log(f"total staged={len(paths)}  ingested(manifest)={len(done)}  SL={SL_URL}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Curated-deep research crawler → Smart-Library")
    ap.add_argument("cmd", choices=["fetch", "ingest", "both", "status"])
    ap.add_argument("--only", default=None, help="limit to one focus (e.g. local-inference)")
    ap.add_argument("--force", action="store_true", help="re-fetch / re-ingest even if present")
    args = ap.parse_args()
    if args.cmd in ("fetch", "both"):
        cmd_fetch(args)
    if args.cmd in ("ingest", "both"):
        cmd_ingest(args)
    if args.cmd == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
