from html.parser import HTMLParser
from collections import Counter
import html
import json
import math
import os
import re
from flask import Flask, abort, render_template, request, send_from_directory

INDEX_FILE = "word_counts.json"
LEGACY_INDEX_FILE = "index.json"
DEFAULT_DOCS_DIR = "docs"
WORD_REGEX = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
INDEX_CACHE = None


class MyHTMLParser(HTMLParser):
    TOKEN_REGEX = re.compile(
        r"(?P<WORD>[A-Za-z]+(?:'[A-Za-z]+)?)|"
        r"(?P<NUMBER>\d+(?:\.\d+)?)|"
        r"(?P<PUNCT>[.,!?;:()\"-])"
    )
    CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
    WHITESPACE = re.compile(r"\s+")

    def __init__(self):
        super().__init__()
        self.word_counts = Counter()

    def clean_data(self, data: str) -> str:
        cleaned = self.CONTROL_CHARS.sub(" ", data)
        cleaned = self.WHITESPACE.sub(" ", cleaned).strip()
        return cleaned

    def lex(self, text: str) -> list[tuple[str, str]]:
        return [(match.lastgroup, match.group()) for match in self.TOKEN_REGEX.finditer(text)]

    def handle_data(self, data):
        cleaned = self.clean_data(data)
        if cleaned:
            tokens = self.lex(cleaned)
            for token_type, token_value in tokens:
                if token_type == "WORD":
                    self.word_counts[token_value.lower()] += 1


class PlainTextHTMLParser(HTMLParser):
    CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
    WHITESPACE = re.compile(r"\s+")

    def __init__(self):
        super().__init__()
        self.parts = []
        self.main_parts = []
        self._skip_depth = 0
        self._main_depth = 0

    @staticmethod
    def _attrs_to_dict(attrs):
        return {key: value for key, value in attrs if key}

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return

        attr_map = self._attrs_to_dict(attrs)
        class_names = set((attr_map.get("class") or "").split())
        is_main_container = attr_map.get("role") == "main" or "body" in class_names
        if is_main_container:
            self._main_depth += 1
        elif self._main_depth > 0:
            self._main_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if self._main_depth > 0:
            self._main_depth -= 1

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        cleaned = self.CONTROL_CHARS.sub(" ", data)
        cleaned = self.WHITESPACE.sub(" ", cleaned).strip()
        if cleaned:
            self.parts.append(cleaned)
            if self._main_depth > 0:
                self.main_parts.append(cleaned)

    def text(self) -> str:
        if self.main_parts:
            return " ".join(self.main_parts)
        return " ".join(self.parts)


def process_html_file(file_path: str) -> dict[str, int]:
    parser = MyHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return dict(parser.word_counts)


def tokenize_words(text: str) -> list[str]:
    return [match.group().lower() for match in WORD_REGEX.finditer(text)]


def index_file(file_path: str, output_file: str = INDEX_FILE) -> dict[str, dict[str, int]]:
    counts_by_file: dict[str, dict[str, int]] = {}
    for dirpath, _, filenames in os.walk(file_path):
        for filename in filenames:
            if not filename.endswith((".html", ".xhtl", ".xhtml")):
                continue
            absolute_file_path = os.path.join(dirpath, filename)
            file_key = f"{dirpath}/{filename}"
            print("Working with {}".format(absolute_file_path))
            counts_by_file[file_key] = process_html_file(absolute_file_path)

    with open(output_file, "w", encoding="utf-8") as json_file:
        json.dump(counts_by_file, json_file, indent=2, sort_keys=True)

    print("Saved word counts to {}".format(output_file))
    return counts_by_file


def load_index_data() -> dict[str, dict[str, int]]:
    global INDEX_CACHE
    if INDEX_CACHE is not None:
        return INDEX_CACHE

    for candidate in (INDEX_FILE, LEGACY_INDEX_FILE):
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as source_file:
                INDEX_CACHE = json.load(source_file)
            return INDEX_CACHE

    if os.path.isdir(DEFAULT_DOCS_DIR):
        INDEX_CACHE = index_file(DEFAULT_DOCS_DIR, output_file=INDEX_FILE)
        return INDEX_CACHE

    raise FileNotFoundError(
        "No search index found. Run: python main.py INDEX <folder path>."
    )


def docs_relative_path(file_key: str) -> str | None:
    normalized = file_key.replace("\\", "/")
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    docs_dir_name = os.path.basename(docs_root.rstrip("/")) or "docs"
    docs_prefix = f"{docs_dir_name}/"

    absolute_key = os.path.abspath(file_key)
    try:
        if os.path.commonpath([docs_root, absolute_key]) == docs_root:
            return os.path.relpath(absolute_key, docs_root).replace(os.sep, "/")
    except ValueError:
        pass

    if normalized.startswith(docs_prefix):
        return normalized[len(docs_prefix):]

    marker = f"/{docs_dir_name}/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]

    if normalized.endswith((".html", ".xhtml", ".xhtl")) and not normalized.startswith("/"):
        return normalized.lstrip("./")

    return None


def safe_doc_path_or_404(doc_path: str) -> str:
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    normalized = os.path.normpath(doc_path).replace("\\", "/")
    if normalized in (".", ""):
        normalized = "index.html"

    if normalized == ".." or normalized.startswith("../"):
        abort(404)

    absolute_file_path = os.path.abspath(os.path.join(docs_root, normalized))
    try:
        if os.path.commonpath([docs_root, absolute_file_path]) != docs_root:
            abort(404)
    except ValueError:
        abort(404)

    if not os.path.isfile(absolute_file_path):
        abort(404)

    return normalized


def extract_plain_text_from_html(file_path: str) -> str:
    parser = PlainTextHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return parser.text()


def build_query_term_regex(query_terms: list[str]) -> re.Pattern | None:
    unique_terms = sorted(set(query_terms), key=len, reverse=True)
    if not unique_terms:
        return None
    return re.compile(
        r"\b(" + "|".join(re.escape(term) for term in unique_terms) + r")\b",
        re.IGNORECASE,
    )


def highlight_query_terms(text: str, query_terms: list[str]) -> str:
    pattern = build_query_term_regex(query_terms)
    if pattern is None:
        return html.escape(text)

    highlighted_parts = []
    last_index = 0
    for match in pattern.finditer(text):
        highlighted_parts.append(html.escape(text[last_index:match.start()]))
        highlighted_parts.append(f"<mark>{html.escape(match.group(0))}</mark>")
        last_index = match.end()
    highlighted_parts.append(html.escape(text[last_index:]))
    return "".join(highlighted_parts)


def build_result_snippet(
    doc_path: str | None,
    query_terms: list[str],
    max_length: int = 220,
) -> str | None:
    if not doc_path:
        return None

    full_path = os.path.join(DEFAULT_DOCS_DIR, doc_path)
    if not os.path.isfile(full_path):
        return None

    plain_text = extract_plain_text_from_html(full_path)
    if not plain_text:
        return None

    match_pattern = build_query_term_regex(query_terms)
    match_start = 0
    if match_pattern is not None:
        match = match_pattern.search(plain_text)
        if match is not None:
            match_start = match.start()

    start = max(0, match_start - (max_length // 3))
    end = min(len(plain_text), start + max_length)

    if start > 0:
        next_space = plain_text.find(" ", start)
        if next_space != -1:
            start = next_space + 1
    if end < len(plain_text):
        previous_space = plain_text.rfind(" ", start, end)
        if previous_space > start:
            end = previous_space

    snippet = plain_text[start:end].strip()
    if not snippet:
        return None

    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(plain_text) else ""
    return f"{prefix}{highlight_query_terms(snippet, query_terms)}{suffix}"


def attach_result_snippets(results: list[dict[str, object]], query_terms: list[str]) -> None:
    for result in results:
        doc_path = result.get("doc_path")
        if not isinstance(doc_path, str):
            result["snippet_html"] = None
            continue
        result["snippet_html"] = build_result_snippet(doc_path, query_terms)


def tf_idf_search(
    query: str,
    counts_by_file: dict[str, dict[str, int]],
    limit: int = 20,
) -> list[dict[str, object]]:
    query_terms = tokenize_words(query)
    if not query_terms:
        return []

    document_count = len(counts_by_file)
    if document_count == 0:
        return []

    query_term_counts = Counter(query_terms)
    unique_query_terms = list(query_term_counts)

    doc_frequency: dict[str, int] = {}
    for term in unique_query_terms:
        doc_frequency[term] = sum(
            1 for term_counts in counts_by_file.values() if term in term_counts
        )

    doc_lengths = {
        file_key: sum(term_counts.values())
        for file_key, term_counts in counts_by_file.items()
    }
    avg_doc_length = sum(doc_lengths.values()) / document_count

    ranked_results = []
    k1 = 1.5
    b = 0.75
    for file_key, term_counts in counts_by_file.items():
        tf_idf_score = 0.0
        term_hits = 0
        unique_matches = 0
        matched_terms = []
        doc_length = doc_lengths[file_key]
        length_norm = 1.0 - b + b * (doc_length / avg_doc_length)
        for term, query_count in query_term_counts.items():
            term_count = term_counts.get(term, 0)
            if term_count <= 0:
                continue

            unique_matches += 1
            term_hits += term_count
            query_weight = 1.0 + math.log(query_count)
            # BM25-like TF normalization keeps term frequency important while
            # reducing the bias toward very long documents.
            tf_component = (term_count * (k1 + 1.0)) / (term_count + k1 * length_norm)
            idf = math.log(
                1.0
                + ((document_count - doc_frequency[term] + 0.5) / (doc_frequency[term] + 0.5))
            )
            tf_idf_score += query_weight * tf_component * idf
            matched_terms.append(f"{term} ({term_count})")

        if tf_idf_score <= 0:
            continue

        coverage = unique_matches / len(unique_query_terms)
        frequency_boost = 1.0 + 0.15 * math.log1p(term_hits)
        score = tf_idf_score * frequency_boost * (1.0 + 0.35 * coverage)
        doc_path = docs_relative_path(file_key)
        ranked_results.append(
            {
                "file": file_key,
                "doc_path": doc_path,
                "score": score,
                "matches": ", ".join(matched_terms),
                "term_hits": term_hits,
                "coverage": coverage,
                "matched_term_count": unique_matches,
                "query_term_count": len(unique_query_terms),
            }
        )

    ranked_results.sort(
        key=lambda result: (-result["score"], -result["term_hits"], result["file"])
    )
    return ranked_results[:limit]


app = Flask(__name__)


@app.route("/docs/")
def view_docs_index():
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    safe_doc_path = safe_doc_path_or_404("index.html")
    return send_from_directory(docs_root, safe_doc_path)


@app.route("/docs/<path:doc_path>")
def view_document(doc_path: str):
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    safe_doc_path = safe_doc_path_or_404(doc_path)
    return send_from_directory(docs_root, safe_doc_path)


@app.route("/", methods = ['GET', 'POST'])
def hello_world():
    query = ""
    results = []
    error = None
    if request.method == 'POST':
        query = request.form.get("query", "").strip()
        if not query:
            error = "Enter a query to search."
        else:
            try:
                counts_by_file = load_index_data()
                results = tf_idf_search(query, counts_by_file)
                query_terms = tokenize_words(query)
                attach_result_snippets(results, query_terms)
            except FileNotFoundError as exc:
                error = str(exc)
    return render_template(
        "index.html",
        query=query,
        results=results,
        error=error,
    )
    
def serve(app):
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, use_reloader=debug_mode)

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python main.py [SUBCOMMAND] [ARGS]")
        usage()
        return
    
    subcommand = sys.argv[1].upper()
    if subcommand == "INDEX":
        if len(sys.argv) < 3:
            print("Usage: python main.py INDEX [folder path]")
            return
        index_file(sys.argv[2])
        return
    if subcommand == "SERVE":
        serve(app)
        return
    usage()

def usage():
    print("SUBCOMMANDS:")
    print("      INDEX:   [folder path]: Process HTML files and generate word counts")
    print("      SERVE: Start the Flask web server")

if __name__ == "__main__":
    main()
