"""
docsearch: a small search engine for your own documents.
 
Usage:
    python docsearch.py index ~/Documents        # build / update the index
    python docsearch.py search "tax receipts"    # one-off search
    python docsearch.py                          # interactive search prompt
 
Features: BM25 ranking, stop words, light stemming, incremental re-indexing
(only changed files are re-read), snippets with the match highlighted.
Plain-text formats work out of the box. For PDF and Word files, install:
    pip install pypdf python-docx
"""
import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
 
INDEX_FILE = Path.home() / ".docsearch_index.json"
SNIPPET_CACHE_CHARS = 20000  # text kept per document for result snippets
 
TEXT_EXT = {".txt", ".md", ".rst", ".csv", ".log", ".json", ".html",
            ".htm", ".tex", ".py", ".js", ".yaml", ".yml"}
OPTIONAL_EXT = {".pdf", ".docx"}
 
STOP_WORDS = set("""
a an and are as at be but by for from has have he i if in into is it its of on
or she so that the their them then there they this to was we were will with you
""".split())
 
 
# ---------------------------------------------------------------- text handling
def stem(word):
    """Very light suffix stripping so 'notes' matches 'note'."""
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""),
                                ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + replacement
    return word
 
 
def tokenize(text):
    words = re.findall(r"\w+", text.lower())
    return [stem(w) for w in words if w not in STOP_WORDS and len(w) > 1]
 
 
def read_text(path):
    """Return the file's text, or None if it can't be read."""
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
        if ext == ".docx":
            from docx import Document
            return "\n".join(p.text for p in Document(path).paragraphs)
        return path.read_text(encoding="utf-8", errors="ignore")
    except ImportError:
        raise
    except Exception as exc:
        print(f"  ! could not read {path}: {exc}", file=sys.stderr)
        return None
 
 
def iter_files(root):
    """Yield files under root, skipping hidden items and unreadable folders."""
    def on_error(err):
        print(f"  ! skipping {err.filename}: {err.strerror}", file=sys.stderr)
 
    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not name.startswith("."):
                yield Path(dirpath) / name
 
 
# ------------------------------------------------------------------- the index
class SearchIndex:
    def __init__(self, index_path=INDEX_FILE):
        self.index_path = Path(index_path)
        self.docs = {}  # path -> {"mtime": float, "length": int, "tf": {term: n}}
        if self.index_path.exists():
            try:
                self.docs = json.loads(self.index_path.read_text())
            except (json.JSONDecodeError, OSError):
                print(f"Warning: {self.index_path} is unreadable; starting with an "
                      "empty index. Re-run 'index' to rebuild it.", file=sys.stderr)
                self.docs = {}
        self._build_postings()
 
    def _build_postings(self):
        self.postings = defaultdict(dict)  # term -> {path: count}
        for path, doc in self.docs.items():
            for term, count in doc["tf"].items():
                self.postings[term][path] = count
        total = sum(d["length"] for d in self.docs.values())
        # 'or 1' avoids dividing by zero for an empty index or only-empty documents
        self.avg_len = (total / len(self.docs) if self.docs else 0) or 1
 
    def save(self):
        """Write to a temp file, then swap it in, so a crash can't corrupt the index."""
        tmp = self.index_path.with_name(self.index_path.name + ".tmp")
        tmp.write_text(json.dumps(self.docs))
        os.replace(tmp, self.index_path)
 
    def update(self, root):
        """Index new/changed files under root and drop files that disappeared."""
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            sys.exit(f"Error: '{root}' is not a folder.")
        seen, added, skipped_types = set(), 0, set()
 
        for path in iter_files(root):
            ext = path.suffix.lower()
            if ext not in TEXT_EXT | OPTIONAL_EXT:
                continue
 
            key = str(path)
            try:
                mtime = path.stat().st_mtime
            except OSError as exc:
                print(f"  ! skipping {path}: {exc.strerror}", file=sys.stderr)
                continue
            seen.add(key)
            if key in self.docs and self.docs[key]["mtime"] == mtime:
                continue  # unchanged
 
            try:
                text = read_text(path)
            except ImportError:
                skipped_types.add(ext)
                seen.discard(key)
                continue
            if text is None:  # unreadable; already reported
                seen.discard(key)
                continue
            tokens = tokenize(text)
            self.docs[key] = {"mtime": mtime, "length": len(tokens),
                              "tf": dict(Counter(tokens)),
                              "text": re.sub(r"\s+", " ", text)[:SNIPPET_CACHE_CHARS]}
            added += 1
            print(f"  indexed {path}")
 
        # Remove entries for deleted files that lived under this root.
        prefix = str(root) + os.sep
        removed = [k for k in self.docs if k.startswith(prefix) and k not in seen]
        for k in removed:
            del self.docs[k]
 
        self.save()
        self._build_postings()
        print(f"\nDone: {added} added/updated, {len(removed)} removed, "
              f"{len(self.docs)} documents total.")
        if skipped_types:
            print(f"Skipped {', '.join(sorted(skipped_types))} files "
                  "(run: pip install pypdf python-docx)")
 
    def search(self, query, top_k=5, k1=1.5, b=0.75):
        """Rank documents with BM25."""
        terms = tokenize(query)
        n_docs = len(self.docs)
        scores = defaultdict(float)
 
        for term in set(terms):
            postings = self.postings.get(term, {})
            if not postings:
                continue
            idf = math.log(1 + (n_docs - len(postings) + 0.5) / (len(postings) + 0.5))
            for path, tf in postings.items():
                length = self.docs[path]["length"]
                norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / self.avg_len))
                scores[path] += idf * norm
 
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(path, score, self._snippet(self.docs[path].get("text", ""), terms))
                for path, score in ranked]
 
    @staticmethod
    def _snippet(text, terms, width=80):
        if not terms:
            return text[: 2 * width]
        pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in set(terms)) + r")\w*", re.I)
        match = pattern.search(text)
        if not match:
            return text[: 2 * width]
        start, end = max(0, match.start() - width), min(len(text), match.end() + width)
        snippet = pattern.sub(lambda m: f"**{m.group(0)}**", text[start:end])
        return ("..." if start else "") + snippet + ("..." if end < len(text) else "")
 
 
# ------------------------------------------------------------------------- CLI
def show(results):
    if not results:
        print("No matches.")
        return
    for i, (path, score, snippet) in enumerate(results, 1):
        print(f"\n{i}. {path}  (score {score:.2f})\n   {snippet}")
 
 
def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Search your own documents.")
    sub = parser.add_subparsers(dest="cmd")
    p_index = sub.add_parser("index", help="index a folder")
    p_index.add_argument("folder")
    p_search = sub.add_parser("search", help="search the index")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("-n", type=int, default=5, help="number of results")
    args = parser.parse_args()
 
    engine = SearchIndex()
 
    if args.cmd == "index":
        engine.update(args.folder)
    elif args.cmd == "search":
        if not engine.docs:
            sys.exit("Index is empty. Run:  python docsearch.py index <folder>")
        show(engine.search(" ".join(args.query), top_k=args.n))
    else:  # interactive mode
        if not engine.docs:
            sys.exit("Index is empty. Run:  python docsearch.py index <folder>")
        print(f"{len(engine.docs)} documents indexed. Empty line to quit.")
        try:
            while (q := input("\nsearch> ").strip()):
                show(engine.search(q))
        except (EOFError, KeyboardInterrupt):
            print()
 
 
if __name__ == "__main__":
    main()
 