# -*- coding: utf-8 -*-

from pyrevit import script, forms
from Autodesk.Revit.DB import *
import clr
import json
import urllib2
import re

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Windows.Forms import (
    Form, TextBox, Button, Label, DialogResult,
    FormStartPosition, ScrollBars
)
from System.Drawing import Size, Point, Font


doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
app = __revit__.Application
output = script.get_output()

KEY_PATH = r"C:\AI\gemini_key.txt"

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite"
]


class PromptForm(Form):
    def __init__(self):
        self.Text = "AI BIM Code Assistant"
        self.Size = Size(980, 680)
        self.StartPosition = FormStartPosition.CenterScreen

        label = Label()
        label.Text = "Enter any Revit command:"
        label.Location = Point(25, 20)
        label.Size = Size(900, 25)
        label.Font = Font("Segoe UI", 10)
        self.Controls.Add(label)

        self.textbox = TextBox()
        self.textbox.Multiline = True
        self.textbox.ScrollBars = ScrollBars.Vertical
        self.textbox.Location = Point(25, 60)
        self.textbox.Size = Size(900, 490)
        self.textbox.Font = Font("Segoe UI", 11)
        self.textbox.Text = "Create 5 sheets named Test 1, Test 2, Test 3, Test 4, Test 5"
        self.Controls.Add(self.textbox)

        run_btn = Button()
        run_btn.Text = "Generate Code"
        run_btn.Location = Point(665, 575)
        run_btn.Size = Size(120, 36)
        run_btn.DialogResult = DialogResult.OK
        self.Controls.Add(run_btn)

        cancel_btn = Button()
        cancel_btn.Text = "Cancel"
        cancel_btn.Location = Point(805, 575)
        cancel_btn.Size = Size(120, 36)
        cancel_btn.DialogResult = DialogResult.Cancel
        self.Controls.Add(cancel_btn)

        self.AcceptButton = run_btn
        self.CancelButton = cancel_btn


class CodePreviewForm(Form):
    def __init__(self, code):
        self.Text = "AI Generated Revit Python Code - Preview"
        self.Size = Size(1100, 760)
        self.StartPosition = FormStartPosition.CenterScreen

        label = Label()
        label.Text = "Review the generated code carefully before executing:"
        label.Location = Point(25, 20)
        label.Size = Size(1000, 25)
        label.Font = Font("Segoe UI", 10)
        self.Controls.Add(label)

        self.textbox = TextBox()
        self.textbox.Multiline = True
        self.textbox.ScrollBars = ScrollBars.Vertical
        self.textbox.Location = Point(25, 60)
        self.textbox.Size = Size(1030, 560)
        self.textbox.Font = Font("Consolas", 10)
        self.textbox.Text = code
        self.textbox.ReadOnly = False
        self.Controls.Add(self.textbox)

        execute_btn = Button()
        execute_btn.Text = "Execute"
        execute_btn.Location = Point(815, 645)
        execute_btn.Size = Size(110, 36)
        execute_btn.DialogResult = DialogResult.OK
        self.Controls.Add(execute_btn)

        cancel_btn = Button()
        cancel_btn.Text = "Cancel"
        cancel_btn.Location = Point(945, 645)
        cancel_btn.Size = Size(110, 36)
        cancel_btn.DialogResult = DialogResult.Cancel
        self.Controls.Add(cancel_btn)

        self.AcceptButton = execute_btn
        self.CancelButton = cancel_btn


def alert(msg):
    forms.alert(msg, title="AI BIM Code Assistant")


def read_api_key():
    with open(KEY_PATH, "r") as f:
        return f.read().strip()


def clean_code(text):
    text = text.replace("```python", "")
    text = text.replace("```py", "")
    text = text.replace("```", "")
    return text.strip()


def get_context():
    sheets = []
    for s in FilteredElementCollector(doc).OfClass(ViewSheet).ToElements():
        if not s.IsPlaceholder:
            sheets.append({
                "number": s.SheetNumber,
                "name": s.Name
            })

    views = []
    for v in FilteredElementCollector(doc).OfClass(View).ToElements():
        if not v.IsTemplate and not isinstance(v, ViewSheet):
            views.append({
                "name": v.Name,
                "type": str(v.ViewType)
            })

    levels = []
    for l in FilteredElementCollector(doc).OfClass(Level).ToElements():
        levels.append({
            "name": l.Name,
            "elevation_ft": l.Elevation
        })

    grids = []
    for g in FilteredElementCollector(doc).OfClass(Grid).ToElements():
        grids.append({
            "name": g.Name
        })

    return {
        "sheets": sheets[:300],
        "views": views[:300],
        "levels": levels,
        "grids": grids
    }


def call_gemini_model(api_key, model, user_prompt, context):
    url = "https://generativelanguage.googleapis.com/v1beta/models/{0}:generateContent?key={1}".format(
        model,
        api_key
    )

    system_prompt = """
You are an expert Autodesk Revit API and pyRevit IronPython developer.

Generate ONLY executable IronPython code for pyRevit.
No markdown.
No explanation.
No comments outside the code.

Available variables already exist:
- doc
- uidoc
- app
- output
- __revit__

You may use:
from Autodesk.Revit.DB import *

Important rules:
- Use IronPython 2.7 compatible syntax.
- Do not use f-strings.
- Do not use external packages.
- Do not use os, sys, subprocess, shutil, socket, requests, urllib, file operations, or internet access.
- Do not read or write files.
- Do not open URLs.
- For model changes, use Transaction(doc, "...").
- For Revit units, internal length is feet.
- If user gives millimeters, convert using mm / 304.8.
- If creating sheets, find first title block using OST_TitleBlocks and FamilySymbol.
- If no title block exists, use ElementId.InvalidElementId.
- If deleting elements, delete only elements clearly requested by the user.
- Prefer safe, minimal, direct code.
- At the end, show result using forms.alert("message") or output.print_md("message").
"""

    full_prompt = (
        system_prompt +
        "\n\nCurrent Revit context:\n" +
        json.dumps(context, ensure_ascii=False) +
        "\n\nUser request:\n" +
        user_prompt
    )

    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": 0.05
        }
    }

    req = urllib2.Request(
        url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"}
    )

    response = urllib2.urlopen(req)
    result = json.loads(response.read())

    raw_text = result["candidates"][0]["content"]["parts"][0]["text"]

    output.print_md("## Raw AI Code")
    output.print_code(raw_text)

    return clean_code(raw_text)


def call_gemini(api_key, user_prompt, context):
    errors = []

    for model in MODELS:
        try:
            code = call_gemini_model(api_key, model, user_prompt, context)
            return code, model
        except Exception as e:
            errors.append(model + " -> " + str(e))

    raise Exception("All Gemini models failed:\n\n" + "\n\n".join(errors))


def safety_check(code):
    blocked_terms = [
        "import os",
        "import sys",
        "import subprocess",
        "import shutil",
        "import socket",
        "import requests",
        "urllib",
        "open(",
        "file(",
        "eval(",
        "exec(",
        "__import__",
        "compile(",
        "input(",
        "raw_input(",
        "pickle",
        "base64",
        "Delete(",
        "doc.Delete"
    ]

    lower_code = code.lower()

    for term in blocked_terms:
        if term.lower() in lower_code:
            return False, "Blocked unsafe term: {0}".format(term)

    return True, "OK"


def execute_generated_code(code):
    safe, message = safety_check(code)

    if not safe:
        alert("Execution blocked for safety.\n\n{0}".format(message))
        return

    globals_dict = {
        "__revit__": __revit__,
        "doc": doc,
        "uidoc": uidoc,
        "app": app,
        "output": output,
        "forms": forms,

        "FilteredElementCollector": FilteredElementCollector,
        "ViewSheet": ViewSheet,
        "Transaction": Transaction,
        "BuiltInCategory": BuiltInCategory,
        "FamilySymbol": FamilySymbol,
        "ElementId": ElementId,
        "Level": Level,
        "Grid": Grid,
        "Line": Line,
        "XYZ": XYZ,
        "View": View,
        "Viewport": Viewport,
        "ViewDuplicateOption": ViewDuplicateOption
    }

    exec(code, globals_dict)


# MAIN

prompt_form = PromptForm()
prompt_result = prompt_form.ShowDialog()

if prompt_result != DialogResult.OK:
    script.exit()

user_prompt = prompt_form.textbox.Text.strip()

if not user_prompt:
    alert("No command entered.")
    script.exit()

try:
    api_key = read_api_key()
    context = get_context()

    code, used_model = call_gemini(api_key, user_prompt, context)

    code = "# Model used: {0}\n\n".format(used_model) + code

    preview_form = CodePreviewForm(code)
    preview_result = preview_form.ShowDialog()

    if preview_result != DialogResult.OK:
        alert("Cancelled. Code was not executed.")
        script.exit()

    final_code = preview_form.textbox.Text

    lines = final_code.splitlines()
    cleaned_lines = []

    for line in lines:
        if not line.strip().startswith("# Model used:"):
            cleaned_lines.append(line)

    final_code = "\n".join(cleaned_lines)

    execute_generated_code(final_code)

except Exception as e:
    alert("Error:\n\n{0}".format(str(e)))