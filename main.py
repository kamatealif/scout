from html.parser import HTMLParser


class MyHTMLParser(HTMLParser):
    def handle_data(self,data):
        print(f"data: {data}")


def main():
    parser = MyHTMLParser()
    with open('docs/library/csv.html','r') as file:
        reader = file.read();
        parser.feed(reader)


if __name__ == "__main__":
    main()
