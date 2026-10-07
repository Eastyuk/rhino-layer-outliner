# Layer Outliner for Rhino 8

A small outliner window for Rhino 8: the layer tree with every object listed under its layer. Rhino's Layers panel shows layers only. This shows what is on them.

<img width="649" height="297" alt="screenshot-menu" src="https://github.com/user-attachments/assets/88071db3-34a1-4ee6-9ef2-201d3dd2136f" />


## Features

- Layer tree that matches the Rhino Layers panel, with the object count on each layer
- Objects listed under each layer, sorted by type, with name and tags (hidden, locked, unnamed)
- Click an object to select it in Rhino and zoom to it
- Click a layer to select everything on it
- Ctrl+click or Shift+click to select more than one row
- **Show** checkbox: hide or show an object, or turn a layer off or on
- Right-click menu: Hide, Show, Isolate, Unisolate, Show all hidden objects
- Rename objects and layers in place (click the name again or press F2)
- Ctrl+Z in Rhino undoes renames and hide/show

## Requirements

- Rhino 8 for Windows (tested)
- Rhino 8 for Mac: not tested yet. Reports are welcome.

No plugins or other installs needed. It uses the Python 3 and Eto that come with Rhino 8.

## Install

1. Download `LayerOutliner.py` and save it in a permanent folder.
2. In Rhino, open **Tools > Options > Aliases**, click **New**, and add:
   - Alias: `LO`
   - Command macro: `_-ScriptEditor _Run "C:\path\to\LayerOutliner.py"`
3. Type `LO` in Rhino to open the outliner.

You can also open the file in `ScriptEditor` and click Run.

## Use

| To do this | Do this |
|---|---|
| Select an object in Rhino | Click its row |
| Select all objects on a layer | Click the layer row |
| Hide or show | Clear or tick the Show checkbox, or right-click > Hide / Show |
| Show only some objects | Select rows, right-click > Isolate. Unisolate restores. |
| Rename | Select the row, click the name again or press F2, type, press Enter |
| Update the list | Click Refresh |

## Limits

- The list does not update by itself. Click **Refresh** after you add or delete objects.
- Hidden objects, locked objects and objects on layers that are off are listed but cannot be selected. The status line counts them as skipped.
- Rhino does not hide locked objects and does not turn off the current layer. The status line tells you when that happens.
- The Show checkbox can need two clicks: one to select the row, one to toggle.

## Report a problem

Open an issue. Include your Rhino version (Help > About) and any line on the command line that starts with `Outliner error`.

## License

MIT. See [LICENSE](LICENSE).
