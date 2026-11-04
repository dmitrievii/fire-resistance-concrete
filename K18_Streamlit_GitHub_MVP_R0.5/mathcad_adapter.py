#!/usr/bin/env python3
"""Read existing scalar definitions/results from a Mathcad 15 XMCD worksheet.

This is an archival-data adapter, NOT a Mathcad evaluator. A saved result is
only evidence of the last recorded calculation, not of a fresh calculation.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from collections import Counter
from pathlib import Path
from lxml import etree
import hashlib

MATH = 'http://schemas.mathsoft.com/math30'
WS = 'http://schemas.mathsoft.com/worksheet30'

def local(element):
    return etree.QName(element).localname

@dataclass(frozen=True)
class Scalar:
    region_id: str
    name: str
    value: Decimal
    provenance: str
    disabled: bool = False

    def record(self):
        return dict(region_id=self.region_id, name=self.name, value=str(self.value),
                    provenance=self.provenance, disabled=self.disabled)

class Xmcd:
    def __init__(self, path):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.tree = etree.parse(str(self.path), etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
        self.rows = []
        self.regions = {}
        self.scalars = {}
        for region in self.tree.xpath('//*[local-name()="region"]'):
            rid = region.get('region-id')
            if not rid:
                continue
            self.regions[rid] = region
            math = region.find(f'{{{WS}}}math')
            if math is None:
                continue
            disabled = math.get('disable-calc','false') == 'true'
            definition = next((c for c in math if local(c) == 'define'), None)
            if definition is None:
                definition = next(iter(math.xpath('./*[local-name()="provenance"]/*[local-name()="define"]')), None)
            lhs = definition[0] if definition is not None and len(definition) else None
            var_name = self._name(lhs)
            # Result in the live math expression, not in provenance history.
            result = math.xpath('./*[local-name()="define" or local-name()="eval"]//*[local-name()="result"]')
            if not result:
                result = math.xpath('./*[local-name()="provenance"]/*[local-name()="define" or local-name()="eval"]//*[local-name()="result"]')
            value = None
            origin = None
            if result:
                value = self._number(result[-1])
                if value is not None:
                    origin = 'saved_result' if result[0].getparent().getparent().getparent() is not None else 'saved_result'
            if value is None and definition is not None and len(definition)>1:
                # A literal worksheet definition is an actual input setting.
                value = self._number(definition[1])
                if value is not None:
                    origin = 'literal_definition'
            row = dict(region_id=rid, name=var_name, value=str(value) if value is not None else None,
                       kind=origin or 'expression_or_array', disabled=disabled)
            self.rows.append(row)
            if value is not None and not disabled:
                self.scalars[rid] = Scalar(rid,var_name,value,origin,disabled)

    @staticmethod
    def _name(e):
        if e is None: return ''
        if local(e) == 'id': return (e.text or '') + ('_' + e.get('subscript') if e.get('subscript') else '')
        return local(e)

    @classmethod
    def _number(cls, e):
        if e is None: return None
        tag=local(e)
        if tag=='real' and e.text:
            try: return Decimal(e.text.strip())
            except InvalidOperation: return None
        if tag in ('eval','result','parens'):
            candidates=[c for c in e if local(c) not in ('symResult','command','symEval')]
            if len(candidates)==1: return cls._number(candidates[0])
        if tag=='apply' and len(e)>=2:
            op=local(e[0]); vals=[cls._number(c) for c in e[1:]]
            if all(x is not None for x in vals):
                try:
                    if op=='plus': return sum(vals)
                    if op=='minus':return -vals[0] if len(vals)==1 else vals[0]-sum(vals[1:])
                    if op=='mult':
                        v=Decimal(1)
                        for x in vals:v*=x
                        return v
                    if op=='div' and len(vals)==2:return vals[0]/vals[1]
                    if op=='pow' and len(vals)==2 and vals[1]==int(vals[1]):return vals[0]**int(vals[1])
                except (ArithmeticError,OverflowError):pass
        return None

    def get(self, rid):
        if str(rid) not in self.scalars:
            raise KeyError(f'XMCD region {rid} missing scalar value or calculation disabled')
        return self.scalars[str(rid)]

    def inventory(self):
        return dict(path=self.path.name, sha256=self.sha256,
                    regions_total=len(self.regions), math_regions=len(self.rows),
                    numeric_scalars=len(self.scalars), kind_count=dict(Counter(r['kind'] for r in self.rows)),
                    scalar_rows=self.rows)
