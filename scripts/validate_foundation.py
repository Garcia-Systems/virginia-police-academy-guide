#!/usr/bin/env python3
import importlib.util, re, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args,cwd=ROOT,ok=True):
 p=subprocess.run(args,cwd=cwd,text=True,capture_output=True)
 if ok and p.returncode: raise SystemExit(p.stdout+p.stderr)
 return p
for lang in ('en','es'): run(str(ROOT/'scripts/build-pdf.sh'),lang)
spec=importlib.util.spec_from_file_location('m',ROOT/'book_manifest.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for lang,cfg in m.BOOKS.items():
 data=(ROOT/'dist'/cfg['output']).read_bytes()
 assert data.startswith(b'%PDF-1.7') and data.rstrip().endswith(b'%%EOF')
 assert b'/MediaBox [0 0 612 792]' in data and b'/Subtype /Link' in data
 text=data.decode('latin1')
 positions=[]
 for fn in cfg['chapters']:
  first=(ROOT/'chapters'/lang/fn).read_text().splitlines()[0][2:]
  token=first[:42].encode('cp1252','replace').decode('latin1').replace('(','\\(').replace(')','\\)')
  positions.append(text.find(token))
 assert all(x>=0 for x in positions) and positions==sorted(positions)
if shutil.which('pdfinfo'):
 for cfg in m.BOOKS.values(): run('pdfinfo',str(ROOT/'dist'/cfg['output']))
if shutil.which('pdftotext'):
 for lang,cfg in m.BOOKS.items():
  out=ROOT/'dist'/f'{lang}.txt'; run('pdftotext',str(ROOT/'dist'/cfg['output']),str(out)); t=out.read_text(errors='replace')
  assert ('Contents' in t if lang=='en' else 'Contenido' in t)
  if lang=='es': assert all(x in t for x in ('Guía','Policía','Año'))
with tempfile.TemporaryDirectory() as d:
 copy=Path(d)/'repo'; shutil.copytree(ROOT,copy,ignore=shutil.ignore_patterns('.git','dist','__pycache__'))
 victim=copy/'chapters/en'/m.BOOKS['en']['chapters'][7]; victim.unlink()
 p=run(str(copy/'scripts/build-pdf.sh'),'en',cwd=copy,ok=False)
 assert p.returncode and 'missing required canonical file' in p.stderr+p.stdout and victim.name in p.stderr+p.stdout
print('Foundation validation passed: builds, PDF structure, order, links, Unicode, contents, and missing-file failure.')
