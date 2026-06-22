# -*- coding: utf-8 -*-

from pyrevit import revit, forms, script
from pyrevit.forms import WPFWindow
from Autodesk.Revit.DB import *
from Microsoft.Win32 import OpenFileDialog
from System.Collections.Generic import Dictionary
from System import String
import os
import clr
import System

doc = revit.doc
uidoc = __revit__.ActiveUIDocument
uiapp = __revit__
app = uiapp.Application
output = script.get_output()


def load_ifc_engine():
    revit_exe = System.Diagnostics.Process.GetCurrentProcess().MainModule.FileName
    revit_folder = os.path.dirname(revit_exe)

    for dll in [
        "Revit.IFC.Common.dll",
        "Revit.IFC.Import.Core.dll",
        "Revit.IFC.Import.dll"
    ]:
        path = os.path.join(revit_folder, dll)
        if os.path.exists(path):
            try:
                clr.AddReferenceToFileAndPath(path)
            except:
                pass


class LinkRow(object):
    def __init__(self, inst):
        self.instance = inst
        self.link_type = doc.GetElement(inst.GetTypeId())
        self.checked = False
        self.name = self.get_name()
        self.status = self.get_status()
        self.typeid = self.link_type.Id.IntegerValue
        self.link_kind = self.get_kind()

    def get_name(self):
        try:
            ldoc = self.instance.GetLinkDocument()
            if ldoc:
                return ldoc.Title
        except:
            pass

        try:
            return Element.Name.GetValue(self.link_type)
        except:
            return "Unknown Link"

    def get_status(self):
        try:
            return "Loaded" if self.instance.GetLinkDocument() else "Unloaded"
        except:
            return "Unloaded"

    def get_kind(self):
        n = self.name.lower()
        if ".ifc" in n:
            return "IFC"
        return "RVT"


class LinkManagerWindow(WPFWindow):

    def __init__(self, xaml_file):
        WPFWindow.__init__(self, xaml_file)
        self.cancel_requested = False
        self.rows = []
        self.reload_ui_rows()

        if not doc.IsWorkshared:
            try:
                self.btnUnloadForMe.IsEnabled = False
                self.btnUnloadForMe.ToolTip = "Unload For Me is only available in workshared models."
            except:
                pass

    def set_status(self, text):
        self.txtStatus.Text = text
        try:
            self.Dispatcher.Invoke(lambda: None)
        except:
            pass

    def set_progress(self, current, total):
        if total <= 0:
            self.pbProgress.Value = 0
            return
        self.pbProgress.Value = int((float(current) / float(total)) * 100.0)

    def cancel_process(self, sender, args):
        self.cancel_requested = True
        self.set_status("Cancel requested...")

    def load_links(self, sender, args):
        self.cancel_requested = False

        dialog = OpenFileDialog()
        dialog.Title = "Select RVT or IFC files"
        dialog.Filter = "RVT & IFC (*.rvt;*.ifc)|*.rvt;*.ifc|RVT (*.rvt)|*.rvt|IFC (*.ifc)|*.ifc"
        dialog.Multiselect = True

        if dialog.ShowDialog() != True:
            return

        files = list(dialog.FileNames)
        total = len(files)

        for idx, filepath in enumerate(files):
            if self.cancel_requested:
                output.print_md("⚠ Cancelled by user.")
                break

            self.set_progress(idx + 1, total)
            self.set_status("Processing {} of {}: {}".format(idx + 1, total, os.path.basename(filepath)))

            ext = os.path.splitext(filepath)[1].lower()

            if ext == ".rvt":
                self.link_rvt(filepath)

            elif ext == ".ifc":
                self.link_ifc_like_manage_links(filepath)

        self.reload_ui_rows()
        self.set_status("Done")
        self.set_progress(0, 1)

    def get_existing_link_by_name(self, name):
        target = name.lower()

        for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance).WhereElementIsNotElementType():
            lt = doc.GetElement(inst.GetTypeId())
            try:
                lt_name = Element.Name.GetValue(lt).lower()
                if target in lt_name or lt_name in target:
                    return lt
            except:
                pass

        return None

    def remove_existing_link(self, link_type):
        t = Transaction(doc, "Remove Existing Link")
        try:
            t.Start()
            doc.Delete(link_type.Id)
            t.Commit()
            return True
        except Exception as ex:
            try:
                if t.HasStarted():
                    t.RollBack()
            except:
                pass
            output.print_md("❌ Could not remove existing link: {}".format(ex))
            return False

    def should_skip_or_replace(self, filepath):
        base = os.path.splitext(os.path.basename(filepath))[0]
        existing = self.get_existing_link_by_name(base)

        if not existing:
            return False

        if self.chkReplaceExisting.IsChecked:
            output.print_md("Replacing existing link: **{}**".format(base))
            self.remove_existing_link(existing)
            return False

        output.print_md("Skipped duplicate: **{}**".format(base))
        return True

    def link_rvt(self, filepath):
        if self.should_skip_or_replace(filepath):
            return

        t = Transaction(doc, "Link RVT")

        try:
            t.Start()

            relative = bool(self.chkRelativePath.IsChecked)
            options = RevitLinkOptions(relative)
            model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(filepath)

            result = RevitLinkType.Create(doc, model_path, options)
            inst = RevitLinkInstance.Create(doc, result.ElementId)

            t.Commit()

            output.print_md("✔ RVT linked: **{}**".format(filepath))
            output.print_md("Instance Id: `{}`".format(inst.Id.IntegerValue))

        except Exception as ex:
            try:
                if t.HasStarted():
                    t.RollBack()
            except:
                pass

            output.print_md("❌ RVT failed: **{}** → {}".format(filepath, ex))

    def link_ifc_like_manage_links(self, filepath):
        if self.should_skip_or_replace(filepath):
            return

        try:
            load_ifc_engine()

            folder = os.path.dirname(filepath)
            name = os.path.splitext(os.path.basename(filepath))[0]
            cache_rvt = os.path.join(folder, name + ".ifc.RVT")

            if self.chkRebuildIFC.IsChecked and os.path.exists(cache_rvt):
                try:
                    os.remove(cache_rvt)
                    output.print_md("Deleted IFC cache: **{}**".format(cache_rvt))
                except Exception as ex:
                    output.print_md("Could not delete IFC cache: **{}** → {}".format(cache_rvt, ex))

            from Revit.IFC.Import import Importer

            opts = Dictionary[String, String]()
            opts["Intent"] = "Reference"
            opts["Action"] = "Link"
            opts["ForceImport"] = "false"
            opts["Process3DGeometry"] = "true"
            opts["ProcessBoundingBoxGeometry"] = "true"
            opts["AlwaysProcessBoundingBoxGeometry"] = "false"
            opts["CreateDuplicateZoneGeometry"] = "true"
            opts["CreateDuplicateContainerGeometry"] = "true"
            opts["CreateLinkInstanceOnly"] = "false"

            importer = Importer.CreateImporter(doc, filepath, opts)

            if importer is None:
                output.print_md("❌ IFC importer could not be created: **{}**".format(filepath))
                return

            importer.ReferenceIFC(doc, filepath)

            output.print_md("✔ IFC linked using Revit IFC engine: **{}**".format(filepath))

        except Exception as ex:
            output.print_md("❌ IFC failed: **{}** → {}".format(filepath, ex))

    def reload_selected(self, sender, args):
        self.run_action("reload")

    def unload_for_me(self, sender, args):
        self.run_action("unload_me")

    def unload_for_all(self, sender, args):
        self.run_action("unload_all")

    def run_action(self, action):
        selected = [r for r in self.rows if r.checked]

        if not selected:
            forms.alert("Select at least one link.")
            return

        total = len(selected)

        for idx, r in enumerate(selected):
            if self.cancel_requested:
                break

            self.set_progress(idx + 1, total)
            self.set_status("{}: {}".format(action, r.name))

            try:
                if action == "reload":
                    r.link_type.Reload()
                    output.print_md("Reloaded: **{}**".format(r.name))

                elif action == "unload_all":
                    r.link_type.Unload(None)
                    output.print_md("Unloaded for all: **{}**".format(r.name))

                elif action == "unload_me":
                    if not doc.IsWorkshared:
                        output.print_md("Skipped: **{}** - Unload For Me is only available in workshared models.".format(r.name))
                    elif hasattr(r.link_type, "UnloadLocally"):
                        r.link_type.UnloadLocally(None)
                        output.print_md("Unloaded for me: **{}**".format(r.name))
                    else:
                        output.print_md("Failed: **{}** - Unload For Me is not available.".format(r.name))

            except Exception as ex:
                output.print_md("❌ Failed: **{}** → {}".format(r.name, ex))

        self.reload_ui_rows()
        self.set_status("Done")
        self.set_progress(0, 1)

    def check_all(self, sender, args):
        for r in self.rows:
            r.checked = True
        self.lvLinks.Items.Refresh()

    def uncheck_all(self, sender, args):
        for r in self.rows:
            r.checked = False
        self.lvLinks.Items.Refresh()

    def reload_ui_rows(self):
        instances = FilteredElementCollector(doc) \
            .OfClass(RevitLinkInstance) \
            .WhereElementIsNotElementType() \
            .ToElements()

        self.rows = [LinkRow(i) for i in instances]
        self.lvLinks.ItemsSource = self.rows
        self.lvLinks.Items.Refresh()


xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
win = LinkManagerWindow(xaml_path)
win.ShowDialog()