#!/usr/bin/env python3
"""Dependency-free, deterministic Markdown-to-PDF skeleton builder."""
from __future__ import annotations
import argparse, importlib.util, re, struct, sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
W,H=612,792; LEFT,RIGHT,TOP,BOTTOM=58,58,60,52
URL_RE=re.compile(r'\[([^]]+)\]\(([^)]+)\)|(https?://[^\s<>]+)')
IMAGE_RE=re.compile(r'^!\[([^]]*)\]\(([^)]+\.png)\)$', re.IGNORECASE)
LINK_BLUE=(0,0,238/255)

def load_manifest():
 spec=importlib.util.spec_from_file_location('manifest',ROOT/'book_manifest.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod.BOOKS

def expected(cfg,lang):
 return ([ROOT/'frontmatter'/lang/x for x in cfg['frontmatter']]+[ROOT/'chapters'/lang/x for x in cfg['chapters']]+[ROOT/'appendix'/lang/x for x in cfg['appendices']])

def validate(cfg,lang):
 files=expected(cfg,lang); missing=[str(x.relative_to(ROOT)) for x in files if not x.is_file()]
 if missing: raise SystemExit('Build validation failed: missing required canonical file(s):\n  - '+'\n  - '.join(missing))
 if len(cfg['chapters'])!=22: raise SystemExit(f"Build validation failed: expected 22 chapters, found {len(cfg['chapters'])}")
 for f in files:
  if not f.read_text(encoding='utf-8').lstrip().startswith('# '): raise SystemExit(f'Build validation failed: {f.relative_to(ROOT)} needs one level-1 title')
 return files

def esc(s): return s.replace('\\','\\\\').replace('(','\\(').replace(')','\\)').replace('\r','').encode('cp1252','replace').decode('latin1')
def clean(s): return re.sub(r'[*_`]', '', s)
def plain(s): return clean(URL_RE.sub(lambda m:m.group(1) or m.group(3),s)).strip()
# Character widths from Adobe's Helvetica and Helvetica-Bold AFM files.  PDF
# base-14 font widths are expressed in thousandths of an em.  The renderer uses
# WinAnsiEncoding, so accented Latin letters have the width of their underlying
# Helvetica glyph rather than an estimated average-character width.
_HELVETICA_ASCII=(
 278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,
 556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,
 1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,
 667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,
 333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,
 556,556,333,500,278,556,500,722,500,500,500,334,260,334,584)
_HELVETICA_BOLD_ASCII=(
 278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,
 556,556,556,556,556,556,556,556,556,556,333,333,584,584,584,611,
 975,722,722,722,722,667,611,778,722,278,556,722,611,833,722,778,
 667,778,722,667,611,722,667,944,667,667,611,333,278,333,584,556,
 333,556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,
 611,611,389,556,333,611,556,778,556,556,500,389,280,389,584)
_EXTRA_WIDTHS={
 '€':556,'‚':222,'ƒ':556,'„':333,'…':1000,'†':556,'‡':556,'ˆ':333,
 '‰':1000,'Š':667,'‹':333,'Œ':1000,'Ž':611,'‘':222,'’':222,'“':333,
 '”':333,'•':350,'–':556,'—':1000,'˜':333,'™':1000,'š':500,'›':333,
 'œ':944,'ž':500,'Ÿ':667,'¡':333,'¿':611,
}
_EXTRA_BOLD_WIDTHS={**_EXTRA_WIDTHS,'‚':278,'„':500,'Š':667,'‹':333,
 'Œ':1000,'‘':278,'’':278,'“':500,'”':500,'•':350,'š':556,'œ':944}
_BASE_LETTER={
 **{c:'A' for c in 'ÀÁÂÃÄÅ'},**{c:'a' for c in 'àáâãäå'},
 'Ç':'C','ç':'c',**{c:'E' for c in 'ÈÉÊË'},**{c:'e' for c in 'èéêë'},
 **{c:'I' for c in 'ÌÍÎÏ'},**{c:'i' for c in 'ìíîï'},'Ð':'D','ð':'d',
 'Ñ':'N','ñ':'n',**{c:'O' for c in 'ÒÓÔÕÖØ'},**{c:'o' for c in 'òóôõöø'},
 **{c:'U' for c in 'ÙÚÛÜ'},**{c:'u' for c in 'ùúûü'},'Ý':'Y','ý':'y','ÿ':'y',
 'Þ':'P','þ':'p',
}
_EXTRA_WIDTHS.update({'Æ':1000,'æ':889,'ß':611})
_EXTRA_BOLD_WIDTHS.update({'Æ':1000,'æ':889,'ß':611})
def glyph_width(char,bold=False):
 table=_HELVETICA_BOLD_ASCII if bold else _HELVETICA_ASCII
 if ' '<=char<='~': return table[ord(char)-32]
 char=_BASE_LETTER.get(char,char)
 if ' '<=char<='~': return table[ord(char)-32]
 return (_EXTRA_BOLD_WIDTHS if bold else _EXTRA_WIDTHS).get(char,556)
def width(s,size,bold=False): return sum(glyph_width(c,bold) for c in s)*size/1000
def wrap(s,size,maxw,bold=False):
 words=s.split(); out=[]; cur=''
 for word in words:
  nxt=(cur+' '+word).strip()
  if cur and width(plain(nxt),size,bold)>maxw: out.append(cur); cur=word
  else: cur=nxt
  # A single unusually long token must not cross the right margin.
  while width(plain(cur),size,bold)>maxw:
   cut=max(i for i in range(1,len(cur)+1) if width(plain(cur[:i]),size,bold)<=maxw)
   out.append(cur[:cut]); cur=cur[cut:]
 if cur: out.append(cur)
 return out or ['']

def wrap_spans(spans,size,maxw):
 """Return visual lines and linked character ranges for styled Markdown spans."""
 chars=[]
 for text,link in spans:
  chars.extend((c,link) for c in text)
 # Markdown paragraph whitespace becomes one ordinary ASCII space.
 normalized=[]; pending_space=False
 for char,link in chars:
  if char.isspace(): pending_space=bool(normalized); continue
  if pending_space: normalized.append((' ',None)); pending_space=False
  normalized.append((char,link))
 lines=[]; line=[]
 # Keep the link metadata while grouping the normalized characters into words.
 tokens=[]; token=[]
 for item in normalized:
  if item[0]==' ':
   if token: tokens.append(token); token=[]
  else: token.append(item)
 if token: tokens.append(token)
 for token in tokens:
  candidate=line+([(' ',None)] if line else [])+token
  if line and width(''.join(c for c,_ in candidate),size)>maxw:
   lines.append(line); line=[]
  if not line and width(''.join(c for c,_ in token),size)>maxw:
   part=[]
   for item in token:
    if part and width(''.join(c for c,_ in part+[item]),size)>maxw:
     lines.append(part); part=[]
    part.append(item)
   line=part
  else: line=line+([(' ',None)] if line else [])+token
 if line: lines.append(line)
 result=[]
 for items in lines or [[]]:
  text=''.join(c for c,_ in items); runs=[]; start=0
  while start<len(items):
   link=items[start][1]; end=start+1
   while end<len(items) and items[end][1]==link: end+=1
   if link: runs.append((start,end,link))
   start=end
  result.append((text,runs))
 return result
@dataclass
class Page:
 head:str; ops:list[str]=field(default_factory=list); links:list[tuple]=field(default_factory=list); images:dict[Path,str]=field(default_factory=dict); destinations:list[tuple[str,float]]=field(default_factory=list)
class Renderer:
 def __init__(self,title,lang,files):
  self.title=title; self.lang=lang; self.pages=[]; self.page=None; self.y=0; self.toc=False
  appendix_slugs=['glossary','certification-roadmap','physical-preparation','family-guide','master-bibliography','source-notes']
  self.file_dest={}
  chapter_no=appendix_no=0
  for path in files:
   if path.parent.parent.name=='chapters': dest=f'chapter-{chapter_no:02d}'; chapter_no+=1
   elif path.parent.parent.name=='appendix': dest=f'appendix-{appendix_slugs[appendix_no]}'; appendix_no+=1
   else: dest='frontmatter-'+path.stem.lower().replace('_','-')
   self.file_dest[path.resolve()]=dest
 def new(self,head=''):
  self.page=Page(head); self.pages.append(self.page); self.y=H-TOP
 def line(self,text,size=10.5,bold=False,indent=0,url=None,gap=14):
  if self.y-gap<BOTTOM: self.new(self.page.head)
  font='F2' if bold else 'F1'; x=LEFT+indent
  self.page.ops.append(f'BT /{font} {size:.1f} Tf {x:.1f} {self.y:.1f} Td ({esc(plain(text))}) Tj ET')
  if url: self.page.links.append((x,self.y-2,min(W-RIGHT,x+width(plain(text),size,bold)),self.y+size,'uri',url))
  self.y-=gap
 def markdown_spans(self,text):
  """Convert supported Markdown links and bare URLs to text/link spans."""
  spans=[]; pos=0
  for m in URL_RE.finditer(text):
   spans.append((clean(text[pos:m.start()]),None))
   label=m.group(1) or m.group(3); target=m.group(2) or m.group(3)
   # Sentence punctuation is not part of a bare URL.
   if not m.group(1):
    clean_url=target.rstrip('.,;:)'); suffix=target[len(clean_url):]; target=clean_url
   else: suffix=''
   if target.startswith(('http://','https://')): link=('uri',target)
   else:
    resolved=(Path(target.split('#',1)[0]) if target else Path())
    candidate=(getattr(self,'source_path',ROOT)/resolved).resolve() if target else None
    link=('goto',self.file_dest.get(candidate)) if candidate in self.file_dest else None
   spans.append((clean(label),link)); spans.append((suffix,None)); pos=m.end()
  spans.append((clean(text[pos:]),None))
  return spans
 def styled_line(self,text,runs,x,size,bold=False):
  """Render one measured line, changing color without resetting text position."""
  font='F2' if bold else 'F1'; parts=[]; pos=0
  for start,end,link in runs:
   if start>pos: parts.append(f'0 g ({esc(text[pos:start])}) Tj')
   parts.append(f'{LINK_BLUE[0]:.3f} {LINK_BLUE[1]:.3f} {LINK_BLUE[2]:.3f} rg ({esc(text[start:end])}) Tj')
   link_x=x+width(text[:start],size,bold)
   self.page.links.append((link_x,self.y-2,link_x+width(text[start:end],size,bold),self.y+size,*link))
   pos=end
  if pos<len(text) or not parts: parts.append(f'0 g ({esc(text[pos:])}) Tj')
  # Every segment remains in one PDF text object, so each Tj advances the same
  # continuous Helvetica text position used by the line-oriented renderer.
  self.page.ops.append(f'BT /{font} {size:.1f} Tf {x:.1f} {self.y:.1f} Td '+ ' '.join(parts)+' ET')
 def styled_block(self,text,size=10.5,bold=False,indent=0,gap=14,prefix='',internal=None):
  spans=self.markdown_spans(text)
  if prefix: spans.insert(0,(prefix,None))
  if internal: spans=[(''.join(s for s,_ in spans),('goto',internal))]
  x=LEFT+indent
  for line,runs in wrap_spans(spans,size,W-RIGHT-x):
   if self.y-gap<BOTTOM: self.new(self.page.head)
   self.styled_line(line,runs,x,size,bold)
   self.y-=gap
 def paragraph(self,text,quote=False,bullet=False,internal=None):
  indent=16 if quote or bullet else 0; prefix='• ' if bullet else ('“' if quote else '')
  self.styled_block(text,indent=indent,prefix=prefix,internal=internal)
  self.y-=5
 def image(self,path):
  image=read_png(path)
  draw_w=W-LEFT-RIGHT; draw_h=draw_w*image.height/image.width
  # Do not make a detailed diagram tiny merely to use the bottom of a page.
  if self.y-BOTTOM < draw_h*.7: self.new(self.page.head)
  available=self.y-BOTTOM
  if draw_h>available:
   scale=available/draw_h; draw_w*=scale; draw_h*=scale
  x=LEFT+(W-LEFT-RIGHT-draw_w)/2; y=self.y-draw_h
  name=f'Im{len(self.page.images)+1}'
  self.page.images[path]=name
  self.page.ops.append(f'q {draw_w:.2f} 0 0 {draw_h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q')
  self.y=y-14
 def document(self,path):
  lines=path.read_text(encoding='utf-8').splitlines(); raw_title=lines[0][2:]; title=plain(raw_title)
  self.new(title)
  self.source_path=path.parent; self.toc=path.stem=='CONTENTS'
  dest=self.file_dest[path.resolve()]; self.page.destinations.append((dest,self.y))
  # The first H1 was formerly consumed as metadata. Render the canonical title.
  self.styled_block(raw_title,20,True,gap=25)
  self.y-=8
  para=[]
  def flush():
   nonlocal para
   if para: self.paragraph(' '.join(x.strip() for x in para)); para=[]
  for raw in lines[1:]:
   s=raw.strip()
   if not s: flush(); continue
   image_match=IMAGE_RE.match(s)
   if image_match:
    flush(); image_path=(path.parent/image_match.group(2)).resolve()
    if not image_path.is_file():
     raise SystemExit(f'Missing Markdown image: source={path.relative_to(ROOT)} reference={image_match.group(2)}')
    self.image(image_path)
   elif s.startswith('#'):
    flush(); n=len(s)-len(s.lstrip('#')); text=s[n:].strip(); sizes={1:20,2:14,3:11.5}; self.y-=8 if n<3 else 2
    size=sizes.get(n,11); self.styled_block(text,size,True,gap=size+5)
    self.y-=5
   elif s.startswith('> '): flush(); self.paragraph(s[2:],quote=True)
   elif re.match(r'^[-*] ',s):
    flush(); body=s[2:]; target=None
    if self.toc:
     m=re.search(r'Chapter\s+(\d+)|Cap[ií]tulo\s+(\d+)',body,re.I)
     if m: target=f'chapter-{int(m.group(1) or m.group(2)):02d}'
    self.paragraph(body,bullet=True,internal=target)
   elif self.toc and re.match(r'^\d+\.\s+',s):
    flush(); m=re.match(r'^(\d+)\.\s+(.*)',s); slugs=['glossary','certification-roadmap','physical-preparation','family-guide','master-bibliography','source-notes']
    self.paragraph(m.group(2),internal=f'appendix-{slugs[int(m.group(1))-1]}')
   elif s.startswith('|'): flush(); self.paragraph(s.replace('|','  '))
   else: para.append(s)
  flush()
 def render(self,files,out):
  self.new(self.title); self.y=H-170
  for line in wrap(self.title,25,W-LEFT-RIGHT,True): self.line(line,25,True,gap=34)
  self.y-=20; self.line('Foundation skeleton edition' if self.lang=='en' else 'Edición de estructura',13)
  self.line('Language: English' if self.lang=='en' else 'Idioma: Español',11)
  self.y-=25; self.paragraph('Numbered weeks are an editorial learning journey, not a claim about HRCJTA’s unpublished weekly schedule.' if self.lang=='en' else 'Las semanas numeradas son un recorrido editorial, no una afirmación sobre el calendario semanal no publicado de HRCJTA.')
  for f in files: self.document(f)
  PDF(self.pages,self.title,self.lang).write(out)
class PDF:
 def __init__(self,pages,title,lang): self.pages=pages; self.title=title; self.lang=lang; self.objs=[]
 def add(self,b): self.objs.append(b if isinstance(b,bytes) else b.encode('latin1','replace')); return len(self.objs)
 def write(self,path):
  catalog=self.add(b''); pages_id=self.add(b''); f1=self.add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>'); f2=self.add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
  image_ids={}
  for image_path in dict.fromkeys(image_path for page in self.pages for image_path in page.images):
   image=read_png(image_path)
   header=(f'<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height} '
           f'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode '
           f'/DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns {image.width} >> '
           f'/Length {len(image.data)} >>\nstream\n').encode()
   image_ids[image_path]=self.add(header+image.data+b'\nendstream')
  page_ids=[]
  for no,p in enumerate(self.pages,1):
   ops=list(p.ops); head=p.head or self.title
   ops += [f'BT /F1 8 Tf {LEFT} 28 Td ({esc(head[:78])}) Tj ET',f'BT /F1 8 Tf {W-RIGHT-20} 28 Td ({no}) Tj ET']
   stream='\n'.join(ops).encode('latin1','replace'); content=self.add(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
   anns=[]
   for x1,y1,x2,y2,kind,target in p.links:
    if kind=='uri': action=f'/A << /S /URI /URI ({esc(target)}) >>'
    else: action=f'/A << /S /GoTo /D ({esc(target)}) >>'
    anns.append(self.add(f'<< /Type /Annot /Subtype /Link /Rect [{x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f}] /Border [0 0 0] {action} >>'))
   aid=(' /Annots ['+' '.join(f'{x} 0 R' for x in anns)+']') if anns else ''
   xobjects=' '.join(f'/{name} {image_ids[image_path]} 0 R' for image_path,name in p.images.items())
   image_resources=f' /XObject << {xobjects} >>' if xobjects else ''
   page_ids.append(self.add(f'<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >>{image_resources} >> /Contents {content} 0 R{aid} >>'))
  self.objs[pages_id-1]=f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{x} 0 R' for x in page_ids)}] >>".encode()
  destinations=[]; outline_entries=[]
  for page,page_id in zip(self.pages,page_ids):
   for name,y in page.destinations:
    destinations.append((name,page_id,y)); outline_entries.append((page.head,name))
  names_id=self.add('<< /Names ['+' '.join(f'({esc(name)}) [{page_id} 0 R /XYZ null {y:.1f} null]' for name,page_id,y in sorted(destinations))+'] >>')
  outlines_id=self.add(b'')
  outline_ids=[self.add(b'') for _ in outline_entries]
  for i,((label,dest),oid) in enumerate(zip(outline_entries,outline_ids)):
   prev=f' /Prev {outline_ids[i-1]} 0 R' if i else ''
   nxt=f' /Next {outline_ids[i+1]} 0 R' if i+1<len(outline_ids) else ''
   self.objs[oid-1]=f'<< /Title ({esc(label)}) /Parent {outlines_id} 0 R{prev}{nxt} /Dest ({esc(dest)}) >>'.encode()
  if outline_ids:
   self.objs[outlines_id-1]=f'<< /Type /Outlines /First {outline_ids[0]} 0 R /Last {outline_ids[-1]} 0 R /Count {len(outline_ids)} >>'.encode()
  else: self.objs[outlines_id-1]=b'<< /Type /Outlines /Count 0 >>'
  self.objs[catalog-1]=f'<< /Type /Catalog /Pages {pages_id} 0 R /Lang ({self.lang}) /Names << /Dests {names_id} 0 R >> /Outlines {outlines_id} 0 R /PageMode /UseOutlines >>'.encode()
  info=self.add(f'<< /Title ({esc(self.title)}) /Creator (Virginia Police Academy Guide deterministic builder) >>')
  data=bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'); offsets=[0]
  for i,o in enumerate(self.objs,1): offsets.append(len(data)); data+=f'{i} 0 obj\n'.encode()+o+b'\nendobj\n'
  xref=len(data); data+=f'xref\n0 {len(self.objs)+1}\n0000000000 65535 f \n'.encode()
  for off in offsets[1:]: data+=f'{off:010d} 00000 n \n'.encode()
  data+=f'trailer\n<< /Size {len(self.objs)+1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
  path.parent.mkdir(exist_ok=True); path.write_bytes(data)

@dataclass(frozen=True)
class PNG:
 width:int; height:int; data:bytes

def read_png(path):
 """Return PDF-ready scanlines from an 8-bit, non-interlaced RGB PNG."""
 data=path.read_bytes()
 if data[:8]!=b'\x89PNG\r\n\x1a\n': raise SystemExit(f'Unsupported PNG (bad signature): {path}')
 pos=8; width=height=None; compressed=[]
 while pos<len(data):
  length=struct.unpack('>I',data[pos:pos+4])[0]; kind=data[pos+4:pos+8]; chunk=data[pos+8:pos+8+length]; pos+=length+12
  if kind==b'IHDR':
   width,height,depth,color,compression,png_filter,interlace=struct.unpack('>IIBBBBB',chunk)
   if (depth,color,compression,png_filter,interlace)!=(8,2,0,0,0):
    raise SystemExit(f'Unsupported PNG format in {path}: requires 8-bit non-interlaced RGB')
  elif kind==b'IDAT': compressed.append(chunk)
  elif kind==b'IEND': break
 if width is None or not compressed: raise SystemExit(f'Unsupported PNG (missing image data): {path}')
 return PNG(width,height,b''.join(compressed))
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('language',choices=('en','es')); ap.add_argument('--validate-only',action='store_true'); a=ap.parse_args(); cfg=load_manifest()[a.language]; files=validate(cfg,a.language)
 if a.validate_only: print(f'Validated {a.language}: {len(files)} ordered source files'); return
 out=ROOT/'dist'/cfg['output']; Renderer(cfg['title'],a.language,files).render(files,out); print(f'Built {out.relative_to(ROOT)} ({len(files)} ordered source files)')
if __name__=='__main__': main()
