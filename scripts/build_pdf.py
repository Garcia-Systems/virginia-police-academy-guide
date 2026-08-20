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
def width(s,size,bold=False): return len(s)*size*(.54 if not bold else .57)
def wrap(s,size,maxw,bold=False):
 words=s.split(); out=[]; cur=''
 for word in words:
  nxt=(cur+' '+word).strip()
  if cur and width(plain(nxt),size,bold)>maxw: out.append(cur); cur=word
  else: cur=nxt
 if cur: out.append(cur)
 return out or ['']
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
 def paragraph(self,text,quote=False,bullet=False,internal=None):
  indent=16 if quote or bullet else 0; prefix='• ' if bullet else ('“' if quote else '')
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
  if prefix: spans.insert(0,(prefix,None))
  if internal: spans=[(''.join(s for s,_ in spans),('goto',internal))]
  x=LEFT+indent; maxx=W-RIGHT
  for span,link in spans:
   for token in re.findall(r'\s+|\S+',span):
    # Helvetica spaces are 278 units wide. Applying the average-letter width
    # here made the gaps between separately positioned words look justified.
    token_width=len(token)*10.5*.278 if token.isspace() else width(token,10.5)
    if not token.isspace() and x>LEFT+indent and x+token_width>maxx:
     self.y-=14; x=LEFT+indent
     if self.y-14<BOTTOM: self.new(self.page.head); x=LEFT+indent
    if token.isspace() and x==LEFT+indent: continue
    if not token.isspace():
     self.page.ops.append(f'BT /F1 10.5 Tf {x:.1f} {self.y:.1f} Td ({esc(token)}) Tj ET')
     if link: self.page.links.append((x,self.y-2,min(maxx,x+token_width),self.y+10.5,*link))
    x+=token_width
  self.y-=14
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
  lines=path.read_text(encoding='utf-8').splitlines(); title=plain(lines[0][2:])
  self.new(title)
  self.source_path=path.parent; self.toc=path.stem=='CONTENTS'
  dest=self.file_dest[path.resolve()]; self.page.destinations.append((dest,self.y))
  # The first H1 was formerly consumed as metadata. Render the canonical title.
  for l in wrap(title,20,W-LEFT-RIGHT,True): self.line(l,20,True,gap=25)
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
    for l in wrap(text,sizes.get(n,11),W-LEFT-RIGHT,True): self.line(l,sizes.get(n,11),True,gap=sizes.get(n,11)+5)
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
