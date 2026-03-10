import os

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

import indexer
import search

app = Flask(__name__)


@app.route("/docs/")
def view_docs_index():
    docs_root = os.path.abspath(indexer.DEFAULT_DOCS_DIR)
    try:
        safe_doc_path = indexer.resolve_doc_path("index.html")
    except FileNotFoundError:
        abort(404)
    return send_from_directory(docs_root, safe_doc_path)


@app.route("/docs/<path:doc_path>")
def view_document(doc_path: str):
    docs_root = os.path.abspath(indexer.DEFAULT_DOCS_DIR)
    try:
        safe_doc_path = indexer.resolve_doc_path(doc_path)
    except FileNotFoundError:
        abort(404)
    return send_from_directory(docs_root, safe_doc_path)


@app.route("/result/<path:doc_path>")
def open_result(doc_path: str):
    try:
        safe_doc_path = indexer.resolve_doc_path(doc_path)
    except FileNotFoundError:
        abort(404)

    indexer.increment_click_count(safe_doc_path)
    return redirect(url_for("view_document", doc_path=safe_doc_path))


@app.route("/", methods=["GET", "POST"])
def hello_world():
    query = ""
    results = []
    error = None
    use_stemming = False
    selected_section = ""
    selected_section_label = "All docs"
    section_options = [{"value": "", "label": "All docs"}]
    counts_by_file = None

    try:
        counts_by_file = indexer.load_index_data()
        section_options = search.section_options_for_index(counts_by_file)
    except FileNotFoundError as exc:
        if request.method == "POST":
            error = str(exc)

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        use_stemming = request.form.get("stemming") == "1"
        selected_section = request.form.get("section", "")
        section_labels = {
            option["value"]: option["label"]
            for option in section_options
        }
        if selected_section not in section_labels:
            selected_section = ""
        selected_section_label = section_labels.get(selected_section, "All docs")

        if not query:
            error = "Enter a query to search."
        elif counts_by_file is not None:
            filtered_counts_by_file = search.filter_index_by_section(
                counts_by_file, selected_section
            )
            _, snippet_terms, normalized_query_terms = search.prepare_query_terms(
                query, use_stemming=use_stemming
            )
            if not normalized_query_terms:
                error = "Query contains only stopwords. Try more specific words."
                results = []
            else:
                results = search.tf_idf_search(
                    query,
                    filtered_counts_by_file,
                    use_stemming=use_stemming,
                    query_terms=normalized_query_terms,
                )
                search.attach_result_snippets(results, snippet_terms)

    return render_template(
        "index.html",
        query=query,
        results=results,
        use_stemming=use_stemming,
        section_options=section_options,
        selected_section=selected_section,
        selected_section_label=selected_section_label,
        error=error,
    )


def serve(flask_app=app):
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    flask_app.run(debug=debug_mode, use_reloader=debug_mode)
