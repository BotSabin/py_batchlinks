# -*- coding: utf-8 -*-
__title__ = "Add +\nLink LNG"
__author__ = "Sabin"

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog
from pyrevit import revit, script

doc = revit.doc
output = script.get_output()

PARAM_NAME = "LNG"
GLOBAL_PARAM_NAME = "Local Language"

CATEGORIES = [
    BuiltInCategory.OST_PipeAccessory,
    BuiltInCategory.OST_PipeFitting,
    BuiltInCategory.OST_Sprinklers,
    BuiltInCategory.OST_MechanicalEquipment,
    BuiltInCategory.OST_GenericModel,
]


class FamilyLoadOptions(IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues = True
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        overwriteParameterValues = True
        return True


def get_id_int(eid):
    if eid is None:
        return -1
    try:
        return eid.IntegerValue
    except:
        try:
            return eid.Value
        except:
            return -1


def safe_name(e):
    try:
        return e.Name
    except:
        return "<no name>"


def find_global_parameter(name):
    for gp_id in GlobalParametersManager.GetAllGlobalParameters(doc):
        gp = doc.GetElement(gp_id)
        if gp and gp.Name == name:
            return gp_id
    return None


def find_param(elem, name):
    if not elem:
        return None

    try:
        p = elem.LookupParameter(name)
        if p:
            return p
    except:
        pass

    try:
        for p in elem.Parameters:
            try:
                if p.Definition.Name == name:
                    return p
            except:
                pass
    except:
        pass

    return None


def family_has_param(fam_doc, name):
    fm = fam_doc.FamilyManager

    try:
        for p in fm.Parameters:
            try:
                if p.Definition.Name == name:
                    return True
            except:
                pass
    except:
        pass

    return False


def add_lng_family_parameter(fam_doc):
    fm = fam_doc.FamilyManager

    if family_has_param(fam_doc, PARAM_NAME):
        return False, "already exists"

    t = Transaction(fam_doc, "Add LNG parameter")
    t.Start()

    try:
        # Revit 2022+
        try:
            group_id = GroupTypeId.Text
            spec_id = SpecTypeId.String.Text
            fm.AddParameter(PARAM_NAME, group_id, spec_id, False)  # False = Type parameter
        except:
            # Revit older fallback
            fm.AddParameter(PARAM_NAME, BuiltInParameterGroup.PG_TEXT, ParameterType.Text, False)

        t.Commit()
        return True, "added"

    except Exception as ex:
        if t.HasStarted():
            t.RollBack()
        return False, str(ex)


def collect_family_symbols():
    symbols = {}

    for bic in CATEGORIES:
        try:
            elems = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
            for e in elems:
                try:
                    tid = e.GetTypeId()
                    if get_id_int(tid) == -1:
                        continue

                    typ = doc.GetElement(tid)
                    if not typ:
                        continue

                    fam = typ.Family
                    if not fam:
                        continue

                    symbols[get_id_int(typ.Id)] = typ
                except:
                    pass
        except:
            pass

    return symbols.values()


def get_families_missing_lng(symbols):
    fams = {}

    for typ in symbols:
        p = find_param(typ, PARAM_NAME)

        if not p:
            try:
                fam = typ.Family
                if fam and fam.IsEditable:
                    fams[get_id_int(fam.Id)] = fam
            except:
                pass

    return fams.values()


def add_lng_to_families(families):
    added = []
    skipped = []
    failed = []

    for fam in families:
        fam_name = safe_name(fam)

        try:
            fam_doc = doc.EditFamily(fam)
        except Exception as ex:
            failed.append("{} | cannot edit family | {}".format(fam_name, ex))
            continue

        try:
            did_add, msg = add_lng_family_parameter(fam_doc)

            if did_add:
                try:
                    fam_doc.LoadFamily(doc, FamilyLoadOptions())
                    added.append(fam_name)
                except Exception as ex:
                    failed.append("{} | reload failed | {}".format(fam_name, ex))
            else:
                skipped.append("{} | {}".format(fam_name, msg))

        except Exception as ex:
            failed.append("{} | {}".format(fam_name, ex))

        try:
            fam_doc.Close(False)
        except:
            pass

    return added, skipped, failed


def is_already_linked(param):
    try:
        gp_id = param.GetAssociatedGlobalParameter()
        return gp_id and get_id_int(gp_id) != -1
    except:
        return False


def can_link(param, gp_id):
    if not param:
        return False, "parameter not found"

    try:
        if param.IsReadOnly:
            return False, "read-only"
    except:
        pass

    try:
        if not param.CanBeAssociatedWithGlobalParameters():
            return False, "cannot be associated with global parameters"
    except:
        pass

    try:
        if not param.CanBeAssociatedWithGlobalParameter(gp_id):
            return False, "not compatible with Local Language"
    except Exception as ex:
        return False, str(ex)

    return True, ""


def link_lng_to_global(symbols, gp_id):
    linked = []
    skipped = []
    failed = []

    t = Transaction(doc, "Link LNG to Local Language")
    t.Start()

    for typ in symbols:
        label = "{} | Type Id {}".format(safe_name(typ), get_id_int(typ.Id))

        try:
            p = find_param(typ, PARAM_NAME)

            if not p:
                skipped.append("{} | LNG still not found".format(label))
                continue

            if is_already_linked(p):
                skipped.append("{} | already linked".format(label))
                continue

            ok, reason = can_link(p, gp_id)

            if ok:
                try:
                    p.AssociateWithGlobalParameter(gp_id)
                    linked.append(label)
                except Exception as ex:
                    failed.append("{} | {}".format(label, ex))
            else:
                skipped.append("{} | {}".format(label, reason))

        except Exception as ex:
            failed.append("{} | {}".format(label, ex))

    t.Commit()

    return linked, skipped, failed


def main():
    if doc.IsFamilyDocument:
        TaskDialog.Show("Add + Link LNG", "Run this inside the project, not inside Family Editor.")
        return

    gp_id = find_global_parameter(GLOBAL_PARAM_NAME)

    if not gp_id:
        TaskDialog.Show(
            "Add + Link LNG",
            "Global Parameter '{}' was not found.".format(GLOBAL_PARAM_NAME)
        )
        return

    symbols_before = list(collect_family_symbols())
    families_missing = list(get_families_missing_lng(symbols_before))

    added, add_skipped, add_failed = add_lng_to_families(families_missing)

    symbols_after = list(collect_family_symbols())
    linked, link_skipped, link_failed = link_lng_to_global(symbols_after, gp_id)

    output.print_md("# BIMBOT - Add + Link LNG Report")
    output.print_md("")
    output.print_md("**Family Parameter:** `LNG`")
    output.print_md("")
    output.print_md("**Global Parameter:** `Local Language`")
    output.print_md("---")

    output.print_md("## Families where LNG was added: {}".format(len(added)))
    for x in added:
        output.print_md("- {}".format(x))

    output.print_md("")
    output.print_md("## Types linked to Local Language: {}".format(len(linked)))
    for x in linked:
        output.print_md("- {}".format(x))

    output.print_md("")
    output.print_md("## Add skipped: {}".format(len(add_skipped)))
    for x in add_skipped[:200]:
        output.print_md("- {}".format(x))

    output.print_md("")
    output.print_md("## Link skipped: {}".format(len(link_skipped)))
    for x in link_skipped[:300]:
        output.print_md("- {}".format(x))

    output.print_md("")
    output.print_md("## Failed: {}".format(len(add_failed) + len(link_failed)))
    for x in add_failed:
        output.print_md("- ADD FAILED | {}".format(x))
    for x in link_failed:
        output.print_md("- LINK FAILED | {}".format(x))

    TaskDialog.Show(
        "Add + Link LNG",
        "Done.\n\nFamilies LNG added: {}\nTypes linked: {}\nFailed: {}\n\nCheck pyRevit output.".format(
            len(added),
            len(linked),
            len(add_failed) + len(link_failed)
        )
    )


main()