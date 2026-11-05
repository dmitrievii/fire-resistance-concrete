"""Remove obsolete drawing thumbnails and equation binaries inherited from the original Word template.

Only unreferenced document-level image/OLE relationships and package parts are pruned.
Footer/header content remains byte-exact.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from tempfile import mkstemp
from posixpath import normpath
import os

REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'

def prune_unused_template_assets(target):
    target = Path(target)
    with ZipFile(target) as zin:
        dxml = zin.read('word/document.xml')
        droot = etree.fromstring(dxml)
        relname = 'word/_rels/document.xml.rels'
        relroot = etree.fromstring(zin.read(relname))
        # r:id, r:embed, and r:link are the only external relationship IDs
        # referenced by the live document body.
        used_ids = {v for e in droot.iter() for k, v in e.attrib.items() if k.startswith('{'+R_NS+'}')}
        removed_rids = []
        removed_targets = []
        for rel in list(relroot):
            typ = rel.get('Type', '').rsplit('/', 1)[-1]
            if typ not in ('image', 'oleObject') or rel.get('Id') in used_ids:
                continue
            removed_rids.append(rel.get('Id'))
            t = rel.get('Target')
            if not rel.get('TargetMode') and t:
                removed_targets.append(normpath('word/'+t.lstrip('/')))
            relroot.remove(rel)
        # Retain media still referenced from any relationship file after edits.
        live_media_targets = set()
        for n in zin.namelist():
            if not n.endswith('.rels'):
                continue
            rr = relroot if n == relname else etree.fromstring(zin.read(n))
            if n == '_rels/.rels': source_dir = ''
            else: source_dir = n.split('/_rels/')[0] + '/'
            for rel in rr:
                t = rel.get('Target', '')
                if not t or rel.get('TargetMode') == 'External': continue
                path = normpath(source_dir + t.lstrip('/'))
                live_media_targets.add(path)
        dropped_parts = [n for n in zin.namelist()
            if (n.startswith('word/media/') or n.startswith('word/embeddings/'))
            and n not in live_media_targets]
        ct = etree.fromstring(zin.read('[Content_Types].xml'))
        for elem in list(ct):
            if elem.get('PartName', '').lstrip('/') in dropped_parts:
                ct.remove(elem)
        fd, tmp = mkstemp(suffix='.docx', dir=target.parent)
        os.close(fd)
        with ZipFile(tmp, 'w') as zout:
            for info in zin.infolist():
                n = info.filename
                if n in dropped_parts: continue
                if n == relname: data = etree.tostring(relroot, xml_declaration=True, encoding='UTF-8', standalone=True)
                elif n == '[Content_Types].xml': data = etree.tostring(ct, xml_declaration=True, encoding='UTF-8', standalone=True)
                else: data = zin.read(n)
                zout.writestr(info, data)
    os.replace(tmp, target)
    return {'removed_rels': len(removed_rids), 'removed_parts': len(dropped_parts),
            'removed_images': sum(x.startswith('word/media/') for x in dropped_parts),
            'removed_ole': sum(x.startswith('word/embeddings/') for x in dropped_parts)}