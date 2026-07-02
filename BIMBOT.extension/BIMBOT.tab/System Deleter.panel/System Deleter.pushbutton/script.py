# -*- coding: utf-8 -*-
__title__ = "System\nDeleter"

from pyrevit import revit, DB, script

import clr
import re

clr.AddReference("System")
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Collections.Generic import List
from System.Windows.Forms import (
    Form, TextBox, CheckedListBox, Button, Label,
    DialogResult, MessageBox, MessageBoxButtons, MessageBoxIcon,
    FormStartPosition, AnchorStyles, FlatStyle
)
from System.Drawing import Size, Point, Font, FontStyle, Color, ContentAlignment


doc = revit.doc


def get_all_mep_systems():
    systems = []

    categories = [
        DB.BuiltInCategory.OST_PipingSystem,
        DB.BuiltInCategory.OST_DuctSystem,
        DB.BuiltInCategory.OST_ElectricalCircuit
    ]

    for cat in categories:
        try:
            elems = DB.FilteredElementCollector(doc)\
                .OfCategory(cat)\
                .WhereElementIsNotElementType()\
                .ToElements()

            for elem in elems:
                try:
                    name = elem.Name
                except:
                    name = "<No Name>"

                if not name:
                    name = "<No Name>"

                systems.append((name, elem))
        except:
            pass

    systems.sort(key=lambda x: x[0].lower())
    return systems


def get_system_element_ids(system):
    ids = set()

    for attr in ["Elements", "PipingNetwork", "DuctNetwork"]:
        try:
            for elem in getattr(system, attr):
                if elem:
                    ids.add(elem.Id)
        except:
            pass

    try:
        if system.BaseEquipment:
            ids.add(system.BaseEquipment.Id)
    except:
        pass

    return list(ids)


class SystemDeleterForm(Form):

    def __init__(self, systems):
        Form.__init__(self)

        self.systems = systems
        self.filtered_systems = systems
        self.selected_systems = []

        self.Text = "System Deleter"
        self.Size = Size(430, 680)
        self.MinimumSize = Size(430, 680)
        self.StartPosition = FormStartPosition.CenterScreen
        self.BackColor = Color.FromArgb(245, 245, 245)

        self.title_label = Label()
        self.title_label.Text = "SYSTEM DELETER"
        self.title_label.Font = Font("Segoe UI", 13, FontStyle.Bold)
        self.title_label.Location = Point(15, 20)
        self.title_label.Size = Size(390, 30)
        self.title_label.TextAlign = ContentAlignment.MiddleCenter
        self.Controls.Add(self.title_label)

        self.subtitle_label = Label()
        self.subtitle_label.Text = "Select the systems you want to delete"
        self.subtitle_label.Font = Font("Segoe UI", 9)
        self.subtitle_label.Location = Point(15, 52)
        self.subtitle_label.Size = Size(390, 20)
        self.subtitle_label.TextAlign = ContentAlignment.MiddleCenter
        self.Controls.Add(self.subtitle_label)

        self.search_box = TextBox()
        self.search_box.Font = Font("Segoe UI", 10)
        self.search_box.Location = Point(15, 95)
        self.search_box.Size = Size(390, 30)
        self.search_box.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
        self.search_box.Text = "Search..."
        self.search_box.ForeColor = Color.Gray
        self.search_box.GotFocus += self.search_focus
        self.search_box.LostFocus += self.search_blur
        self.search_box.TextChanged += self.filter_list
        self.Controls.Add(self.search_box)

        self.listbox = CheckedListBox()
        self.listbox.CheckOnClick = True
        self.listbox.IntegralHeight = False
        self.listbox.Font = Font("Segoe UI", 10)
        self.listbox.Location = Point(15, 140)
        self.listbox.Size = Size(390, 370)
        self.listbox.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.Controls.Add(self.listbox)

        self.count_label = Label()
        self.count_label.Font = Font("Segoe UI", 9)
        self.count_label.Location = Point(15, 520)
        self.count_label.Size = Size(390, 20)
        self.count_label.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.Controls.Add(self.count_label)

        self.warning_label = Label()
        self.warning_label.Text = "Warning: All elements belonging to the selected systems will be permanently deleted."
        self.warning_label.Font = Font("Segoe UI", 8, FontStyle.Bold)
        self.warning_label.ForeColor = Color.DarkRed
        self.warning_label.Location = Point(15, 545)
        self.warning_label.Size = Size(390, 35)
        self.warning_label.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.warning_label.TextAlign = ContentAlignment.MiddleCenter
        self.Controls.Add(self.warning_label)

        self.delete_button = Button()
        self.delete_button.Text = "DELETE SELECTED SYSTEMS"
        self.delete_button.Font = Font("Segoe UI", 9, FontStyle.Bold)
        self.delete_button.Location = Point(15, 595)
        self.delete_button.Size = Size(390, 38)
        self.delete_button.Anchor = AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
        self.delete_button.FlatStyle = FlatStyle.Flat
        self.delete_button.BackColor = Color.FromArgb(220, 0, 0)
        self.delete_button.ForeColor = Color.White
        self.delete_button.Click += self.on_delete
        self.Controls.Add(self.delete_button)

        self.populate_list()
        self.ActiveControl = self.listbox

    def search_focus(self, sender, event):
        if self.search_box.Text == "Search...":
            self.search_box.Text = ""
            self.search_box.ForeColor = Color.Black

    def search_blur(self, sender, event):
        if self.search_box.Text.strip() == "":
            self.search_box.Text = "Search..."
            self.search_box.ForeColor = Color.Gray

    def normalize_text(self, text):
        return re.sub(r'[^a-z0-9]', '', text.lower())

    def name_matches_search(self, system_name, search_text):
        if not search_text:
            return True

        name = self.normalize_text(system_name)
        search = self.normalize_text(search_text)

        if search == "":
            return True

        # Example:
        # wet1  -> Fire Protection Wet 1
        # fire1 -> Fire Protection Wet 1
        # wet13 -> Fire Protection Wet 13
        if search in name:
            return True

        # Split letters/numbers:
        # fire1 -> ["fire", "1"]
        # wet13 -> ["wet", "13"]
        parts = re.findall(r'[a-z]+|\d+', search)

        for part in parts:
            if part not in name:
                return False

        return True

    def populate_list(self):
        self.listbox.Items.Clear()

        for name, system in self.filtered_systems:
            self.listbox.Items.Add(name, False)

        self.update_count()

    def update_count(self):
        self.count_label.Text = "Systems shown: {0} / Total systems: {1}".format(
            len(self.filtered_systems),
            len(self.systems)
        )

    def get_checked_ids(self):
        checked_ids = []

        for i in range(self.listbox.Items.Count):
            if self.listbox.GetItemChecked(i):
                item_name = str(self.listbox.Items[i])

                for name, system in self.filtered_systems:
                    if name == item_name:
                        checked_ids.append(system.Id.IntegerValue)
                        break

        return checked_ids

    def filter_list(self, sender, event):
        if self.search_box.Text == "Search...":
            return

        checked_ids = self.get_checked_ids()

        search_text = self.search_box.Text.strip()
        self.filtered_systems = []

        for name, system in self.systems:
            if self.name_matches_search(name, search_text):
                self.filtered_systems.append((name, system))

        self.listbox.Items.Clear()

        for name, system in self.filtered_systems:
            checked = system.Id.IntegerValue in checked_ids
            self.listbox.Items.Add(name, checked)

        self.update_count()

    def on_delete(self, sender, event):
        selected = []

        for i in range(self.listbox.Items.Count):
            if self.listbox.GetItemChecked(i):
                selected_name = str(self.listbox.Items[i])

                for name, system in self.filtered_systems:
                    if name == selected_name:
                        selected.append(system)
                        break

        if len(selected) == 0:
            MessageBox.Show(
                "No system selected.",
                "System Deleter",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            )
            return

        confirm = MessageBox.Show(
            "You are about to permanently delete the selected system(s) and all associated elements.\n\nDo you want to continue?",
            "Delete Systems",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning
        )

        if confirm != DialogResult.Yes:
            return

        self.selected_systems = selected
        self.DialogResult = DialogResult.OK
        self.Close()


systems = get_all_mep_systems()

if len(systems) == 0:
    MessageBox.Show(
        "No systems were found in this project.",
        "System Deleter",
        MessageBoxButtons.OK,
        MessageBoxIcon.Information
    )
    script.exit()

form = SystemDeleterForm(systems)
result = form.ShowDialog()

if result == DialogResult.OK:
    all_ids = set()

    for system in form.selected_systems:
        for elem_id in get_system_element_ids(system):
            all_ids.add(elem_id)

    ids_to_delete = List[DB.ElementId]()

    for elem_id in all_ids:
        ids_to_delete.Add(elem_id)

    if ids_to_delete.Count == 0:
        MessageBox.Show(
            "No elements were found inside the selected systems.",
            "System Deleter",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information
        )
        script.exit()

    try:
        with revit.Transaction("Delete Selected Systems"):
            deleted_ids = doc.Delete(ids_to_delete)
            deleted_count = deleted_ids.Count

        MessageBox.Show(
            "Done.\n\nDeleted elements: {0}".format(deleted_count),
            "System Deleter",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information
        )

    except Exception as ex:
        MessageBox.Show(
            "Delete failed:\n\n{0}".format(ex),
            "System Deleter",
            MessageBoxButtons.OK,
            MessageBoxIcon.Error
        )