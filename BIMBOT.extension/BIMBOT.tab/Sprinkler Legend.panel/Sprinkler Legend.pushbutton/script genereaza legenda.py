# -*- coding: utf-8 -*-
"""
BIMBOT - Automatic Sprinkler Legend

Creates or updates a Revit Legend containing:

    SPRINKLER LEGEND

    SYMBOL | TYPE | COUNT

SOURCE
------
The tool can be executed from:

1. A model plan:
   - reads sprinklers visible in the active view.

2. A sheet:
   - reads sprinklers visible in all supported model viewports
     placed on the active sheet;
   - removes duplicate sprinklers by ElementId;
   - places the generated Legend automatically on the sheet.

TEMPLATE
--------
A Revit Legend named exactly:

    SPRINKLER_Template

The template can contain multiple native Revit Legend Components.
Each component must have its correct sprinkler Component Type selected.

OUTPUT
------
If executed from a model view:

    SPRINKLER_LEGEND_<View Name>

If executed from a sheet:

    SPRINKLER_LEGEND_<Sheet Number>

The script attempts to reproduce the sprinkler symbol color from:
1. element override;
2. applicable view filters;
3. category override.

Compatible with:
    pyRevit / IronPython
    Revit 2022-2026
"""

__title__ = "Sprinkler\nLegend"
__author__ = "Sabin / BIMBOT"
__doc__ = "Generate a sprinkler Legend with Symbol, Type and Count."


import clr
import re
import traceback

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    CopyPasteOptions,
    CurveElement,
    Element,
    ElementId,
    ElementTransformUtils,
    FamilyInstance,
    FamilySymbol,
    FilteredElementCollector,
    Line,
    OverrideGraphicSettings,
    ParameterFilterElement,
    StorageType,
    TextNote,
    TextNoteOptions,
    TextNoteType,
    Transaction,
    TransactionStatus,
    Transform,
    View,
    ViewDuplicateOption,
    Viewport,
    ViewSheet,
    ViewType,
    XYZ
)

from Autodesk.Revit.UI import TaskDialog
from System.Collections.Generic import List


# ============================================================
# CONFIGURATION
# ============================================================

TEMPLATE_LEGEND_NAME = "SPRINKLER_Template"
OUTPUT_LEGEND_PREFIX = "SPRINKLER_LEGEND_"

OUTPUT_LEGEND_SCALE = 50
TITLE_TEXT = "SPRINKLER LEGEND"

# ------------------------------------------------------------
# TABLE LAYOUT
# Values are millimetres measured on paper.
# ------------------------------------------------------------

TABLE_LEFT_MM = 0.0
SYMBOL_COLUMN_END_MM = 32.0
TYPE_COLUMN_END_MM = 132.0
TABLE_RIGHT_MM = 155.0

TITLE_X_MM = 0.0

SYMBOL_TEXT_X_MM = 4.0
TYPE_TEXT_X_MM = 35.0
COUNT_TEXT_X_MM = 136.0

TITLE_SPACE_MM = 12.0
HEADER_HEIGHT_MM = 9.0
ROW_HEIGHT_MM = 14.0

TEXT_TOP_MARGIN_MM = 2.0

# Width available for wrapped Type text.
TYPE_TEXT_WIDTH_MM = (
    TYPE_COLUMN_END_MM
    - SYMBOL_COLUMN_END_MM
    - 6.0
)

# Sheet placement coordinates.
SHEET_POSITION_X_MM = 220.0
SHEET_POSITION_Y_MM = 80.0

# Preferred text sizes.
BODY_TEXT_SIZE_MM = 2.5
TITLE_TEXT_SIZE_MM = 4.0


# ============================================================
# REVIT CONTEXT
# ============================================================

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
active_view = doc.ActiveView


# ============================================================
# BASIC HELPERS
# ============================================================

def show_message(message):
    TaskDialog.Show(
        "BIMBOT - Sprinkler Legend",
        message
    )


def mm_to_feet(value_mm):
    return float(value_mm) / 304.8


def feet_to_mm(value_feet):
    return float(value_feet) * 304.8


def paper_mm_to_view_feet(value_mm, view_scale):
    """
    Convert a paper distance to model-space feet inside a Legend.
    """
    try:
        scale = int(view_scale)
    except:
        scale = OUTPUT_LEGEND_SCALE

    if scale <= 0:
        scale = OUTPUT_LEGEND_SCALE

    return mm_to_feet(value_mm) * scale


def get_id_value(element_id):
    """
    Supports both older and newer ElementId APIs.
    """
    if element_id is None:
        return -1

    try:
        return int(element_id.Value)
    except:
        pass

    try:
        return int(element_id.IntegerValue)
    except:
        return -1


def valid_element(element):
    if element is None:
        return False

    try:
        return bool(element.IsValidObject)
    except:
        return True


def get_element_name(element):
    if not valid_element(element):
        return ""

    try:
        return Element.Name.GetValue(element)
    except:
        pass

    try:
        return element.Name
    except:
        return ""


def transaction_is_started(transaction):
    try:
        return (
            transaction.GetStatus()
            == TransactionStatus.Started
        )
    except:
        return False


def rollback_transaction(transaction):
    try:
        if transaction_is_started(transaction):
            transaction.RollBack()
    except:
        pass


def sanitize_view_name(value):
    if not value:
        return "Unnamed"

    result = value

    invalid_characters = [
        "\\", "/", ":", "{", "}", "[", "]",
        "|", ";", "<", ">", "?", "`", "~"
    ]

    for character in invalid_characters:
        result = result.replace(character, "-")

    result = re.sub(
        r"\s+",
        " ",
        result
    ).strip()

    if len(result) > 120:
        result = result[:120]

    return result


# ============================================================
# SOURCE VIEW DETECTION
# ============================================================

def is_supported_model_view(view):
    if not valid_element(view):
        return False

    try:
        if view.IsTemplate:
            return False
    except:
        return False

    unsupported_types = [
        ViewType.DrawingSheet,
        ViewType.Legend,
        ViewType.Schedule,
        ViewType.ProjectBrowser,
        ViewType.SystemBrowser,
        ViewType.Internal,
        ViewType.Report,
        ViewType.Rendering
    ]

    try:
        if view.ViewType in unsupported_types:
            return False
    except:
        return False

    return True


def get_model_view_ids_from_sheet(sheet):
    """
    Return supported model views placed as Viewports on the sheet.
    """
    result = []
    processed_ids = set()

    for viewport_id in sheet.GetAllViewports():

        viewport = doc.GetElement(
            viewport_id
        )

        if not valid_element(viewport):
            continue

        if not isinstance(viewport, Viewport):
            continue

        try:
            view_id = viewport.ViewId
        except:
            continue

        view_key = get_id_value(
            view_id
        )

        if view_key < 0:
            continue

        if view_key in processed_ids:
            continue

        view = doc.GetElement(
            view_id
        )

        if not is_supported_model_view(view):
            continue

        processed_ids.add(
            view_key
        )

        result.append(
            view_id
        )

    return result


def get_source_information():
    """
    Returns:
        source_view_ids
        source_name
        sheet_id
        source_description
    """

    if isinstance(active_view, ViewSheet):

        source_ids = get_model_view_ids_from_sheet(
            active_view
        )

        return (
            source_ids,
            active_view.SheetNumber,
            active_view.Id,
            "Sheet {0}".format(
                active_view.SheetNumber
            )
        )

    if is_supported_model_view(active_view):

        view_name = get_element_name(
            active_view
        )

        return (
            [active_view.Id],
            view_name,
            ElementId.InvalidElementId,
            "View {0}".format(
                view_name
            )
        )

    return (
        [],
        "",
        ElementId.InvalidElementId,
        ""
    )


# ============================================================
# SPRINKLER COLLECTION
# ============================================================

def collect_unique_sprinklers(view_ids):
    """
    Collect unique sprinklers and remember a source view for each one.

    Output:
        [
            {
                "element_id": ElementId,
                "view_id": ElementId
            }
        ]
    """
    unique_items = {}

    for view_id in view_ids:

        try:
            collector = (
                FilteredElementCollector(
                    doc,
                    view_id
                )
                .OfCategory(
                    BuiltInCategory.OST_Sprinklers
                )
                .WhereElementIsNotElementType()
            )
        except:
            continue

        for sprinkler in collector:

            if not valid_element(sprinkler):
                continue

            if not isinstance(
                sprinkler,
                FamilyInstance
            ):
                continue

            try:
                if sprinkler.ViewSpecific:
                    continue
            except:
                pass

            element_key = get_id_value(
                sprinkler.Id
            )

            if element_key < 0:
                continue

            if element_key not in unique_items:

                unique_items[element_key] = {
                    "element_id": sprinkler.Id,
                    "view_id": view_id
                }

    return list(
        unique_items.values()
    )


def get_family_name(symbol):
    if not valid_element(symbol):
        return ""

    try:
        family = symbol.Family

        if valid_element(family):
            return get_element_name(
                family
            )
    except:
        pass

    try:
        parameter = symbol.get_Parameter(
            BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM
        )

        if parameter is not None:
            return parameter.AsString() or ""
    except:
        pass

    return ""


def group_sprinklers_by_type(sprinkler_items):
    """
    Groups sprinklers by Revit FamilySymbol type.
    """
    grouped = {}

    for item in sprinkler_items:

        sprinkler_id = item["element_id"]
        source_view_id = item["view_id"]

        sprinkler = doc.GetElement(
            sprinkler_id
        )

        if not valid_element(sprinkler):
            continue

        try:
            type_id = sprinkler.GetTypeId()
        except:
            continue

        type_key = get_id_value(
            type_id
        )

        if type_key < 0:
            continue

        symbol = doc.GetElement(
            type_id
        )

        if not valid_element(symbol):
            continue

        if not isinstance(
            symbol,
            FamilySymbol
        ):
            continue

        type_name = get_element_name(
            symbol
        )

        if not type_name:
            type_name = "<Unnamed Type>"

        family_name = get_family_name(
            symbol
        )

        if type_key not in grouped:

            grouped[type_key] = {
                "type_id": type_id,
                "type_key": type_key,
                "family_name": family_name,
                "type_name": type_name,
                "count": 0,
                "sample_element_id": sprinkler_id,
                "sample_view_id": source_view_id
            }

        grouped[type_key]["count"] += 1

    rows = list(
        grouped.values()
    )

    rows.sort(
        key=lambda row: (
            row["family_name"].lower(),
            row["type_name"].lower()
        )
    )

    return rows


# ============================================================
# LEGEND HELPERS
# ============================================================

def find_legend_id_by_name(name):
    collector = (
        FilteredElementCollector(doc)
        .OfClass(View)
    )

    for view in collector:

        if not valid_element(view):
            continue

        try:
            if view.ViewType != ViewType.Legend:
                continue
        except:
            continue

        if get_element_name(view) == name:
            return view.Id

    return ElementId.InvalidElementId


def get_legend_component_parameter(element):
    """
    Legend Components have no dedicated public API class.

    They are identified using the LEGEND_COMPONENT parameter.
    """
    if not valid_element(element):
        return None

    try:
        parameter = element.get_Parameter(
            BuiltInParameter.LEGEND_COMPONENT
        )
    except:
        parameter = None

    if parameter is None:
        return None

    try:
        if parameter.StorageType != StorageType.ElementId:
            return None
    except:
        pass

    return parameter


def get_legend_component_ids(view_id):
    result = []

    collector = (
        FilteredElementCollector(
            doc,
            view_id
        )
        .WhereElementIsNotElementType()
    )

    for element in collector:

        if not valid_element(element):
            continue

        parameter = get_legend_component_parameter(
            element
        )

        if parameter is not None:
            result.append(
                element.Id
            )

    return result


def build_template_symbol_map(template_view_id):
    """
    Maps each sprinkler FamilySymbol type to its template component.

    Output:
        {
            type_id_integer: legend_component_id
        }
    """
    symbol_map = {}

    component_ids = get_legend_component_ids(
        template_view_id
    )

    for component_id in component_ids:

        component = doc.GetElement(
            component_id
        )

        if not valid_element(component):
            continue

        parameter = get_legend_component_parameter(
            component
        )

        if parameter is None:
            continue

        try:
            component_type_id = parameter.AsElementId()
        except:
            continue

        type_key = get_id_value(
            component_type_id
        )

        if type_key < 0:
            continue

        if type_key not in symbol_map:
            symbol_map[type_key] = component_id

    return symbol_map


def validate_template(template_view_id):
    if get_id_value(template_view_id) < 0:

        return False, (
            "The sprinkler template Legend was not found.\n\n"
            "Create a Legend named exactly:\n\n"
            "{0}".format(TEMPLATE_LEGEND_NAME)
        )

    template_view = doc.GetElement(
        template_view_id
    )

    if not valid_element(template_view):

        return False, (
            "SPRINKLER_Template is not a valid Legend View."
        )

    component_ids = get_legend_component_ids(
        template_view_id
    )

    if len(component_ids) == 0:

        return False, (
            "SPRINKLER_Template contains no native "
            "Legend Components.\n\n"
            "Use:\n\n"
            "Annotate > Component > Legend Component\n\n"
            "Place the required sprinkler symbols inside "
            "SPRINKLER_Template."
        )

    symbol_map = build_template_symbol_map(
        template_view_id
    )

    if len(symbol_map) == 0:

        return False, (
            "The components inside SPRINKLER_Template "
            "do not have valid sprinkler Component Types."
        )

    return True, ""


def create_output_legend(
    template_view_id,
    output_name
):
    template_view = doc.GetElement(
        template_view_id
    )

    if not valid_element(template_view):

        raise Exception(
            "SPRINKLER_Template is invalid."
        )

    new_view_id = template_view.Duplicate(
        ViewDuplicateOption.Duplicate
    )

    doc.Regenerate()

    new_view = doc.GetElement(
        new_view_id
    )

    if not valid_element(new_view):

        raise Exception(
            "Revit could not duplicate SPRINKLER_Template."
        )

    new_view.Name = output_name

    try:
        new_view.Scale = OUTPUT_LEGEND_SCALE
    except:
        pass

    doc.Regenerate()

    return new_view_id


def delete_output_legend_content(output_view_id):
    """
    Deletes only the generated view content.

    The Legend View itself is never deleted.
    """
    output_view = doc.GetElement(
        output_view_id
    )

    if not valid_element(output_view):

        raise Exception(
            "The generated Legend View is invalid."
        )

    delete_ids = List[ElementId]()

    collector = (
        FilteredElementCollector(
            doc,
            output_view_id
        )
        .WhereElementIsNotElementType()
    )

    for element in collector:

        if not valid_element(element):
            continue

        element_id = element.Id

        if get_id_value(element_id) == get_id_value(
            output_view_id
        ):
            continue

        should_delete = False

        if get_legend_component_parameter(element) is not None:
            should_delete = True

        elif isinstance(element, TextNote):
            should_delete = True

        elif isinstance(element, CurveElement):
            should_delete = True

        if should_delete:
            delete_ids.Add(
                element_id
            )

    if delete_ids.Count > 0:
        doc.Delete(
            delete_ids
        )

    doc.Regenerate()


# ============================================================
# TEXT NOTE TYPES
# ============================================================

def get_text_type_size_mm(text_type):
    if not valid_element(text_type):
        return None

    try:
        parameter = text_type.get_Parameter(
            BuiltInParameter.TEXT_SIZE
        )

        if parameter is None:
            return None

        return feet_to_mm(
            parameter.AsDouble()
        )
    except:
        return None


def get_closest_text_note_type_id(target_size_mm):
    """
    Select the existing TextNoteType with the closest text size.
    """
    text_types = list(
        FilteredElementCollector(doc)
        .OfClass(TextNoteType)
    )

    if len(text_types) == 0:
        return ElementId.InvalidElementId

    closest_type = None
    closest_difference = None

    for text_type in text_types:

        size_mm = get_text_type_size_mm(
            text_type
        )

        if size_mm is None:
            continue

        difference = abs(
            size_mm - target_size_mm
        )

        if (
            closest_difference is None
            or difference < closest_difference
        ):
            closest_difference = difference
            closest_type = text_type

    if closest_type is not None:
        return closest_type.Id

    return text_types[0].Id


# ============================================================
# LEGEND COMPONENT COPY
# ============================================================

def copy_template_component(
    template_view_id,
    output_view_id,
    template_component_id
):
    template_view = doc.GetElement(
        template_view_id
    )

    output_view = doc.GetElement(
        output_view_id
    )

    template_component = doc.GetElement(
        template_component_id
    )

    if not valid_element(template_view):
        raise Exception(
            "SPRINKLER_Template is invalid."
        )

    if not valid_element(output_view):
        raise Exception(
            "The output Legend is invalid."
        )

    if not valid_element(template_component):
        raise Exception(
            "A template sprinkler component is invalid."
        )

    source_ids = List[ElementId]()
    source_ids.Add(
        template_component_id
    )

    options = CopyPasteOptions()

    copied_ids = ElementTransformUtils.CopyElements(
        template_view,
        source_ids,
        output_view,
        Transform.Identity,
        options
    )

    doc.Regenerate()

    if copied_ids is None:
        raise Exception(
            "The sprinkler symbol could not be copied."
        )

    if copied_ids.Count == 0:
        raise Exception(
            "The sprinkler symbol could not be copied."
        )

    copied_id = copied_ids[0]

    copied_component = doc.GetElement(
        copied_id
    )

    if not valid_element(copied_component):
        raise Exception(
            "The copied sprinkler symbol is invalid."
        )

    return copied_id


def change_component_type(
    component_id,
    sprinkler_type_id
):
    component = doc.GetElement(
        component_id
    )

    if not valid_element(component):
        return False, "Copied component is invalid."

    parameter = get_legend_component_parameter(
        component
    )

    if parameter is None:
        return False, (
            "Component Type parameter was not found."
        )

    try:
        if parameter.IsReadOnly:
            return False, (
                "Component Type parameter is read-only."
            )
    except:
        pass

    try:
        parameter.Set(
            sprinkler_type_id
        )

        doc.Regenerate()

        component = doc.GetElement(
            component_id
        )

        if not valid_element(component):

            return False, (
                "The Legend Component became invalid "
                "after changing its type."
            )

        parameter = get_legend_component_parameter(
            component
        )

        if parameter is None:

            return False, (
                "Component Type parameter disappeared."
            )

        actual_type_id = parameter.AsElementId()

        if get_id_value(actual_type_id) != get_id_value(
            sprinkler_type_id
        ):

            return False, (
                "Revit did not accept this sprinkler type."
            )

        return True, ""

    except Exception as exception:

        return False, str(exception)


# ============================================================
# ELEMENT POSITIONING
# ============================================================

def get_element_center(
    element_id,
    view_id
):
    element = doc.GetElement(
        element_id
    )

    view = doc.GetElement(
        view_id
    )

    if not valid_element(element):
        return XYZ(0, 0, 0)

    try:
        location = element.Location

        if location is not None:

            try:
                point = location.Point

                if point is not None:
                    return point
            except:
                pass
    except:
        pass

    if valid_element(view):

        try:
            box = element.get_BoundingBox(
                view
            )

            if box is not None:
                return (
                    box.Min + box.Max
                ) * 0.5
        except:
            pass

    try:
        box = element.get_BoundingBox(
            None
        )

        if box is not None:
            return (
                box.Min + box.Max
            ) * 0.5
    except:
        pass

    return XYZ(0, 0, 0)


def move_element_to(
    element_id,
    view_id,
    target_point
):
    current_point = get_element_center(
        element_id,
        view_id
    )

    movement = (
        target_point - current_point
    )

    ElementTransformUtils.MoveElement(
        doc,
        element_id,
        movement
    )

    doc.Regenerate()


# ============================================================
# TEXT AND DETAIL LINES
# ============================================================

def create_text(
    view_id,
    point,
    value,
    text_type_id
):
    options = TextNoteOptions(
        text_type_id
    )

    return TextNote.Create(
        doc,
        view_id,
        point,
        value,
        options
    )


def create_wrapped_text(
    view_id,
    point,
    width,
    value,
    text_type_id
):
    """
    Creates a TextNote with an explicit width, allowing wrapping.
    """
    options = TextNoteOptions(
        text_type_id
    )

    try:
        return TextNote.Create(
            doc,
            view_id,
            point,
            width,
            value,
            options
        )

    except:
        # Fallback for an API/version where the width overload
        # is not available through IronPython.
        return TextNote.Create(
            doc,
            view_id,
            point,
            value,
            options
        )


def create_detail_line(
    view_id,
    start_point,
    end_point
):
    view = doc.GetElement(
        view_id
    )

    if not valid_element(view):
        raise Exception(
            "The output Legend View is invalid."
        )

    line = Line.CreateBound(
        start_point,
        end_point
    )

    return doc.Create.NewDetailCurve(
        view,
        line
    )


# ============================================================
# COLOR / GRAPHIC OVERRIDES
# ============================================================

def color_is_valid(color):
    if color is None:
        return False

    try:
        return bool(color.IsValid)
    except:
        pass

    try:
        return (
            int(color.Red) >= 0
            and int(color.Green) >= 0
            and int(color.Blue) >= 0
        )
    except:
        return False


def get_override_color(override_settings):
    """
    Read the most useful visible color from OverrideGraphicSettings.
    """
    if override_settings is None:
        return None

    color_property_names = [
        "ProjectionLineColor",
        "SurfaceForegroundPatternColor",
        "SurfaceBackgroundPatternColor",
        "CutLineColor",
        "CutForegroundPatternColor",
        "CutBackgroundPatternColor"
    ]

    for property_name in color_property_names:

        try:
            color = getattr(
                override_settings,
                property_name
            )

            if color_is_valid(color):
                return color
        except:
            pass

    return None


def get_direct_element_color(
    source_view,
    sprinkler_id
):
    try:
        overrides = source_view.GetElementOverrides(
            sprinkler_id
        )
    except:
        return None

    return get_override_color(
        overrides
    )


def filter_contains_category(
    parameter_filter,
    category_id
):
    if not valid_element(parameter_filter):
        return False

    try:
        categories = parameter_filter.GetCategories()
    except:
        return True

    target_value = get_id_value(
        category_id
    )

    for filter_category_id in categories:

        if get_id_value(
            filter_category_id
        ) == target_value:
            return True

    return False


def get_ordered_filter_ids(view):
    """
    Uses GetOrderedFilters when available.
    Falls back to GetFilters on older API versions.
    """
    try:
        return list(
            view.GetOrderedFilters()
        )
    except:
        pass

    try:
        return list(
            view.GetFilters()
        )
    except:
        return []


def element_passes_parameter_filter(
    parameter_filter,
    element
):
    if not valid_element(parameter_filter):
        return False

    if not valid_element(element):
        return False

    try:
        element_filter = (
            parameter_filter.GetElementFilter()
        )
    except:
        return False

    if element_filter is None:
        return False

    try:
        return bool(
            element_filter.PassesFilter(
                element
            )
        )
    except:
        pass

    try:
        return bool(
            element_filter.PassesFilter(
                doc,
                element.Id
            )
        )
    except:
        return False


def get_filter_color_for_element(
    source_view,
    element
):
    """
    Attempts to identify an applicable parameter-filter color.

    When several filters apply, the last applicable valid color
    encountered in view order is retained.
    """
    if not valid_element(source_view):
        return None

    if not valid_element(element):
        return None

    applicable_color = None

    filter_ids = get_ordered_filter_ids(
        source_view
    )

    for filter_id in filter_ids:

        try:
            if not source_view.GetFilterVisibility(
                filter_id
            ):
                continue
        except:
            pass

        filter_element = doc.GetElement(
            filter_id
        )

        if not isinstance(
            filter_element,
            ParameterFilterElement
        ):
            continue

        if element.Category is not None:

            if not filter_contains_category(
                filter_element,
                element.Category.Id
            ):
                continue

        if not element_passes_parameter_filter(
            filter_element,
            element
        ):
            continue

        try:
            overrides = source_view.GetFilterOverrides(
                filter_id
            )
        except:
            continue

        color = get_override_color(
            overrides
        )

        if color_is_valid(color):
            applicable_color = color

    return applicable_color


def get_category_color(
    source_view,
    element
):
    if not valid_element(source_view):
        return None

    if not valid_element(element):
        return None

    category = element.Category

    if category is None:
        return None

    try:
        overrides = source_view.GetCategoryOverrides(
            category.Id
        )
    except:
        return None

    return get_override_color(
        overrides
    )


def get_sprinkler_display_color(
    source_view_id,
    sprinkler_id
):
    """
    Attempts to reproduce the visible symbol color.

    Priority:
    1. direct element override;
    2. view filter override;
    3. category override.
    """
    source_view = doc.GetElement(
        source_view_id
    )

    sprinkler = doc.GetElement(
        sprinkler_id
    )

    if not valid_element(source_view):
        return None

    if not valid_element(sprinkler):
        return None

    color = get_direct_element_color(
        source_view,
        sprinkler_id
    )

    if color_is_valid(color):
        return color

    color = get_filter_color_for_element(
        source_view,
        sprinkler
    )

    if color_is_valid(color):
        return color

    color = get_category_color(
        source_view,
        sprinkler
    )

    if color_is_valid(color):
        return color

    return None


def apply_symbol_color(
    legend_view_id,
    symbol_component_id,
    color
):
    if not color_is_valid(color):
        return False

    legend_view = doc.GetElement(
        legend_view_id
    )

    symbol_component = doc.GetElement(
        symbol_component_id
    )

    if not valid_element(legend_view):
        return False

    if not valid_element(symbol_component):
        return False

    settings = OverrideGraphicSettings()

    try:
        settings.SetProjectionLineColor(
            color
        )
    except:
        pass

    try:
        settings.SetCutLineColor(
            color
        )
    except:
        pass

    try:
        settings.SetSurfaceForegroundPatternColor(
            color
        )
    except:
        pass

    try:
        settings.SetSurfaceBackgroundPatternColor(
            color
        )
    except:
        pass

    try:
        settings.SetCutForegroundPatternColor(
            color
        )
    except:
        pass

    try:
        settings.SetCutBackgroundPatternColor(
            color
        )
    except:
        pass

    legend_view.SetElementOverrides(
        symbol_component_id,
        settings
    )

    return True


# ============================================================
# LEGEND GENERATION
# ============================================================

def rebuild_legend(
    template_view_id,
    output_view_id,
    rows
):
    missing_template_symbols = []
    failed_symbols = []
    colored_symbols = 0

    output_view = doc.GetElement(
        output_view_id
    )

    if not valid_element(output_view):
        raise Exception(
            "The output Legend View is invalid."
        )

    try:
        output_view.Scale = OUTPUT_LEGEND_SCALE
    except:
        pass

    legend_scale = OUTPUT_LEGEND_SCALE

    template_symbol_map = build_template_symbol_map(
        template_view_id
    )

    template_component_ids = get_legend_component_ids(
        template_view_id
    )

    if len(template_component_ids) == 0:

        raise Exception(
            "SPRINKLER_Template contains no Legend Components."
        )

    fallback_component_id = (
        template_component_ids[0]
    )

    delete_output_legend_content(
        output_view_id
    )

    output_view = doc.GetElement(
        output_view_id
    )

    if not valid_element(output_view):

        raise Exception(
            "The generated Legend was deleted unexpectedly."
        )

    try:
        output_view.Scale = OUTPUT_LEGEND_SCALE
    except:
        pass

    body_text_type_id = get_closest_text_note_type_id(
        BODY_TEXT_SIZE_MM
    )

    title_text_type_id = get_closest_text_note_type_id(
        TITLE_TEXT_SIZE_MM
    )

    if get_id_value(body_text_type_id) < 0:

        raise Exception(
            "No Text Note Type exists in the project."
        )

    if get_id_value(title_text_type_id) < 0:
        title_text_type_id = body_text_type_id

    # --------------------------------------------------------
    # CONVERT TABLE DIMENSIONS
    # --------------------------------------------------------

    left_x = paper_mm_to_view_feet(
        TABLE_LEFT_MM,
        legend_scale
    )

    symbol_column_x = paper_mm_to_view_feet(
        SYMBOL_COLUMN_END_MM,
        legend_scale
    )

    type_column_x = paper_mm_to_view_feet(
        TYPE_COLUMN_END_MM,
        legend_scale
    )

    right_x = paper_mm_to_view_feet(
        TABLE_RIGHT_MM,
        legend_scale
    )

    title_x = paper_mm_to_view_feet(
        TITLE_X_MM,
        legend_scale
    )

    symbol_text_x = paper_mm_to_view_feet(
        SYMBOL_TEXT_X_MM,
        legend_scale
    )

    type_text_x = paper_mm_to_view_feet(
        TYPE_TEXT_X_MM,
        legend_scale
    )

    count_text_x = paper_mm_to_view_feet(
        COUNT_TEXT_X_MM,
        legend_scale
    )

    title_space = paper_mm_to_view_feet(
        TITLE_SPACE_MM,
        legend_scale
    )

    header_height = paper_mm_to_view_feet(
        HEADER_HEIGHT_MM,
        legend_scale
    )

    row_height = paper_mm_to_view_feet(
        ROW_HEIGHT_MM,
        legend_scale
    )

    text_top_margin = paper_mm_to_view_feet(
        TEXT_TOP_MARGIN_MM,
        legend_scale
    )

    type_text_width = paper_mm_to_view_feet(
        TYPE_TEXT_WIDTH_MM,
        legend_scale
    )

    # ========================================================
    # TITLE
    # ========================================================

    title_y = 0.0

    create_text(
        output_view_id,
        XYZ(
            title_x,
            title_y,
            0
        ),
        TITLE_TEXT,
        title_text_type_id
    )

    table_top_y = (
        title_y - title_space
    )

    # ========================================================
    # TABLE HEADER
    # ========================================================

    header_text_y = (
        table_top_y
        - text_top_margin
    )

    create_text(
        output_view_id,
        XYZ(
            symbol_text_x,
            header_text_y,
            0
        ),
        "SYMBOL",
        body_text_type_id
    )

    create_text(
        output_view_id,
        XYZ(
            type_text_x,
            header_text_y,
            0
        ),
        "TYPE",
        body_text_type_id
    )

    create_text(
        output_view_id,
        XYZ(
            count_text_x,
            header_text_y,
            0
        ),
        "COUNT",
        body_text_type_id
    )

    header_bottom_y = (
        table_top_y - header_height
    )

    # Top border.
    create_detail_line(
        output_view_id,
        XYZ(
            left_x,
            table_top_y,
            0
        ),
        XYZ(
            right_x,
            table_top_y,
            0
        )
    )

    # Bottom border of header.
    create_detail_line(
        output_view_id,
        XYZ(
            left_x,
            header_bottom_y,
            0
        ),
        XYZ(
            right_x,
            header_bottom_y,
            0
        )
    )

    doc.Regenerate()

    # ========================================================
    # DATA ROWS
    # ========================================================

    for index, row in enumerate(rows):

        row_top_y = (
            header_bottom_y
            - row_height * index
        )

        row_bottom_y = (
            row_top_y - row_height
        )

        row_center_y = (
            row_top_y + row_bottom_y
        ) * 0.5

        row_text_y = (
            row_top_y
            - text_top_margin
        )

        type_key = row["type_key"]

        template_component_id = (
            template_symbol_map.get(
                type_key
            )
        )

        used_fallback = False

        if template_component_id is None:

            template_component_id = (
                fallback_component_id
            )

            used_fallback = True

        copied_component_id = copy_template_component(
            template_view_id,
            output_view_id,
            template_component_id
        )

        symbol_created = True

        if used_fallback:

            success, reason = change_component_type(
                copied_component_id,
                row["type_id"]
            )

            if not success:

                try:
                    doc.Delete(
                        copied_component_id
                    )

                    doc.Regenerate()
                except:
                    pass

                create_text(
                    output_view_id,
                    XYZ(
                        symbol_text_x,
                        row_text_y,
                        0
                    ),
                    "[Missing]",
                    body_text_type_id
                )

                missing_template_symbols.append(
                    row["type_name"]
                )

                symbol_created = False

        if symbol_created:

            try:
                symbol_target_x = (
                    left_x + symbol_column_x
                ) * 0.5

                move_element_to(
                    copied_component_id,
                    output_view_id,
                    XYZ(
                        symbol_target_x,
                        row_center_y,
                        0
                    )
                )

                source_color = get_sprinkler_display_color(
                    row["sample_view_id"],
                    row["sample_element_id"]
                )

                if apply_symbol_color(
                    output_view_id,
                    copied_component_id,
                    source_color
                ):
                    colored_symbols += 1

            except Exception as exception:

                failed_symbols.append(
                    (
                        row["type_name"],
                        str(exception)
                    )
                )

        # Type text uses a fixed width to prevent overlap with Count.
        create_wrapped_text(
            output_view_id,
            XYZ(
                type_text_x,
                row_text_y,
                0
            ),
            type_text_width,
            row["type_name"],
            body_text_type_id
        )

        create_text(
            output_view_id,
            XYZ(
                count_text_x,
                row_text_y,
                0
            ),
            str(row["count"]),
            body_text_type_id
        )

        # Bottom row separator.
        create_detail_line(
            output_view_id,
            XYZ(
                left_x,
                row_bottom_y,
                0
            ),
            XYZ(
                right_x,
                row_bottom_y,
                0
            )
        )

        doc.Regenerate()

    # ========================================================
    # VERTICAL TABLE BORDERS
    # ========================================================

    table_bottom_y = (
        header_bottom_y
        - row_height * len(rows)
    )

    vertical_positions = [
        left_x,
        symbol_column_x,
        type_column_x,
        right_x
    ]

    for vertical_x in vertical_positions:

        create_detail_line(
            output_view_id,
            XYZ(
                vertical_x,
                table_top_y,
                0
            ),
            XYZ(
                vertical_x,
                table_bottom_y,
                0
            )
        )

    doc.Regenerate()

    return (
        missing_template_symbols,
        failed_symbols,
        colored_symbols
    )


# ============================================================
# SHEET PLACEMENT
# ============================================================

def find_viewport_id_on_sheet(
    sheet_id,
    view_id
):
    sheet = doc.GetElement(
        sheet_id
    )

    if not valid_element(sheet):
        return ElementId.InvalidElementId

    for viewport_id in sheet.GetAllViewports():

        viewport = doc.GetElement(
            viewport_id
        )

        if not valid_element(viewport):
            continue

        if not isinstance(
            viewport,
            Viewport
        ):
            continue

        try:
            viewport_view_id = viewport.ViewId
        except:
            continue

        if get_id_value(
            viewport_view_id
        ) == get_id_value(view_id):

            return viewport_id

    return ElementId.InvalidElementId


def place_legend_on_sheet(
    sheet_id,
    legend_view_id
):
    sheet = doc.GetElement(
        sheet_id
    )

    legend = doc.GetElement(
        legend_view_id
    )

    if not valid_element(sheet):
        raise Exception(
            "The active Sheet is invalid."
        )

    if not valid_element(legend):
        raise Exception(
            "The generated Legend is invalid."
        )

    existing_viewport_id = find_viewport_id_on_sheet(
        sheet_id,
        legend_view_id
    )

    if get_id_value(existing_viewport_id) >= 0:
        return existing_viewport_id

    can_place = Viewport.CanAddViewToSheet(
        doc,
        sheet_id,
        legend_view_id
    )

    if not can_place:

        raise Exception(
            "The generated Legend cannot be placed "
            "on the active Sheet."
        )

    placement_point = XYZ(
        mm_to_feet(
            SHEET_POSITION_X_MM
        ),
        mm_to_feet(
            SHEET_POSITION_Y_MM
        ),
        0
    )

    viewport = Viewport.Create(
        doc,
        sheet_id,
        legend_view_id,
        placement_point
    )

    doc.Regenerate()

    return viewport.Id


# ============================================================
# MAIN
# ============================================================

def main():

    (
        source_view_ids,
        source_name,
        sheet_id,
        source_description
    ) = get_source_information()

    if len(source_view_ids) == 0:

        show_message(
            "Open a Floor Plan, Engineering Plan, "
            "Ceiling Plan or a Sheet containing model views, "
            "then run the tool again."
        )

        return

    sprinkler_items = collect_unique_sprinklers(
        source_view_ids
    )

    if len(sprinkler_items) == 0:

        show_message(
            "No sprinklers were found in:\n\n"
            "{0}".format(
                source_description
            )
        )

        return

    rows = group_sprinklers_by_type(
        sprinkler_items
    )

    if len(rows) == 0:

        show_message(
            "Sprinklers were found, but their Family Types "
            "could not be read."
        )

        return

    template_view_id = find_legend_id_by_name(
        TEMPLATE_LEGEND_NAME
    )

    valid_template, validation_message = validate_template(
        template_view_id
    )

    if not valid_template:

        show_message(
            validation_message
        )

        return

    safe_source_name = sanitize_view_name(
        source_name
    )

    output_name = (
        OUTPUT_LEGEND_PREFIX
        + safe_source_name
    )

    output_view_id = find_legend_id_by_name(
        output_name
    )

    # --------------------------------------------------------
    # CREATE OUTPUT LEGEND
    # --------------------------------------------------------

    if get_id_value(output_view_id) < 0:

        create_transaction = Transaction(
            doc,
            "Create Sprinkler Legend"
        )

        try:
            create_transaction.Start()

            output_view_id = create_output_legend(
                template_view_id,
                output_name
            )

            create_transaction.Commit()

        except Exception as exception:

            rollback_transaction(
                create_transaction
            )

            show_message(
                "The output Legend could not be created.\n\n"
                "{0}\n\n"
                "{1}".format(
                    str(exception),
                    traceback.format_exc()
                )
            )

            return

    # Reacquire IDs after transaction.
    template_view_id = find_legend_id_by_name(
        TEMPLATE_LEGEND_NAME
    )

    output_view_id = find_legend_id_by_name(
        output_name
    )

    if get_id_value(template_view_id) < 0:

        show_message(
            "SPRINKLER_Template became invalid."
        )

        return

    if get_id_value(output_view_id) < 0:

        show_message(
            "The output Legend became invalid."
        )

        return

    # --------------------------------------------------------
    # GENERATE CONTENT
    # --------------------------------------------------------

    content_transaction = Transaction(
        doc,
        "Generate Sprinkler Legend Content"
    )

    missing_symbols = []
    failed_symbols = []
    colored_symbols = 0

    try:
        content_transaction.Start()

        (
            missing_symbols,
            failed_symbols,
            colored_symbols
        ) = rebuild_legend(
            template_view_id,
            output_view_id,
            rows
        )

        content_transaction.Commit()

    except Exception as exception:

        rollback_transaction(
            content_transaction
        )

        show_message(
            "The Sprinkler Legend could not be generated.\n\n"
            "{0}\n\n"
            "{1}".format(
                str(exception),
                traceback.format_exc()
            )
        )

        return

    output_view_id = find_legend_id_by_name(
        output_name
    )

    if get_id_value(output_view_id) < 0:

        show_message(
            "The generated Legend became invalid."
        )

        return

    # --------------------------------------------------------
    # PLACE LEGEND WHEN EXECUTED FROM A SHEET
    # --------------------------------------------------------

    if get_id_value(sheet_id) >= 0:

        placement_transaction = Transaction(
            doc,
            "Place Sprinkler Legend on Sheet"
        )

        try:
            placement_transaction.Start()

            place_legend_on_sheet(
                sheet_id,
                output_view_id
            )

            placement_transaction.Commit()

        except Exception as exception:

            rollback_transaction(
                placement_transaction
            )

            show_message(
                "The Legend was generated, but it could not "
                "be placed on the Sheet.\n\n"
                "{0}".format(
                    str(exception)
                )
            )

            return

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    total_count = sum(
        row["count"]
        for row in rows
    )

    result = (
        "Sprinkler Legend generated successfully.\n\n"
        "Source: {0}\n"
        "Legend: {1}\n"
        "Sprinkler types: {2}\n"
        "Sprinklers counted: {3}\n"
        "Colored symbols: {4}"
        .format(
            source_description,
            output_name,
            len(rows),
            total_count,
            colored_symbols
        )
    )

    if get_id_value(sheet_id) < 0:

        result += (
            "\n\nThe tool was executed from a model view. "
            "The Legend was created in the Project Browser "
            "and can now be placed on a Sheet."
        )

    if len(missing_symbols) > 0:

        result += (
            "\n\nMissing template symbols: {0}"
            .format(
                len(missing_symbols)
            )
        )

        for type_name in missing_symbols[:10]:

            result += (
                "\n- {0}".format(
                    type_name
                )
            )

        if len(missing_symbols) > 10:

            result += (
                "\n- ... and {0} more"
                .format(
                    len(missing_symbols) - 10
                )
            )

    if len(failed_symbols) > 0:

        result += (
            "\n\nSymbols that could not be positioned: {0}"
            .format(
                len(failed_symbols)
            )
        )

        for type_name, reason in failed_symbols[:10]:

            result += (
                "\n- {0}: {1}".format(
                    type_name,
                    reason
                )
            )

    show_message(
        result
    )


if __name__ == "__main__":
    main()