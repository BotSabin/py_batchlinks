# -*- coding: utf-8 -*-
import os, sys
from pyrevit import revit, forms, script
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..','..','..'))
lib = os.path.join(root, 'lib')
if lib not in sys.path:
    sys.path.append(lib)
from mepgraph import *
uidoc = revit.uidoc
doc = revit.doc
out = script.get_output()

el = pick_one(uidoc, 'Selecteaza un element MEP pentru raport')
ids = traverse(doc, el.Id)
counts = {}
opens = 0
length_ft = 0.0
for eid in ids:
    x = doc.GetElement(eid)
    cname = x.Category.Name if x.Category else 'No Category'
    counts[cname] = counts.get(cname, 0) + 1
    opens += open_connector_count(x)
    try:
        p = x.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        if p: length_ft += p.AsDouble()
    except Exception:
        pass
out.print_md('## Route Inspector')
out.print_md('**Elemente in retea:** {}'.format(len(ids)))
out.print_md('**Lungime curbe:** {:.2f} m'.format(length_ft * 0.3048))
out.print_md('**Conectori liberi:** {}'.format(opens))
out.print_md('### Categorii')
for k in sorted(counts.keys()):
    out.print_md('- {}: {}'.format(k, counts[k]))
set_selection(uidoc, ids)
