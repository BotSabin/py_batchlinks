# -*- coding: utf-8 -*-

from pyrevit import forms, script
from collections import defaultdict
import os
import re
import json
import tempfile
import subprocess

output = script.get_output()

ifc_path = forms.pick_file(file_ext='ifc', title='Selecteaza IFC pentru filtrare FAST')
if not ifc_path:
    script.exit()

class_counts = defaultdict(int)
total = 0
pattern = re.compile(r"=\s*(IFC[A-Z0-9_]+)\s*\(", re.IGNORECASE)

with open(ifc_path, "r") as f:
    for line in f:
        m = pattern.search(line)
        if m:
            cls = m.group(1).upper()
            class_counts[cls] += 1
            total += 1

items = []
for cls, count in sorted(class_counts.items(), key=lambda x: x[1], reverse=True):
    percent = round((float(count) / float(total)) * 100, 2)
    items.append("{}  [{} elemente | {}%]".format(cls, count, percent))

selected = forms.SelectFromList.show(
    items,
    title="Bifeaza clasele IFC pe care vrei sa le PASTREZI",
    multiselect=True,
    button_name="Create FAST IFC"
)

if not selected:
    script.exit()

keep_classes = [x.split("  [")[0].upper() for x in selected]

folder = os.path.dirname(ifc_path)
base = os.path.splitext(os.path.basename(ifc_path))[0]
target_ifc = os.path.join(folder, base + "_BIMBOT_FAST_Light.ifc")

temp_dir = tempfile.gettempdir()
args_path = os.path.join(temp_dir, "bimbot_fast_args.json")
worker_path = os.path.join(temp_dir, "bimbot_fast_worker.py")

with open(args_path, "w") as f:
    json.dump({
        "source_ifc": ifc_path,
        "target_ifc": target_ifc,
        "keep_classes": keep_classes
    }, f)

worker_code = r"""
import sys
import json

try:
    import ifcopenshell
except Exception as e:
    print("ERROR_IMPORT_IFCOPENSHELL")
    print(str(e))
    sys.exit(1)

args_path = sys.argv[1]

with open(args_path, "r") as f:
    args = json.load(f)

source_ifc = args["source_ifc"]
target_ifc = args["target_ifc"]
keep_classes = set([x.upper() for x in args["keep_classes"]])

src = ifcopenshell.open(source_ifc)
dst = ifcopenshell.file(schema=src.schema)

copied = 0
failed = 0

# Copiem proiectul si setarile principale
for cls in [
    "IfcProject",
    "IfcSite",
    "IfcBuilding",
    "IfcBuildingStorey",
    "IfcUnitAssignment",
    "IfcGeometricRepresentationContext",
    "IfcGeometricRepresentationSubContext"
]:
    try:
        for ent in src.by_type(cls):
            try:
                dst.add(ent)
            except:
                pass
    except:
        pass

# Copiem DOAR produsele din clasele bifate
products = list(src.by_type("IfcProduct"))

for product in products:
    try:
        cls = product.is_a().upper()
        if cls in keep_classes:
            dst.add(product)
            copied += 1
    except Exception:
        failed += 1

dst.write(target_ifc)

print("OK")
print("Source: {}".format(source_ifc))
print("Target: {}".format(target_ifc))
print("Keep classes: {}".format(", ".join(sorted(list(keep_classes)))))
print("Copied products: {}".format(copied))
print("Failed: {}".format(failed))
"""

with open(worker_path, "w") as f:
    f.write(worker_code)

cmd = 'py -3 "{}" "{}"'.format(worker_path, args_path)

process = subprocess.Popen(
    cmd,
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

stdout, stderr = process.communicate()

stdout_text = stdout.decode("utf-8", "ignore") if hasattr(stdout, "decode") else str(stdout)
stderr_text = stderr.decode("utf-8", "ignore") if hasattr(stderr, "decode") else str(stderr)

output.print_md("# BIMBOT FAST IFC Filter")
output.print_md("**Original:** `{}`".format(ifc_path))
output.print_md("**Light IFC:** `{}`".format(target_ifc))
output.print_md("**Clase pastrate:**")
for cls in keep_classes:
    output.print_md("- {}".format(cls))

output.print_md("## Worker Output")
output.print_md("```")
output.print_md(stdout_text)
output.print_md(stderr_text)
output.print_md("```")

if process.returncode != 0:
    forms.alert(
        "Nu am putut crea FAST IFC.\n\n{}\n\n{}".format(stderr_text, stdout_text),
        title="BIMBOT FAST Filter"
    )
    script.exit()

if not os.path.exists(target_ifc):
    forms.alert("Fisierul FAST IFC nu a fost creat.", title="BIMBOT FAST Filter")
    script.exit()

forms.alert(
    "FAST IFC creat:\n\n{}".format(target_ifc),
    title="BIMBOT FAST Filter"
)