# Scout

A local documentation search app built with Flask.

It indexes HTML files (for example, the `docs/` folder), then lets you search and open relevant pages in the browser.

## Features

- HTML document indexing into `word_counts.json`
- Query-based document ranking (TF-IDF/BM25-style scoring)
- Clickable search results that open the full document page
- Minimal web UI for quick local search

## 1. Clone This Repo Locally

```bash
git clone <your-repo-url> scout
cd scout
```

If you already cloned it, just `cd` into the project folder.

## 2. Setup

Python requirement: **3.13+**

### Option A: Using `uv` (recommended if you already use it)

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Option B: Using `venv` + `pip`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 3. Build the Search Index

Index a folder containing `.html`, `.xhtml`, or `.xhtl` files:

```bash
python main.py INDEX docs
```

This generates/updates:

- `word_counts.json` (main index file)

## 4. Run the App

```bash
python main.py SERVE
```

Then open:

- `http://127.0.0.1:5000`

## 5. How to Use

1. Enter a query in the search box.
2. Submit search.
3. Click any result link to open the full documentation page.

## How It Works

### Indexing phase

- `index_file(...)` walks the target folder recursively.
- Each HTML file is parsed by `MyHTMLParser`.
- Only word tokens are counted and normalized to lowercase.
- Counts are stored per document in `word_counts.json`.

### Search phase

- Query text is tokenized with the same word tokenizer.
- For each document:
  - Term frequency is computed from index counts.
  - IDF is computed across all indexed documents.
  - A BM25-style normalization reduces long-document bias.
- Results are sorted by relevance and returned to the template.

### Document serving

- Search results include a path to the matched doc.
- `/docs/<path>` safely serves files from the local `docs/` directory.
- Clicking a result opens that exact documentation page.

## Common Commands

Rebuild index:

```bash
python main.py INDEX docs
```

Start server:

```bash
python main.py SERVE
```

Enable Flask debug mode:

```bash
FLASK_DEBUG=1 python main.py SERVE
```
