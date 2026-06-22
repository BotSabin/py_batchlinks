# -*- coding: utf-8 -*-

from pyrevit import forms, script
from collections import defaultdict
import os
import re
import csv

output = script.get_output()

ifc_path = forms.pick_file(file_ext='ifc', title='Selecteaza IFC pentru analiza')
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

if not class_counts:
    forms.alert("Nu am gasit clase IFC.", title="BIMBOT")
    script.exit()

folder = os.path.dirname(ifc_path)
base = os.path.splitext(os.path.basename(ifc_path))[0]
report_path = os.path.join(folder, base + "_BIMBOT_IFC_Report.csv")

rows = []

for cls, count in sorted(class_counts.items(), key=lambda x: x[1], reverse=True):
    percent = round((float(count) / float(total)) * 100, 2)
    rows.append([cls, count, percent])

with open(report_path, "wb") as f:
    writer = csv.writer(f)
    writer.writerow(["IFC Class", "Count", "Percent"])
    for r in rows:
        writer.writerow(r)

output.print_md("# BIMBOT IFC Analyze")
output.print_md("**IFC:** `{}`".format(ifc_path))
output.print_md("**Total entitati:** `{}`".format(total))
output.print_md("**Raport salvat:** `{}`".format(report_path))
output.print_table(rows, columns=["IFC Class", "Count", "Percent"])

forms.alert("Raport salvat:\n\n{}".format(report_path), title="BIMBOT Analyze IFC")