"""Canva page-one PDF export and embedded layers, with atomic validated cache."""
import hashlib
import io
import json
import os
import time
from pathlib import Path
from PIL import Image


def extract_layers(pdf: bytes, destination: Path) -> Path:
    import pymupdf
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        if not len(doc):
            raise ValueError('PDF Canva vuoto')
        page=doc[0]
        candidates={'background':[], 'player':[]}
        for xref,smask,*_ in page.get_images(full=True):
            rects=page.get_image_rects(xref)
            if len(rects)!=1:
                continue
            rect=rects[0]
            if (rect & page.rect).get_area() < page.rect.get_area()*.35:
                continue
            pix=pymupdf.Pixmap(doc,xref)
            if smask:
                pix=pymupdf.Pixmap(pix,pymupdf.Pixmap(doc,smask))
            if pix.colorspace and pix.colorspace.n!=3:
                pix=pymupdf.Pixmap(pymupdf.csRGB,pix)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGBA')
            role='player' if smask else 'background'
            candidates[role].append((image,rect))
        if any(len(v)!=1 for v in candidates.values()):
            raise ValueError('Pagina 1 ambigua: attesi un background e una sagoma con maschera')
        # Bake each layer using its real PDF placement, not image/xref order.
        destination.mkdir(parents=True,exist_ok=True)
        for role,items in candidates.items():
            image,rect=items[0]
            sx,sy=1086/page.rect.width,1448/page.rect.height
            canvas=Image.new('RGBA',(1086,1448))
            image=image.resize((round(rect.width*sx),round(rect.height*sy)),Image.Resampling.LANCZOS)
            canvas.alpha_composite(image,(round((rect.x0-page.rect.x0)*sx),round((rect.y0-page.rect.y0)*sy)))
            temp=destination/f'{role}.tmp.png'
            canvas.save(temp)
            os.replace(temp,destination/f'{role}.png')
        (destination/'source.pdf').write_bytes(pdf)
        (destination/'manifest.json').write_text(json.dumps({'page':1,'sha256':hashlib.sha256(pdf).hexdigest(),'size':[1086,1448]}))
    return destination


def export_page_one(session, token: str, design: str, cache: Path, *, refresh=True, sleep=time.sleep) -> Path:
    """Only return validated page-one layers; never switch to kit pages."""
    manifest=cache/'current.json'
    def previous():
        if manifest.exists():
            folder=cache/json.loads(manifest.read_text())['folder']
            if all((folder/name).is_file() for name in ['player.png','background.png','manifest.json']):
                return folder
        return None
    try:
        old=previous()
    except (OSError, ValueError, KeyError, TypeError):
        old=None
    if old and not refresh:
        return old
    try:
        if not token:
            raise ValueError('Token Canva assente')
        headers={'Authorization':f'Bearer {token}'}
        response=session.post('https://api.canva.com/rest/v1/exports',headers=headers,json={'design_id':design,'format':{'type':'pdf','pages':[1]}},timeout=30)
        response.raise_for_status()
        job=response.json();job=job.get('job',job)
        job_id=job['id']
        for _ in range(60):
            sleep(3)
            response=session.get(f'https://api.canva.com/rest/v1/exports/{job_id}',headers=headers,timeout=30)
            response.raise_for_status()
            job=response.json();job=job.get('job',job)
            if job.get('status')=='failed':
                raise ValueError('Export PDF Canva fallito')
            if job.get('status')=='success':
                response=session.get(job['urls'][0],timeout=60)
                response.raise_for_status()
                pdf=response.content
                folder=hashlib.sha256(pdf).hexdigest()[:20]
                result=extract_layers(pdf,cache/folder)
                tmp=cache/'current.tmp'
                tmp.write_text(json.dumps({'folder':folder}))
                os.replace(tmp,manifest)
                print('CANVA: PDF pagina 1 scaricato, background e maschera verificati')
                return result
        raise TimeoutError('Export PDF Canva scaduto')
    except Exception as exc:
        if old:
            print(f'CANVA: {type(exc).__name__}; riuso ultima pagina 1 validata')
            return old
        raise
