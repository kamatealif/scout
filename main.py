from html.parser import HTMLParser
import os 

class MyHTMLParser(HTMLParser):
    def handle_data(self,data):
        print(f"data: {data}")


def main():
    parser = MyHTMLParser()
    for dirpath, dirnames, filenames in os.walk('docs'):
        for f in filenames:
            if f.endswith('.html'):
                print("Working with {}".format(os.path.join(dirpath,f)))
                with open(os.path.join(dirpath,f), 'r') as html_file:
                    parser.feed(html_file.read())
            if f.endswith('.xhtl'):
                print("working with {}".format(os.path.join(dirpath, f)))
                with open(os.path.join(dirpath,f),'r') as xhtml_file:
                    parser.feed(xhtml_file.read())
        

if __name__ == "__main__":
    main()
