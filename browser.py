import socket
import sys
import ssl
import tkinter
import tkinter.font
import re

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 70

class Text:
    def __init__(self, text):
        self.text = text

class Tag:
    def __init__(self, tag):
        self.tag = tag

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


def lex(body):
  out = []
  text = ""
  in_tag = False
  position = 0

  def _get_element(end_char):
    return body[position:body.find(end_char, position + 1)]

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

  while position < len(body):
    char = body[position]
    position += 1

    if char == "<":
      in_tag = True
      if text:
        out.append(Text(text))

      text = ""

    elif char == ">":
      in_tag = False
      out.append(Tag(text))
      text = ""

    else:
      if (not in_tag and char == "&"):
        entity_symbol, skip_chars = get_entity_symbol()
        position += skip_chars
        text += entity_symbol
      else:
        text += char

  if not in_tag and text:
    out.append(Text(text))

  return out

class Layout:
  def __init__(self, tokens):
    self.display_list = []
    self.line = []
    self.cursor_x = HSTEP
    self.cursor_y = VSTEP
    self.weight = "normal"
    self.style = "roman"
    self.size = 16
    self.in_body = False
    for token in tokens:
      self.token(token)

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
    font = tkinter.font.Font(
      size=self.size,
      weight=self.weight,
      slant=self.style,
    )
    for word in re.findall(r'\S+|\n', token.text):
      # if word == "\n":
      #   self.cursor_y += VSTEP * 2.0
      #   self.cursor_x = HSTEP

      w = font.measure(word)
      if self.cursor_x + w > WIDTH - HSTEP:
        self.flush()
  
      self.line.append((self.cursor_x, word, font))
      self.cursor_x += w + font.measure(" ")

  def token(self, token):
    if isinstance(token, Text):
      if self.in_body: self.text(token)
    elif token.tag.startswith("body"):
      self.in_body = True
    elif token.tag == "/body":
      self.in_body = False
    elif token.tag in ["em", "i"]:
      self.style = "italic"
    elif token.tag in ["/em", "/i"]:
      self.style = "roman"
    elif token.tag in ["b", "strong"]:
      self.weight = "bold"
    elif token.tag in ["/b", "/strong"]:
      self.weight = "normal"
    elif token.tag == "small":
      self.size -= 2
    elif token.tag == "/small":
      self.size += 2
    elif token.tag == "big":
      self.size += 4
    elif token.tag == "/big":
      self.size -= 4
    elif token.tag == "br":
      self.flush()
    elif token.tag == "/p":
      self.flush()
      self.cursor_y += VSTEP

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
    tokens = lex(body)
    self.display_list = Layout(tokens).display_list
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
