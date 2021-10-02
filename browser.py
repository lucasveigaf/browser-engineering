import socket
import sys
import ssl
import tkinter
import tkinter.font
import re

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 70

FONTS = {}

def get_font(size, weight, slant):
    key = (size, weight, slant)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=slant)
        FONTS[key] = font
    return FONTS[key]

class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.children = []
        self.parent = parent
        self.attributes = attributes

    def __repr__(self):
      return "<" + self.tag + ">"

def request(url, redirectcount = 0):
    scheme, url = url.split("://", 1)
    host, path = url.split("/", 1)
    path = "/" + path
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    assert scheme in ["http", "https"], "Unknown Scheme {}".format(scheme)
    port = 80 if scheme == "http" else 443
    if scheme == "https":
      ctx = ssl.create_default_context()
      s = ctx.wrap_socket(s, server_hostname=host)
  
    if ":" in host:
      host, port = host.split(":", 1)
      port = int(port)

    s.connect((host, port))
    bget = bytes(f"GET {path} HTTP/1.1\r\n", encoding="utf-8")
    bhost = bytes(f"Host: {host}\r\n", encoding="utf-8")
    bconnection = bytes(f"Connection: close\r\n", encoding="utf-8")
    buseragent = bytes(f"User-Agent: pybrowser\r\n\r\n", encoding="utf-8")
    s.send(bget + bhost + bconnection + buseragent)
    response = s.makefile("r", encoding="utf8", newline="\r\n")
    statusline = response.readline()
    version, status, explanation = statusline.split(" ", 2)
    assert status == "200" or status.startswith("3"), "{} - {}: {}".format(version, status, explanation)
    headers = {}
    while True:
      line = response.readline()
      if line == "\r\n": break
      header, value = line.split(":", 1)
      headers[header.lower()] = value.strip()

    if status.startswith("3"):
      s.close()
      assert redirectcount < 5, "Redirect limit reached"
      return request(headers["location"], redirectcount + 1)

    body = response.read()
    s.close()
    return headers, body

def print_tree(node, indent=0):
  print(" " * indent, node)
  for child in node.children:
    print_tree(child, indent + 2)

class HTMLParser:
  SELF_CLOSING_TAGS = [
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
  ]

  HEAD_TAGS = [
      "base", "basefont", "bgsound", "noscript",
      "link", "meta", "title", "style", "script",
  ]

  def __init__(self, body):
      self.body = body
      self.unfinished = []

  def implicit_tags(self, tag):
    while True:
      open_tags = [node.tag for node in self.unfinished]
      if open_tags == [] and tag != "html":
        self.add_tag("html")
      elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
        if tag in self.HEAD_TAGS:
          self.add_tag("head")
        else:
          self.add_tag("body")
      elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
        self.add_tag("/head")
      else:
        break

  def add_text(self, text):
    if text.isspace():
      return
    
    self.implicit_tags(None)
    parent = self.unfinished[-1]
    node = Text(text, parent)
    parent.children.append(node)

  def get_attributes(self, text):
    parts = text.split()
    tag = parts[0].lower()
    attributes = {}
    for attrpair in parts[1:]:
      if "=" in attrpair:
        key, value = attrpair.split("=", 1)
        if len(value) > 2 and value[0] in ["'", "\""]:
          value = value[1:-1]
        attributes[key.lower()] = value
      else:
        attributes[attrpair.lower()] = ""
  
    return tag, attributes

  def add_tag(self, tag):
    tag, attributes = self.get_attributes(tag)
    if tag.startswith("!"):
      return

    self.implicit_tags(tag)
    if tag.startswith("/"):
      if len(self.unfinished) == 1:
        return

      node = self.unfinished.pop()
      parent = self.unfinished[-1]
      parent.children.append(node)

    elif tag in self.SELF_CLOSING_TAGS:
      parent = self.unfinished[-1]
      node = Element(tag, attributes, parent)
      parent.children.append(node)

    else:
      parent = self.unfinished[-1] if self.unfinished else None
      node = Element(tag, attributes, parent)
      self.unfinished.append(node)

  def finish(self):
    while len(self.unfinished) > 1:
      node = self.unfinished.pop()
      parent = self.unfinished[-1]
      parent.children.append(node)

    return self.unfinished.pop()

  def parse(self):
    text = ""
    in_tag = False
    position = 0

    def _get_element(end_char):
      return self.body[position:self.body.find(end_char, position + 1)]

    def get_entity_symbol():
      entity = _get_element(";")
      parsed_entity = ""
      if entity == "amp":
        parsed_entity = "&"
      elif entity == "lt":
        parsed_entity = "<"
      elif entity == "gt":
        parsed_entity = ">"

      return parsed_entity, len(entity) + 1

    while position < len(self.body):
      char = self.body[position]
      position += 1

      if char == "<":
        in_tag = True
        if text:
          self.add_text(text)

        text = ""

      elif char == ">":
        in_tag = False
        self.add_tag(text)
        text = ""

      else:
        if (not in_tag and char == "&"):
          entity_symbol, skip_chars = get_entity_symbol()
          position += skip_chars
          text += entity_symbol
        else:
          text += char

    if not in_tag and text:
      self.add_text(text)

    return self.finish()

class Layout:
  def __init__(self, node_tree):
    self.display_list = []
    self.line = []
    self.cursor_x = HSTEP
    self.cursor_y = VSTEP
    self.weight = "normal"
    self.style = "roman"
    self.size = 16
    self.in_body = False
    self.recurse(node_tree)

    self.flush()

  def flush(self):
    if not self.line: return
    metrics = [font.metrics() for x, word, font in self.line]
    max_ascent = max([metric["ascent"] for metric in metrics])
    baseline = self.cursor_y + 1.2 * max_ascent
    for x, word, font in self.line:
      y = baseline - font.metrics("ascent")
      self.display_list.append((x, y, word, font))

    self.cursor_x = HSTEP
    self.line = []
    max_descent = max([metric["descent"] for metric in metrics])
    self.cursor_y = baseline + 1.2 * max_descent

  def text(self, token):
    font = get_font(self.size, self.weight, self.style)
    for word in re.findall(r'\S+|\n', token.text):
      # if word == "\n":
      #   self.cursor_y += VSTEP * 2.0
      #   self.cursor_x = HSTEP

      w = font.measure(word)
      if self.cursor_x + w > WIDTH - HSTEP:
        self.flush()
  
      self.line.append((self.cursor_x, word, font))
      self.cursor_x += w + font.measure(" ")

  def open_tag(self, tag):
    if tag in ["em", "i"]:
      self.style = "italic"
    elif tag in ["b", "strong"]:
      self.weight = "bold"
    elif tag == "small":
      self.size -= 2
    elif tag == "big":
      self.size += 4
    elif tag == "br":
      self.flush()

  def close_tag(self, tag):
    if tag in ["em", "i"]:
      self.style = "roman"
    elif tag in ["b", "strong"]:
      self.weight = "normal"
    elif tag == "small":
      self.size += 2
    elif tag == "big":
      self.size -= 4
    elif tag == "p":
      self.flush()
      self.cursor_y += VSTEP

  def recurse(self, tree):
    if isinstance(tree, Text):
      self.text(tree)
    else:
      self.open_tag(tree.tag)
      for child in tree.children:
        self.recurse(child)

      self.close_tag(tree.tag)

class Browser:
  def __init__(self):
    self.window = tkinter.Tk()
    self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
    self.canvas.pack()
    self.scroll = 0
    self.window.bind("<Down>", self.scrolldown)
    self.window.bind("<Up>", self.scrollup)
    self.window.bind("<MouseWheel>", self.handle_wheel)

  def handle_wheel(self, e):
    if (e.delta < 1):
      self.scrolldown(e)
    else:
      self.scrollup(e)

  def scrolldown(self, e):
    self.scroll += SCROLL_STEP
    self.draw()

  def scrollup(self, e):
    if self.scroll - SCROLL_STEP < 0:
      self.scroll = 0
    else:
      self.scroll -= SCROLL_STEP
    self.draw()

  def load(self, url):
    headers, body = request(url)
    self.nodes = HTMLParser(body).parse()
    self.display_list = Layout(self.nodes).display_list
    self.draw()

  def draw(self):
    self.canvas.delete("all")
    for x, y, c, f in self.display_list:
      if y > self.scroll + HEIGHT: continue
      if y + VSTEP < self.scroll: continue
      self.canvas.create_text(x, y - self.scroll, text=c, font=f, anchor='nw')


if __name__ == "__main__":
    Browser().load(sys.argv[1])
    tkinter.mainloop()
