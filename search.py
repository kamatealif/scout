from collections import Counter
import html
import math
import re

import indexer

NORMALIZED_INDEX_CACHE: dict[tuple[int, bool], dict[str, dict[str, int]]] = {}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}


def simple_stem(token: str) -> str:
    if len(token) <= 3:
        return token

    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("xes") and len(token) > 4:
        return token[:-2]
    if token.endswith("ed") and len(token) > 4:
        candidate = token[:-2]
        return candidate if len(candidate) >= 3 else token
    if token.endswith("ing") and len(token) > 5:
        candidate = token[:-3]
        if len(candidate) >= 3:
            if len(candidate) > 3 and candidate[-1] == candidate[-2]:
                candidate = candidate[:-1]
            return candidate
    if token.endswith("ly") and len(token) > 4:
        return token[:-2]
    if token.endswith("ment") and len(token) > 6:
        return token[:-4]
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token


def normalize_token(token: str, use_stemming: bool) -> str:
    normalized = token.lower()
    if use_stemming:
        normalized = simple_stem(normalized)
    return normalized


def prepare_query_terms(
    query: str, use_stemming: bool
) -> tuple[list[str], list[str], list[str]]:
    raw_terms = indexer.tokenize_words(query)
    filtered_terms = [term for term in raw_terms if term not in STOPWORDS]
    normalized_terms = [normalize_token(term, use_stemming) for term in filtered_terms]
    return raw_terms, filtered_terms, normalized_terms


def normalized_index_data(
    counts_by_file: dict[str, dict[str, int]], use_stemming: bool
) -> dict[str, dict[str, int]]:
    if not use_stemming:
        return counts_by_file

    cache_key = (id(counts_by_file), use_stemming)
    cached = NORMALIZED_INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached

    normalized_counts_by_file: dict[str, dict[str, int]] = {}
    for file_key, term_counts in counts_by_file.items():
        aggregated = Counter()
        for term, count in term_counts.items():
            aggregated[normalize_token(term, use_stemming=True)] += count
        normalized_counts_by_file[file_key] = dict(aggregated)

    NORMALIZED_INDEX_CACHE[cache_key] = normalized_counts_by_file
    return normalized_counts_by_file


def section_options_for_index(
    counts_by_file: dict[str, dict[str, int]]
) -> list[dict[str, str]]:
    prefixes = set()
    has_root_docs = False

    for file_key in counts_by_file:
        doc_path = indexer.docs_relative_path(file_key)
        if not doc_path:
            continue
        if "/" in doc_path:
            prefixes.add(doc_path.split("/", 1)[0] + "/")
        else:
            has_root_docs = True

    options = [{"value": "", "label": "All docs"}]
    if has_root_docs:
        options.append({"value": "__root__", "label": "docs/*.html"})
    for prefix in sorted(prefixes):
        options.append({"value": prefix, "label": f"docs/{prefix}*"})
    return options


def filter_index_by_section(
    counts_by_file: dict[str, dict[str, int]], selected_section: str
) -> dict[str, dict[str, int]]:
    if not selected_section:
        return counts_by_file

    filtered_counts: dict[str, dict[str, int]] = {}
    for file_key, term_counts in counts_by_file.items():
        doc_path = indexer.docs_relative_path(file_key)
        if not doc_path:
            continue
        if selected_section == "__root__":
            if "/" not in doc_path:
                filtered_counts[file_key] = term_counts
            continue
        if doc_path.startswith(selected_section):
            filtered_counts[file_key] = term_counts
    return filtered_counts


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

    plain_text = indexer.get_document_text(doc_path)
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


def click_score_boost(click_count: int) -> float:
    if click_count <= 0:
        return 1.0
    return 1.0 + 0.35 * math.log1p(click_count)


def tf_idf_search(
    query: str,
    counts_by_file: dict[str, dict[str, int]],
    limit: int = 20,
    use_stemming: bool = False,
    query_terms: list[str] | None = None,
    click_counts: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    if query_terms is None:
        _, _, query_terms = prepare_query_terms(query, use_stemming=use_stemming)
    if not query_terms:
        return []

    search_counts_by_file = normalized_index_data(
        counts_by_file, use_stemming=use_stemming
    )
    document_count = len(counts_by_file)
    if document_count == 0:
        return []
    if click_counts is None:
        click_counts = indexer.load_click_counts()

    query_term_counts = Counter(query_terms)
    unique_query_terms = list(query_term_counts)
    query_phrase_terms = indexer.tokenize_words(query)
    phrase_regex = None
    if len(query_phrase_terms) >= 2:
        phrase_regex = re.compile(
            r"\b" + r"\s+".join(re.escape(term) for term in query_phrase_terms) + r"\b",
            re.IGNORECASE,
        )

    doc_frequency: dict[str, int] = {}
    for term in unique_query_terms:
        doc_frequency[term] = sum(
            1 for term_counts in search_counts_by_file.values() if term in term_counts
        )

    doc_lengths = {
        file_key: sum(term_counts.values())
        for file_key, term_counts in search_counts_by_file.items()
    }
    avg_doc_length = sum(doc_lengths.values()) / document_count

    ranked_results = []
    k1 = 1.5
    b = 0.75
    for file_key, term_counts in search_counts_by_file.items():
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
        doc_path = indexer.docs_relative_path(file_key)
        click_count = click_counts.get(doc_path, 0) if doc_path else 0
        phrase_hits = 0
        if phrase_regex is not None and doc_path is not None:
            plain_text = indexer.get_document_text(doc_path)
            if plain_text:
                phrase_hits = len(phrase_regex.findall(plain_text))
                if phrase_hits > 0:
                    score *= 1.0 + min(0.5, 0.2 * phrase_hits)
        score *= click_score_boost(click_count)

        ranked_results.append(
            {
                "file": file_key,
                "doc_path": doc_path,
                "score": score,
                "click_count": click_count,
                "matches": ", ".join(matched_terms),
                "term_hits": term_hits,
                "coverage": coverage,
                "matched_term_count": unique_matches,
                "query_term_count": len(unique_query_terms),
                "phrase_hits": phrase_hits,
            }
        )

    ranked_results.sort(
        key=lambda result: (
            -result["score"],
            -result["click_count"],
            -result["term_hits"],
            result["file"],
        )
    )
    return ranked_results[:limit]
