from html.parser import HTMLParser
from collections import Counter
import json
import os
import re


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


def process_html_file(file_path: str) -> dict[str, int]:
    parser = MyHTMLParser()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as source_file:
        parser.feed(source_file.read())
    parser.close()
    return dict(parser.word_counts)

def index_file(file_path: str) -> dict[str, int]:
    counts_by_file = {}
    for dirpath, _, filenames in os.walk(file_path):
        for filename in filenames:
            if not filename.endswith((".html", ".xhtl", ".xhtml")):
                continue
            file_path = os.path.join(dirpath, filename)
            file_key = f"{dirpath}/{filename}"
            print("Working with {}".format(file_path))
            counts_by_file[file_key] = process_html_file(file_path)
        
    output_file = "index.json"
    with open(output_file, "w", encoding="utf-8") as json_file:
        json.dump(counts_by_file, json_file, indent=2, sort_keys=True)

    print("Saved word counts to {}".format(output_file))
    
    
def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python main.py [SUBCOMMAND] [ARGS]")
        usage()
        return
    
    subcommand = sys.argv[1].upper()
    if subcommand == 'INDEX':
        if len(sys.argv) < 3:
            print("Usage: python main.py INDEX [folder path]")
            return
        index_file(sys.argv[2])
        
    if subcommand == 'SERVE':
        print("Serve subcommand is not implemented yet.")
        # serve()

def usage():
    print("SUBCOMMANDS:")
    print("      INDEX:   [folder path]: Process HTML files and generate word counts")
    print("    [SERVE]: Start a web server to serve the generated word counts (not implemented yet)")

if __name__ == "__main__":
    usage()
    # main()
