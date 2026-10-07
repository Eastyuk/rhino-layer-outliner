#! python3
"""
Layer Outliner for Rhino 8 (Python 3)  v3.2

Opens a floating window with the layer tree and the objects on each layer.
- Click an object: Rhino selects it (and zooms to it if "Zoom to selection" is on).
- Click a layer: Rhino selects all selectable objects on that layer (not sublayers).
- Ctrl+click or Shift+click to pick more than one row.
- Show column: tick or clear to show or hide. On an object row this hides the
  object (Rhino Hide/Show). On a layer row this turns the layer on or off.
- Right-click: Hide, Show, Isolate, Unisolate, Show all hidden.
- Rename: select a row, then click the name again or press F2. Type, press Enter.
- Ctrl+Z in Rhino undoes renames and hide/show.
- Press Refresh after you add or delete objects in Rhino. The list is not live.

Alias macro (change the path to where you saved the file):
  _-ScriptEditor _Run "C:\\path\\to\\LayerOutliner.py"

MIT License. See LICENSE in the repository.
"""
import System
import Rhino
import scriptcontext as sc
import Eto.Forms as forms
import Eto.Drawing as drawing

STICKY_KEY = "layer_outliner_form"

# Index into each row's Values array (not the column order on screen)
V_NAME, V_INFO, V_TYPE, V_SHOW = 0, 1, 2, 3

H_SHOW = "Show"
H_NAME = "Name"


def active_doc():
    return Rhino.RhinoDoc.ActiveDoc


def make_item(name, info, kind, shown, tag, expanded=False):
    item = forms.TreeGridItem()
    item.Values = System.Array[System.Object]([name, info, kind, bool(shown)])
    item.Tag = tag
    item.Expanded = expanded
    return item


def text_column(header, index, width=None, editable=False):
    col = forms.GridColumn()
    col.HeaderText = header
    col.DataCell = forms.TextBoxCell(index)
    col.Editable = editable
    if width:
        col.Width = width
    return col


def check_column(header, index, width=50):
    col = forms.GridColumn()
    col.HeaderText = header
    col.DataCell = forms.CheckBoxCell(index)
    col.Editable = True
    col.Width = width
    return col


def make_cell(ctrl):
    c = forms.TableCell()
    c.Control = ctrl
    return c


def make_row(ctrl, scale_height=False):
    r = forms.TableRow()
    r.Cells.Add(make_cell(ctrl))
    r.ScaleHeight = scale_height
    return r


def make_stack_item(ctrl):
    s = forms.StackLayoutItem()
    s.Control = ctrl
    return s


def menu_item(text, handler):
    m = forms.ButtonMenuItem()
    m.Text = text
    m.Click += handler
    return m


def defer(fn):
    """Run fn after the current UI event finishes (avoids changing the tree mid-edit)."""
    forms.Application.Instance.AsyncInvoke(System.Action(fn))


def report_error(where, ex, status=None):
    msg = "Outliner error in %s: %s" % (where, ex)
    Rhino.RhinoApp.WriteLine(msg)
    if status is not None:
        try:
            status.Text = msg
        except Exception:
            pass


def collect_objects(doc):
    """Return {layer_index: [RhinoObject, ...]} in one pass over the document."""
    s = Rhino.DocObjects.ObjectEnumeratorSettings()
    s.NormalObjects = True
    s.HiddenObjects = True
    s.LockedObjects = True
    s.DeletedObjects = False
    s.IncludeLights = True
    s.IncludeGrips = False
    by_layer = {}
    for obj in doc.Objects.GetObjectList(s):
        by_layer.setdefault(obj.Attributes.LayerIndex, []).append(obj)
    return by_layer


def object_info(obj):
    tags = []
    if not obj.Attributes.Name:
        tags.append("unnamed")
    if obj.IsHidden:
        tags.append("hidden")
    elif obj.IsLocked:
        tags.append("locked")
    return ", ".join(tags)


def layer_info(layer, count):
    tags = []
    if not layer.IsVisible:
        tags.append("off")
    if layer.IsLocked:
        tags.append("locked")
    info = "%d" % count
    if tags:
        info += "  [" + ", ".join(tags) + "]"
    return info


def collect_expanded(collection, out):
    if collection is None:
        return
    for item in collection:
        if item.Expanded and item.Tag is not None:
            out.add(str(item.Tag))
        collect_expanded(item.Children, out)


def set_object_visible(doc, gid, visible):
    obj = doc.Objects.FindId(gid)
    if obj is None:
        return False, "object no longer exists"
    if visible:
        ok = doc.Objects.Show(obj, True)
    else:
        if obj.IsLocked:
            return False, "locked objects cannot be hidden"
        ok = doc.Objects.Hide(obj, True)
    return bool(ok), ""


def set_layer_visible(doc, idx, visible):
    layer = doc.Layers.FindIndex(idx)
    if layer is None or layer.IsDeleted:
        return False, "layer no longer exists"
    if not visible and idx == doc.Layers.CurrentLayerIndex:
        return False, "cannot turn off the current layer"
    layer.IsVisible = visible
    return bool(layer.CommitChanges()), ""


def build_form():
    form = forms.Form()
    form.Title = "Layer Outliner"
    form.ClientSize = drawing.Size(560, 700)
    form.Resizable = True

    tree = forms.TreeGridView()
    tree.ShowHeader = True
    tree.AllowMultipleSelection = True
    tree.Columns.Add(check_column(H_SHOW, V_SHOW))
    tree.Columns.Add(text_column(H_NAME, V_NAME, 250, editable=True))
    tree.Columns.Add(text_column("Info", V_INFO, 130))
    tree.Columns.Add(text_column("Type", V_TYPE))

    refresh = forms.Button()
    refresh.Text = "Refresh"
    zoom = forms.CheckBox()
    zoom.Text = "Zoom to selection"
    zoom.Checked = True
    hide_empty = forms.CheckBox()
    hide_empty.Text = "Hide empty layers"
    hide_empty.Checked = True
    status = forms.Label()

    state = {"ids_by_layer": {}, "busy": False, "coll": None}

    def safe(fn):
        def wrapper(sender, e):
            try:
                fn(sender, e)
            except Exception as ex:
                report_error(fn.__name__, ex, status)
        return wrapper

    def later(fn):
        def run():
            try:
                fn()
            except Exception as ex:
                report_error(getattr(fn, "__name__", "deferred"), ex, status)
        defer(run)

    # ---------- build the tree ----------
    def populate(sender=None, e=None):
        state["busy"] = True
        try:
            doc = active_doc()
            expanded = set()
            collect_expanded(state["coll"], expanded)

            by_layer = collect_objects(doc)
            state["ids_by_layer"] = {k: [o.Id for o in v] for k, v in by_layer.items()}

            layers = [l for l in doc.Layers if not l.IsDeleted]
            children = {}
            for l in layers:
                children.setdefault(l.ParentLayerId, []).append(l)
            for k in children:
                children[k].sort(key=lambda l: l.SortIndex)

            counts = {"layers": 0, "objects": 0}

            def build(layer):
                subs = [build(c) for c in children.get(layer.Id, [])]
                subs = [s for s in subs if s is not None]
                objs = by_layer.get(layer.Index, [])
                if hide_empty.Checked and not objs and not subs:
                    return None

                tag = "L:%d" % layer.Index
                item = make_item(layer.Name, layer_info(layer, len(objs)), "layer",
                                 layer.IsVisible, tag, tag in expanded)
                for s in subs:
                    item.Children.Add(s)

                rows = []
                for o in objs:
                    rows.append((o.ShortDescription(False), (o.Attributes.Name or "").lower(), o))
                rows.sort(key=lambda t: (t[0], t[1]))
                for kind, _, o in rows:
                    item.Children.Add(make_item(o.Attributes.Name or "", object_info(o), kind,
                                                not o.IsHidden, "O:" + str(o.Id)))

                counts["layers"] += 1
                counts["objects"] += len(objs)
                return item

            coll = forms.TreeGridItemCollection()
            for l in children.get(System.Guid.Empty, []):
                it = build(l)
                if it is not None:
                    coll.Add(it)
            state["coll"] = coll
            tree.DataStore = coll
            status.Text = "%d layers, %d objects" % (counts["layers"], counts["objects"])
        finally:
            state["busy"] = False

    # ---------- helpers ----------
    def selected_targets():
        obj_ids, layer_idx = [], []
        for it in tree.SelectedItems:
            if it is None or it.Tag is None:
                continue
            tag = str(it.Tag)
            if tag.startswith("O:"):
                obj_ids.append(System.Guid(tag[2:]))
            else:
                layer_idx.append(int(tag[2:]))
        return obj_ids, layer_idx

    def select_in_rhino(obj_ids, layer_idx, do_zoom):
        doc = active_doc()
        ids = list(obj_ids)
        for i in layer_idx:
            ids.extend(state["ids_by_layer"].get(i, []))
        doc.Objects.UnselectAll()
        bbox = None
        count = 0
        skipped = 0
        for gid in ids:
            obj = doc.Objects.FindId(gid)
            if obj is None:
                skipped += 1
                continue
            if obj.Select(True) > 0:
                count += 1
                b = obj.Geometry.GetBoundingBox(True)
                if b.IsValid:
                    bbox = b if bbox is None else Rhino.Geometry.BoundingBox.Union(bbox, b)
            else:
                skipped += 1
        doc.Views.Redraw()
        if do_zoom and bbox is not None:
            view = doc.Views.ActiveView
            if view is not None:
                view.ActiveViewport.ZoomBoundingBox(bbox)
                view.Redraw()
        return count, skipped

    def reload_row(item):
        try:
            tree.ReloadItem(item, False)
        except Exception:
            tree.Invalidate()

    # ---------- events ----------
    def on_select(sender, e):
        if state["busy"]:
            return
        obj_ids, layer_idx = selected_targets()
        if not obj_ids and not layer_idx:
            return
        count, skipped = select_in_rhino(obj_ids, layer_idx, zoom.Checked)
        status.Text = "Selected %d, skipped %d (hidden, locked, layer off or deleted)" % (count, skipped)

    def on_edited(sender, e):
        item = e.Item
        if item is None or item.Tag is None or e.GridColumn is None:
            return
        header = e.GridColumn.HeaderText
        tag = str(item.Tag)
        doc = active_doc()

        if header == H_SHOW:
            visible = bool(item.Values[V_SHOW])
            undo = doc.BeginUndoRecord("Outliner show/hide")
            try:
                if tag.startswith("O:"):
                    ok, msg = set_object_visible(doc, System.Guid(tag[2:]), visible)
                else:
                    ok, msg = set_layer_visible(doc, int(tag[2:]), visible)
            except Exception as ex:
                ok, msg = False, str(ex)
            finally:
                doc.EndUndoRecord(undo)
            doc.Views.Redraw()

            if ok:
                if tag.startswith("O:"):
                    obj = doc.Objects.FindId(System.Guid(tag[2:]))
                    if obj is not None:
                        item.Values[V_INFO] = object_info(obj)
                else:
                    layer = doc.Layers.FindIndex(int(tag[2:]))
                    n = len(state["ids_by_layer"].get(layer.Index, []))
                    item.Values[V_INFO] = layer_info(layer, n)
                later(lambda: reload_row(item))
                status.Text = ("Shown" if visible else "Hidden") + ": " + str(item.Values[V_NAME] or item.Values[V_TYPE])
            else:
                later(populate)
                status.Text = "Not changed: " + (msg or "Rhino refused the change")
            return

        if header == H_NAME:
            new = item.Values[V_NAME]
            new = "" if new is None else str(new).strip()
            ok = False
            msg = ""
            undo = doc.BeginUndoRecord("Outliner rename")
            try:
                if tag.startswith("O:"):
                    obj = doc.Objects.FindId(System.Guid(tag[2:]))
                    if obj is None:
                        msg = "Object no longer exists. Press Refresh."
                    else:
                        attr = obj.Attributes.Duplicate()
                        attr.Name = new
                        ok = doc.Objects.ModifyAttributes(obj, attr, True)
                else:
                    layer = doc.Layers.FindIndex(int(tag[2:]))
                    if layer is None or layer.IsDeleted:
                        msg = "Layer no longer exists. Press Refresh."
                    elif not new:
                        msg = "A layer name cannot be empty."
                    elif not Rhino.DocObjects.Layer.IsValidName(new):
                        msg = "Not a valid layer name."
                    else:
                        layer.Name = new
                        ok = layer.CommitChanges()
                        if not ok:
                            msg = "Rename refused. A sibling layer may already use that name."
            except Exception as ex:
                msg = "Rename failed: %s" % ex
            finally:
                doc.EndUndoRecord(undo)

            doc.Views.Redraw()
            if ok:
                if tag.startswith("O:"):
                    obj = doc.Objects.FindId(System.Guid(tag[2:]))
                    if obj is not None:
                        item.Values[V_INFO] = object_info(obj)
                        later(lambda: reload_row(item))
                status.Text = "Renamed to '%s'" % new
            else:
                later(populate)
                status.Text = msg or "Rename failed."

    # ---------- right-click menu ----------
    def apply_visibility(visible):
        doc = active_doc()
        obj_ids, layer_idx = selected_targets()
        if not obj_ids and not layer_idx:
            status.Text = "Nothing selected in the outliner."
            return
        done = 0
        failed = 0
        undo = doc.BeginUndoRecord("Outliner show/hide")
        try:
            for gid in obj_ids:
                ok, _ = set_object_visible(doc, gid, visible)
                done += 1 if ok else 0
                failed += 0 if ok else 1
            for idx in layer_idx:
                ok, _ = set_layer_visible(doc, idx, visible)
                done += 1 if ok else 0
                failed += 0 if ok else 1
        finally:
            doc.EndUndoRecord(undo)
        doc.Views.Redraw()
        populate()
        status.Text = "%s %d, not changed %d" % ("Shown" if visible else "Hidden", done, failed)

    def on_hide(sender, e):
        later(lambda: apply_visibility(False))

    def on_show(sender, e):
        later(lambda: apply_visibility(True))

    def on_isolate(sender, e):
        later(do_isolate)

    def on_unisolate(sender, e):
        later(do_unisolate)

    def on_show_all(sender, e):
        later(do_show_all)

    def on_menu_refresh(sender, e):
        later(populate)

    def do_isolate():
        obj_ids, layer_idx = selected_targets()
        count, _ = select_in_rhino(obj_ids, layer_idx, False)
        if count == 0:
            status.Text = "Nothing visible to isolate."
            return
        Rhino.RhinoApp.RunScript("_Isolate", False)
        populate()
        status.Text = "Isolated %d objects. Use Unisolate to restore." % count

    def do_unisolate():
        Rhino.RhinoApp.RunScript("_Unisolate", False)
        populate()
        status.Text = "Unisolated."

    def do_show_all():
        Rhino.RhinoApp.RunScript("_Show", False)
        populate()
        status.Text = "All hidden objects shown."

    menu = forms.ContextMenu()
    menu.Items.Add(menu_item("Hide", safe(on_hide)))
    menu.Items.Add(menu_item("Show", safe(on_show)))
    menu.Items.Add(forms.SeparatorMenuItem())
    menu.Items.Add(menu_item("Isolate (show only these)", safe(on_isolate)))
    menu.Items.Add(menu_item("Unisolate", safe(on_unisolate)))
    menu.Items.Add(menu_item("Show all hidden objects", safe(on_show_all)))
    menu.Items.Add(forms.SeparatorMenuItem())
    menu.Items.Add(menu_item("Refresh", safe(on_menu_refresh)))
    tree.ContextMenu = menu

    def on_refresh(sender, e):
        populate()

    refresh.Click += safe(on_refresh)
    hide_empty.CheckedChanged += safe(on_refresh)
    tree.SelectionChanged += safe(on_select)
    tree.CellEdited += safe(on_edited)

    # ---------- layout ----------
    bar = forms.StackLayout()
    bar.Orientation = forms.Orientation.Horizontal
    bar.Spacing = 10
    bar.Items.Add(make_stack_item(refresh))
    bar.Items.Add(make_stack_item(zoom))
    bar.Items.Add(make_stack_item(hide_empty))

    table = forms.TableLayout()
    table.Padding = drawing.Padding(6)
    table.Spacing = drawing.Size(4, 4)
    table.Rows.Add(make_row(bar))
    table.Rows.Add(make_row(tree, scale_height=True))
    table.Rows.Add(make_row(status))
    form.Content = table

    def on_closed(sender, e):
        if STICKY_KEY in sc.sticky:
            del sc.sticky[STICKY_KEY]

    form.Closed += on_closed

    populate()
    return form


def main():
    existing = sc.sticky.get(STICKY_KEY)
    if existing is not None:
        try:
            existing.BringToFront()
            return
        except Exception:
            del sc.sticky[STICKY_KEY]
    form = build_form()
    form.Owner = Rhino.UI.RhinoEtoApp.MainWindow
    sc.sticky[STICKY_KEY] = form
    form.Show()


main()
