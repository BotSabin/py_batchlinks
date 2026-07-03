# -*- coding: utf-8 -*-

from pyrevit import revit, script
from Autodesk.Revit.DB import *
import clr
import os

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Windows.Forms import *
from System.Drawing import *

doc = revit.doc
output = script.get_output()
output.set_title("BIMBOT Lookup Table Replacer")


TARGET_CATEGORIES = [
    (BuiltInCategory.OST_PipeCurves, "Pipe Systems"),
    (BuiltInCategory.OST_PipeAccessory, "Pipe Accessories"),
    (BuiltInCategory.OST_PipeFitting, "Pipe Fittings"),
    (BuiltInCategory.OST_Sprinklers, "Sprinklers"),
]


def eid_int(eid):
    try:
        return eid.IntegerValue
    except:
        return eid.Value


TARGET_IDS = dict((eid_int(ElementId(bic)), name) for bic, name in TARGET_CATEGORIES)


def clean_name(path_or_name):
    return os.path.splitext(os.path.basename(path_or_name))[0].strip()


def norm(x):
    return clean_name(x).lower().strip()


def get_csv_files(folder):
    if not folder or not os.path.isdir(folder):
        return []

    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".csv")
    ])


def get_family_category_map():
    data = dict((name, {}) for bic, name in TARGET_CATEGORIES)

    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol):
        try:
            cat = sym.Category
            if not cat:
                continue

            cat_id = eid_int(cat.Id)
            if cat_id not in TARGET_IDS:
                continue

            fam = sym.Family
            if fam and fam.IsEditable:
                data[TARGET_IDS[cat_id]][fam.Name] = fam

        except:
            pass

    return data


def get_manager(fam):
    try:
        return FamilySizeTableManager.GetFamilySizeTableManager(doc, fam.Id)
    except:
        return None


def get_tables(manager):
    try:
        if manager:
            return sorted(list(manager.GetAllSizeTableNames()))
    except:
        pass

    return []


def remove_table(manager, table_name):
    try:
        return manager.RemoveSizeTable(table_name)
    except:
        return False


def import_table(manager, csv_path):
    try:
        err = FamilySizeTableErrorInfo()
        return manager.ImportSizeTable(doc, csv_path, err)
    except:
        return False


class MainForm(Form):
    def __init__(self, category_map):
        self.Text = "BIMBOT - Lookup Table Replacer"
        self.Width = 1250
        self.Height = 800
        self.StartPosition = FormStartPosition.CenterScreen
        self.BackColor = Color.FromArgb(248, 250, 252)
        self.Font = Font("Segoe UI", 9)

        self.category_map = category_map
        self.csv_files = []
        self.result = None
        self._checking = False

        title = Label()
        title.Text = "Lookup Table Replacer"
        title.Left = 28
        title.Top = 18
        title.Width = 700
        title.Height = 42
        title.Font = Font("Segoe UI", 20, FontStyle.Bold)
        title.ForeColor = Color.FromArgb(15, 23, 42)
        self.Controls.Add(title)

        subtitle = Label()
        subtitle.Text = "Replacement only. CSV name must match an existing lookup table name."
        subtitle.Left = 30
        subtitle.Top = 62
        subtitle.Width = 950
        subtitle.Height = 24
        subtitle.ForeColor = Color.FromArgb(71, 85, 105)
        self.Controls.Add(subtitle)

        self.folder_label = Label()
        self.folder_label.Text = "CSV folder: not selected"
        self.folder_label.Left = 30
        self.folder_label.Top = 100
        self.folder_label.Width = 900
        self.folder_label.Height = 24
        self.folder_label.ForeColor = Color.FromArgb(51, 65, 85)
        self.Controls.Add(self.folder_label)

        btn_folder = self.btn("Select CSV Folder", 1010, 92, 190, 36)
        btn_folder.Click += self.pick_folder
        self.Controls.Add(btn_folder)

        self.Controls.Add(self.header("CSV Lookup Tables", 30, 145))

        self.csv_list = CheckedListBox()
        self.csv_list.Left = 30
        self.csv_list.Top = 180
        self.csv_list.Width = 470
        self.csv_list.Height = 440
        self.csv_list.CheckOnClick = True
        self.csv_list.BackColor = Color.White
        self.csv_list.ForeColor = Color.FromArgb(15, 23, 42)
        self.csv_list.BorderStyle = BorderStyle.FixedSingle
        self.Controls.Add(self.csv_list)

        self.Controls.Add(self.header("Families by Category", 545, 145))

        self.tree = TreeView()
        self.tree.Left = 545
        self.tree.Top = 180
        self.tree.Width = 655
        self.tree.Height = 440
        self.tree.CheckBoxes = True
        self.tree.BackColor = Color.White
        self.tree.ForeColor = Color.FromArgb(15, 23, 42)
        self.tree.BorderStyle = BorderStyle.FixedSingle
        self.tree.Font = Font("Segoe UI", 9)
        self.tree.Scrollable = True
        self.tree.ShowLines = True
        self.tree.ShowPlusMinus = True
        self.tree.ShowRootLines = True
        self.tree.HideSelection = False
        self.tree.AfterCheck += self.after_check
        self.Controls.Add(self.tree)

        self.populate_tree()

        b1 = self.btn("Check all CSV", 30, 630, 135, 32)
        b1.Click += self.check_all_csv
        self.Controls.Add(b1)

        b2 = self.btn("Uncheck all CSV", 175, 630, 155, 32)
        b2.Click += self.uncheck_all_csv
        self.Controls.Add(b2)

        b3 = self.btn("Check all Families", 545, 630, 165, 32)
        b3.Click += self.check_all_families
        self.Controls.Add(b3)

        b4 = self.btn("Uncheck all Families", 720, 630, 180, 32)
        b4.Click += self.uncheck_all_families
        self.Controls.Add(b4)

        b5 = self.btn("Expand all", 910, 630, 130, 32)
        b5.Click += self.expand_all
        self.Controls.Add(b5)

        b6 = self.btn("Collapse all", 1050, 630, 150, 32)
        b6.Click += self.collapse_all
        self.Controls.Add(b6)

        note = Label()
        note.Text = "Mode: REPLACE ONLY. Families without matching existing lookup table will be skipped."
        note.Left = 30
        note.Top = 685
        note.Width = 820
        note.Height = 24
        note.ForeColor = Color.FromArgb(185, 28, 28)
        self.Controls.Add(note)

        run = Button()
        run.Text = "REPLACE"
        run.Left = 930
        run.Top = 680
        run.Width = 130
        run.Height = 42
        run.BackColor = Color.FromArgb(37, 99, 235)
        run.ForeColor = Color.White
        run.Font = Font("Segoe UI", 10, FontStyle.Bold)
        run.FlatStyle = FlatStyle.Flat
        run.Click += self.run_click
        self.Controls.Add(run)

        cancel = self.btn("Cancel", 1075, 680, 125, 42)
        cancel.Click += self.cancel_click
        self.Controls.Add(cancel)

    def header(self, text, x, y):
        l = Label()
        l.Text = text
        l.Left = x
        l.Top = y
        l.Width = 350
        l.Height = 26
        l.Font = Font("Segoe UI", 11, FontStyle.Bold)
        l.ForeColor = Color.FromArgb(30, 41, 59)
        return l

    def btn(self, text, x, y, w, h):
        b = Button()
        b.Text = text
        b.Left = x
        b.Top = y
        b.Width = w
        b.Height = h
        b.BackColor = Color.FromArgb(226, 232, 240)
        b.ForeColor = Color.FromArgb(15, 23, 42)
        b.FlatStyle = FlatStyle.Flat
        return b

    def populate_tree(self):
        self.tree.Nodes.Clear()

        for bic, cat_name in TARGET_CATEGORIES:
            fams = self.category_map.get(cat_name, {})
            label = "{:<28}  [{}]".format(cat_name, len(fams))

            parent = TreeNode(label)
            parent.Tag = None
            parent.NodeFont = Font("Segoe UI Semibold", 10, FontStyle.Bold)

            if len(fams) == 0:
                child = TreeNode("No loadable families found")
                child.Tag = None
                child.ForeColor = Color.Gray
                parent.Nodes.Add(child)
            else:
                for fam_name in sorted(fams.keys()):
                    child = TreeNode(fam_name)
                    child.Tag = fams[fam_name]
                    child.NodeFont = Font("Segoe UI", 9, FontStyle.Regular)
                    parent.Nodes.Add(child)

            self.tree.Nodes.Add(parent)
            parent.Expand()

    def after_check(self, sender, args):
        if self._checking:
            return

        self._checking = True
        try:
            node = args.Node
            for child in node.Nodes:
                if child.Tag:
                    child.Checked = node.Checked
        finally:
            self._checking = False

    def pick_folder(self, sender, args):
        dlg = FolderBrowserDialog()

        if dlg.ShowDialog() == DialogResult.OK:
            folder = dlg.SelectedPath
            self.folder_label.Text = "CSV folder: " + folder
            self.csv_files = get_csv_files(folder)
            self.csv_list.Items.Clear()

            for f in self.csv_files:
                self.csv_list.Items.Add(os.path.basename(f), True)

    def check_all_csv(self, sender, args):
        for i in range(self.csv_list.Items.Count):
            self.csv_list.SetItemChecked(i, True)

    def uncheck_all_csv(self, sender, args):
        for i in range(self.csv_list.Items.Count):
            self.csv_list.SetItemChecked(i, False)

    def check_all_families(self, sender, args):
        self._checking = True
        try:
            for p in self.tree.Nodes:
                p.Checked = True
                for c in p.Nodes:
                    if c.Tag:
                        c.Checked = True
        finally:
            self._checking = False

    def uncheck_all_families(self, sender, args):
        self._checking = True
        try:
            for p in self.tree.Nodes:
                p.Checked = False
                for c in p.Nodes:
                    c.Checked = False
        finally:
            self._checking = False

    def expand_all(self, sender, args):
        self.tree.ExpandAll()

    def collapse_all(self, sender, args):
        self.tree.CollapseAll()

    def get_checked_families(self):
        fams = []
        seen = set()

        for p in self.tree.Nodes:
            for c in p.Nodes:
                if c.Checked and c.Tag:
                    fid = eid_int(c.Tag.Id)
                    if fid not in seen:
                        fams.append(c.Tag)
                        seen.add(fid)

        return fams

    def run_click(self, sender, args):
        csvs = []

        for i in range(self.csv_list.Items.Count):
            if self.csv_list.GetItemChecked(i):
                csvs.append(self.csv_files[i])

        fams = self.get_checked_families()

        if not csvs:
            MessageBox.Show("Select at least one CSV.")
            return

        if not fams:
            MessageBox.Show("Select at least one family.")
            return

        self.result = {
            "csvs": csvs,
            "families": fams
        }

        self.DialogResult = DialogResult.OK
        self.Close()

    def cancel_click(self, sender, args):
        self.DialogResult = DialogResult.Cancel
        self.Close()


category_map = get_family_category_map()
form = MainForm(category_map)

if form.ShowDialog() != DialogResult.OK:
    script.exit()

results = []

t = Transaction(doc, "BIMBOT Replace Lookup Tables")
t.Start()

try:
    for fam in form.result["families"]:
        manager = get_manager(fam)

        if manager is None:
            results.append([fam.Name, "Skipped", "-", "No existing lookup table manager"])
            continue

        existing = get_tables(manager)
        existing_norm = dict((norm(x), x) for x in existing)

        if not existing:
            results.append([fam.Name, "Skipped", "-", "Family has no existing lookup tables"])
            continue

        for csv_path in form.result["csvs"]:
            table_name = clean_name(csv_path)
            table_norm = norm(table_name)

            if table_norm not in existing_norm:
                results.append([fam.Name, "Skipped", table_name, "No matching existing lookup table"])
                continue

            old_table = existing_norm[table_norm]

            if not remove_table(manager, old_table):
                results.append([fam.Name, "Error", table_name, "Could not remove existing table"])
                continue

            before = set(get_tables(manager))
            imported = import_table(manager, csv_path)
            after = set(get_tables(manager))

            if imported and (table_name in after or len(after - before) > 0):
                results.append([fam.Name, "Replaced", table_name, "OK"])
            else:
                results.append([fam.Name, "Error", table_name, "ImportSizeTable returned False"])

    t.Commit()

except Exception as ex:
    try:
        t.RollBack()
    except:
        pass

    results.append(["-", "Fatal Error", "-", str(ex)])


output.print_md("# Lookup Table Replacer - Report")
output.print_md("Mode: **Replacement only**")

output.print_table(
    table_data=results,
    columns=["Family", "Status", "CSV / Table", "Details"]
)