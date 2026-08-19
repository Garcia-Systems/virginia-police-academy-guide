#!/usr/bin/env python3
"""Dependency-free, deterministic Markdown-to-PDF skeleton builder."""
from __future__ import annotations
import argparse, importlib.util, re, sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
W,H=612,792; LEFT,RIGHT,TOP,BOTTOM=58,58,60,52
URL_RE=re.compile(r'\[([^]]+)\]\((https?://[^)]+)\)|(https?://\S+)')

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
def plain(s): return re.sub(r'[*_`]', '', URL_RE.sub(lambda m:m.group(1) or m.group(3),s)).strip()
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
 head:str; ops:list[str]=field(default_factory=list); links:list[tuple]=field(default_factory=list)
class Renderer:
 def __init__(self,title,lang): self.title=title; self.lang=lang; self.pages=[]; self.page=None; self.y=0
 def new(self,head=''):
  self.page=Page(head); self.pages.append(self.page); self.y=H-TOP
 def line(self,text,size=10.5,bold=False,indent=0,url=None,gap=14):
  if self.y-gap<BOTTOM: self.new(self.page.head)
  font='F2' if bold else 'F1'; x=LEFT+indent
  self.page.ops.append(f'BT /{font} {size:.1f} Tf {x:.1f} {self.y:.1f} Td ({esc(plain(text))}) Tj ET')
  if url: self.page.links.append((x,self.y-2,min(W-RIGHT,x+width(plain(text),size,bold)),self.y+size,url))
  self.y-=gap
 def paragraph(self,text,quote=False,bullet=False):
  indent=16 if quote or bullet else 0; prefix='• ' if bullet else ('“' if quote else '')
  # Render links as a clickable whole line/paragraph where present.
  m=URL_RE.search(text); url=(m.group(2) or m.group(3)) if m else None
  for i,l in enumerate(wrap(prefix+text,10.5,W-LEFT-RIGHT-indent)):
   self.line(l,indent=indent,url=url if i==0 else None,gap=14)
  self.y-=5
 def document(self,path):
  lines=path.read_text(encoding='utf-8').splitlines(); title=plain(lines[0][2:])
  self.new(title)
  para=[]
  def flush():
   nonlocal para
   if para: self.paragraph(' '.join(x.strip() for x in para)); para=[]
  for raw in lines[1:]:
   s=raw.strip()
   if not s: flush(); continue
   if s.startswith('#'):
    flush(); n=len(s)-len(s.lstrip('#')); text=s[n:].strip(); sizes={1:20,2:14,3:11.5}; self.y-=8 if n<3 else 2
    for l in wrap(text,sizes.get(n,11),W-LEFT-RIGHT,True): self.line(l,sizes.get(n,11),True,gap=sizes.get(n,11)+5)
    self.y-=5
   elif s.startswith('> '): flush(); self.paragraph(s[2:],quote=True)
   elif re.match(r'^[-*] ',s): flush(); self.paragraph(s[2:],bullet=True)
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
  page_ids=[]
  for no,p in enumerate(self.pages,1):
   ops=list(p.ops); head=p.head or self.title
   ops += [f'BT /F1 8 Tf {LEFT} 28 Td ({esc(head[:78])}) Tj ET',f'BT /F1 8 Tf {W-RIGHT-20} 28 Td ({no}) Tj ET']
   stream='\n'.join(ops).encode('latin1','replace'); content=self.add(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
   anns=[]
   for x1,y1,x2,y2,url in p.links:
    anns.append(self.add(f'<< /Type /Annot /Subtype /Link /Rect [{x1:.1f} {y1:.1f} {x2:.1f} {y2:.1f}] /Border [0 0 0] /A << /S /URI /URI ({esc(url)}) >> >>'))
   aid=(' /Annots ['+' '.join(f'{x} 0 R' for x in anns)+']') if anns else ''
   page_ids.append(self.add(f'<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {content} 0 R{aid} >>'))
  self.objs[pages_id-1]=f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{x} 0 R' for x in page_ids)}] >>".encode()
  self.objs[catalog-1]=f'<< /Type /Catalog /Pages {pages_id} 0 R /Lang ({self.lang}) >>'.encode()
  info=self.add(f'<< /Title ({esc(self.title)}) /Creator (Virginia Police Academy Guide deterministic builder) >>')
  data=bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'); offsets=[0]
  for i,o in enumerate(self.objs,1): offsets.append(len(data)); data+=f'{i} 0 obj\n'.encode()+o+b'\nendobj\n'
  xref=len(data); data+=f'xref\n0 {len(self.objs)+1}\n0000000000 65535 f \n'.encode()
  for off in offsets[1:]: data+=f'{off:010d} 00000 n \n'.encode()
  data+=f'trailer\n<< /Size {len(self.objs)+1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
  path.parent.mkdir(exist_ok=True); path.write_bytes(data)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('language',choices=('en','es')); ap.add_argument('--validate-only',action='store_true'); a=ap.parse_args(); cfg=load_manifest()[a.language]; files=validate(cfg,a.language)
 if a.validate_only: print(f'Validated {a.language}: {len(files)} ordered source files'); return
 out=ROOT/'dist'/cfg['output']; Renderer(cfg['title'],a.language).render(files,out); print(f'Built {out.relative_to(ROOT)} ({len(files)} ordered source files)')
if __name__=='__main__': main()
