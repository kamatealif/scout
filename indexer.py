from collections import Counter
from html.parser import HTMLParser
import json
import os
import re

INDEX_FILE = "word_counts.json"
LEGACY_INDEX_FILE = "index.json"
CLICK_COUNT_FILE = "click_counts.json"
DEFAULT_DOCS_DIR = "docs"
WORD_REGEX = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
INDEX_CACHE: dict[str, dict[str, int]] | None = None
CLICK_COUNT_CACHE: dict[str, int] | None = None
DOC_TEXT_CACHE: dict[str, str] = {}


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
        return [
            (match.lastgroup, match.group())
            for match in self.TOKEN_REGEX.finditer(text)
        ]

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


def tokenize_words(text: str) -> list[str]:
    return [match.group().lower() for match in WORD_REGEX.finditer(text)]


def process_html_file(file_path: str) -> dict[str, int]:
    parser = MyHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return dict(parser.word_counts)


def index_file(file_path: str, output_file: str = INDEX_FILE) -> dict[str, dict[str, int]]:
    global INDEX_CACHE, DOC_TEXT_CACHE
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
    INDEX_CACHE = counts_by_file
    DOC_TEXT_CACHE = {}
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


def load_click_counts() -> dict[str, int]:
    global CLICK_COUNT_CACHE
    if CLICK_COUNT_CACHE is not None:
        return CLICK_COUNT_CACHE

    if not os.path.exists(CLICK_COUNT_FILE):
        CLICK_COUNT_CACHE = {}
        return CLICK_COUNT_CACHE

    with open(CLICK_COUNT_FILE, "r", encoding="utf-8") as source_file:
        raw_click_counts = json.load(source_file)

    CLICK_COUNT_CACHE = {
        str(doc_path): max(0, int(count))
        for doc_path, count in raw_click_counts.items()
    }
    return CLICK_COUNT_CACHE


def save_click_counts(click_counts: dict[str, int]) -> dict[str, int]:
    global CLICK_COUNT_CACHE
    normalized_counts: dict[str, int] = {}
    for doc_path, count in click_counts.items():
        normalized_count = max(0, int(count))
        if normalized_count > 0:
            normalized_counts[str(doc_path)] = normalized_count

    with open(CLICK_COUNT_FILE, "w", encoding="utf-8") as json_file:
        json.dump(normalized_counts, json_file, indent=2, sort_keys=True)

    CLICK_COUNT_CACHE = normalized_counts
    return CLICK_COUNT_CACHE


def get_click_count(doc_path: str) -> int:
    return load_click_counts().get(doc_path, 0)


def increment_click_count(doc_path: str) -> int:
    click_counts = load_click_counts()
    updated_count = click_counts.get(doc_path, 0) + 1
    click_counts[doc_path] = updated_count
    save_click_counts(click_counts)
    return updated_count


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


def resolve_doc_path(doc_path: str) -> str:
    docs_root = os.path.abspath(DEFAULT_DOCS_DIR)
    normalized = os.path.normpath(doc_path).replace("\\", "/")
    if normalized in (".", ""):
        normalized = "index.html"

    if normalized == ".." or normalized.startswith("../"):
        raise FileNotFoundError(normalized)

    absolute_file_path = os.path.abspath(os.path.join(docs_root, normalized))
    try:
        if os.path.commonpath([docs_root, absolute_file_path]) != docs_root:
            raise FileNotFoundError(normalized)
    except ValueError as exc:
        raise FileNotFoundError(normalized) from exc

    if not os.path.isfile(absolute_file_path):
        raise FileNotFoundError(normalized)

    return normalized


def extract_plain_text_from_html(file_path: str) -> str:
    parser = PlainTextHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return parser.text()


def get_document_text(doc_path: str) -> str:
    cached_text = DOC_TEXT_CACHE.get(doc_path)
    if cached_text is not None:
        return cached_text

    full_path = os.path.join(DEFAULT_DOCS_DIR, doc_path)
    if not os.path.isfile(full_path):
        DOC_TEXT_CACHE[doc_path] = ""
        return ""

    extracted = extract_plain_text_from_html(full_path)
    DOC_TEXT_CACHE[doc_path] = extracted
    return extracted
