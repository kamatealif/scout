import os
import re
import tempfile
import unittest

import main


class ScoutAppTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.docs_dir = os.path.join(self.tempdir.name, "docs")
        os.makedirs(os.path.join(self.docs_dir, "library"), exist_ok=True)
        os.makedirs(os.path.join(self.docs_dir, "tutorial"), exist_ok=True)

        self._write_doc(
            "index.html",
            "Home page for the documentation search test corpus.",
        )
        self._write_doc(
            "library/asyncio.html",
            (
                "The event loop coordinates asyncio work. "
                "An event loop handles callbacks and sockets. "
                "A stable event loop keeps services responsive."
            ),
        )
        self._write_doc(
            "tutorial/terms.html",
            (
                "An event can trigger a callback. "
                "Each loop iteration runs separately. "
                "This page mentions event and loop often, but not as one phrase."
            ),
        )
        self._write_doc(
            "library/tasks.html",
            (
                "Run one task. Another task can run later. "
                "Task orchestration helps async programs."
            ),
        )

        self.original_docs_dir = main.DEFAULT_DOCS_DIR
        self.original_index_cache = main.INDEX_CACHE
        self.original_normalized_index_cache = main.NORMALIZED_INDEX_CACHE
        self.original_doc_text_cache = main.DOC_TEXT_CACHE
        self.original_testing = main.app.config.get("TESTING", False)

        main.DEFAULT_DOCS_DIR = self.docs_dir
        main.INDEX_CACHE = self._build_index()
        main.NORMALIZED_INDEX_CACHE = {}
        main.DOC_TEXT_CACHE = {}
        main.app.config["TESTING"] = True
        self.client = main.app.test_client()

    def tearDown(self):
        main.DEFAULT_DOCS_DIR = self.original_docs_dir
        main.INDEX_CACHE = self.original_index_cache
        main.NORMALIZED_INDEX_CACHE = self.original_normalized_index_cache
        main.DOC_TEXT_CACHE = self.original_doc_text_cache
        main.app.config["TESTING"] = self.original_testing
        self.tempdir.cleanup()

    def _write_doc(self, relative_path: str, content: str):
        full_path = os.path.join(self.docs_dir, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        html_doc = (
            "<!doctype html>"
            "<html><body>"
            '<div class="sidebar">navigation noise</div>'
            f'<div role="main">{content}</div>'
            "</body></html>"
        )
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(html_doc)

    def _build_index(self) -> dict[str, dict[str, int]]:
        counts_by_file: dict[str, dict[str, int]] = {}
        for dirpath, _, filenames in os.walk(self.docs_dir):
            for filename in filenames:
                if not filename.endswith(".html"):
                    continue
                full_path = os.path.join(dirpath, filename)
                file_key = f"{dirpath}/{filename}"
                counts_by_file[file_key] = main.process_html_file(full_path)
        return counts_by_file

    def test_prepare_query_terms_filters_stopwords_and_applies_stemming(self):
        raw_terms, filtered_terms, normalized_terms = main.prepare_query_terms(
            "The runners are running quickly", use_stemming=True
        )

        self.assertEqual(raw_terms, ["the", "runners", "are", "running", "quickly"])
        self.assertEqual(filtered_terms, ["runners", "running", "quickly"])
        self.assertEqual(normalized_terms, ["runner", "run", "quick"])

    def test_tf_idf_search_prioritizes_exact_phrase_match(self):
        _, _, normalized_terms = main.prepare_query_terms(
            "event loop", use_stemming=False
        )

        results = main.tf_idf_search(
            "event loop",
            main.INDEX_CACHE,
            use_stemming=False,
            query_terms=normalized_terms,
        )

        self.assertGreater(len(results), 1)
        self.assertEqual(results[0]["doc_path"], "library/asyncio.html")
        self.assertGreater(results[0]["phrase_hits"], 0)

    def test_tf_idf_search_with_stemming_matches_word_variants(self):
        _, _, normalized_terms = main.prepare_query_terms(
            "running tasks", use_stemming=True
        )

        results = main.tf_idf_search(
            "running tasks",
            main.INDEX_CACHE,
            use_stemming=True,
            query_terms=normalized_terms,
        )

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["doc_path"], "library/tasks.html")

    def test_index_route_renders_search_page(self):
        response = self.client.get("/")
        try:
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("Documentation Search", html)
            self.assertIn('name="section"', html)
        finally:
            response.close()

    def test_index_route_post_filters_results_by_section(self):
        response = self.client.post(
            "/",
            data={"query": "event loop", "section": "library/"},
        )
        try:
            html = response.get_data(as_text=True)
            doc_hrefs = re.findall(r'href="(/docs/[^"]+)"', html)

            self.assertEqual(response.status_code, 200)
            self.assertIn("/docs/library/asyncio.html", doc_hrefs)
            self.assertTrue(all(href.startswith("/docs/library/") for href in doc_hrefs))
            self.assertIn('class="snippet"', html)
        finally:
            response.close()

    def test_docs_route_serves_document(self):
        response = self.client.get("/docs/library/asyncio.html")
        try:
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("event loop coordinates asyncio work", html.lower())
        finally:
            response.close()

    def test_docs_route_blocks_path_traversal(self):
        response = self.client.get("/docs/%2e%2e/README.md")
        try:
            self.assertEqual(response.status_code, 404)
        finally:
            response.close()


if __name__ == "__main__":
    unittest.main()
