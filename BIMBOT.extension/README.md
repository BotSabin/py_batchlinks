# BIMBOT pyRevit Extension

A comprehensive **BIM tools extension for Autodesk Revit** powered by pyRevit. This extension provides streamlined workflows for managing Revit links (RVT and IFC files) and DWG drafting operations.

## Features

### 🔗 Batch Links Manager
- **Load multiple RVT links** - Batch import Revit link files
- **Load multiple IFC links** - Import multiple IFC files simultaneously
- **Reload selected links** - Refresh specific links without reloading the entire project
- **Unload For Me** - Unload links for your session only
- **Unload For All** - Unload links for all users in the workset
- **Multi-select workflow** - Select and manage multiple links at once
- **Enhanced UI** - XAML-based interface for intuitive link management

### 📐 IFC Tools
- **Analyze IFC** - Inspect and analyze IFC file properties
- **Filter IFC** - Filter and organize IFC elements by category
- **Link IFC** - Link IFC files into Revit projects

### 🖼️ DWG Tools
- **DWG to Drafting RVT** - Convert DWG files to Revit drafting views

---

## System Requirements

- **Revit** 2021 or newer
- **pyRevit** 4.8+ (pyRevit Master or Student edition)
- Python 3.7+

---

## Installation

### Option 1: Using pyRevit Extensions Manager (Recommended)

1. Open Revit and go to **pyRevit → Extensions → Settings**
2. Search for `py_batchlinks` in the extension manager
3. Click **Install** and restart Revit

### Option 2: Manual Installation

1. Download this repository as ZIP or clone it:
   ```bash
   git clone https://github.com/BotSabin/py_batchlinks.git
   ```

2. Copy the `BIMBOT.extension` folder to your pyRevit extensions directory:
   - **Windows**: `%APPDATA%\pyRevit\extensions\`
   - Or place in your custom pyRevit extensions folder if configured

3. Restart Revit

4. Verify installation:
   - Open Revit and check the **BIMBOT** tab at the top ribbon
   - You should see the **Batch Links**, **IFC Tools**, and **DWG Tools** panels

---

## Usage

### Batch Links Manager

1. Click **BIMBOT → Batch Links → Batch Links** in the Revit ribbon
2. The UI will display current links and available options
3. Select links you want to manage
4. Choose your action:
   - **Load** - Load one or multiple link files
   - **Reload** - Refresh selected links
   - **Unload For Me** - Unload for your session only
   - **Unload For All** - Unload for all workset users

### IFC Tools

- **Analyze IFC** - Click to inspect IFC file properties
- **Filter IFC** - Filter elements by category (structure, MEP, architecture, etc.)
- **Link IFC** - Import and link IFC files into your model

### DWG Tools

- **DWG to Drafting RVT** - Convert imported DWG entities to Revit drafting elements

---

## Project Structure

```
BIMBOT.extension/
├── extension.json                          # Extension manifest
├── extensions.json                         # Extension metadata
├── README.md                               # Documentation
└── BIMBOT.tab/
    ├── Batch Links.panel/
    │   └── Batch Links.pushbutton/
    │       ├── bundle.yaml                # Button configuration
    │       ├── script.py                  # Main logic
    │       ├── script_.py                 # Backup script
    │       ├── ui.xaml                    # UI design
    │       ├── ui_.xaml                   # UI backup
    │       ├── settings.json              # User settings
    │       └── icon.png                   # Button icon
    ├── IFC Tools.panel/
    │   ├── Analyze IFC.pushbutton/
    │   │   └── script.py
    │   ├── Filter IFC.pushbutton/
    │   │   └── script.py
    │   └── Link IFC.pushbutton/
    │       └── script.py
    └── DWG Tools.panel/
        └── DWG To Drafting RVT.pushbutton/
            └── script.py
```

---

## Troubleshooting

### Extension not showing in Revit

1. Verify the installation path is correct
2. Restart Revit completely (close all instances)
3. Check pyRevit extensions are enabled: **pyRevit → Settings → Extensions → Enable**
4. Verify `extension.json` and `bundle.yaml` files are present and valid

### UI not loading

- Ensure XAML files (`ui.xaml`, `ui_.xaml`) are in the button directory
- Verify settings.json is properly formatted JSON

### Links not loading

- Check file paths are accessible from your computer
- Verify Revit permissions for link loading
- Try reloading individual links first

---

## Development

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Open a Pull Request

### Modifying Scripts

Each button's logic is in the corresponding `script.py` file. Modify as needed and restart Revit to test changes.

---

## License

This extension is provided as-is for use with Autodesk Revit and pyRevit.

## Author

**Sabin Bot** - BIM Automation & Revit Tools

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/BotSabin/py_batchlinks/issues
- Contact: Check repository for contact details

---

## Version History

**v1.0.0** (2026-06-23)
- Initial release
- Batch links management
- IFC tools suite
- DWG conversion tools

---

**Happy linking! 🔗**

