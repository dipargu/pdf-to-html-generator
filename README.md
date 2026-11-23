# PDF → HTML Converter

> **Status:** Work in Progress (core conversion works; layout edge cases and extra features are still being refined).

Desktop GUI tool built with Python and PyMuPDF that converts PDF files into clean HTML pages while keeping the original document structure: headings, paragraphs, lists, tables, and styles.

## Overview

The app parses a PDF page by page using PyMuPDF and generates a semantic `index.html` file along with an `imagenes/` folder for selected assets. Originally built to automate converting structured guides and formatted documents into web pages.

### Current Features

- **Table detection:** Uses `page.find_tables()` to rebuild tables as semantic HTML (`<table>`, `<tr>`, `<th>`, `<td>`) without duplicating cell text.
- **Reusable CSS classes:** Repeated styles across the document are grouped into CSS classes (`.estilo-1`, `.estilo-2`, ...) inside a `<style>` block, while unique styles stay inline to keep the output light.
- **Logical sections:** Groups content into `<div class="seccion-bloque">` containers headed by each main title.
- **Style extraction from skipped pages:** Pages marked as "skip" are not rendered in the final HTML, but are still parsed to extract base theme colors (background and text colors) from template/instruction pages.
- **Internal navigation:** Automatically adds anchor links (`inicio`, `indice`, `apartadoN`, `final`) and turns navigation text and author emails into clickable links.

## Requirements

- **Python 3.9 or higher** (`python --version`)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/dipargu/pdf-to-html-generator.git
cd pdf-to-html-generator
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
```

- **Windows (PowerShell):** `venv\Scripts\Activate.ps1`
- **Windows (CMD):** `venv\Scripts\activate.bat`
- **Linux / macOS:** `source venv/bin/activate`

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the application:

```bash
python main.py
```

| Field | Description |
| --- | --- |
| **1. PDF File** | Select the source PDF file to convert. |
| **Pages to skip** | Optional page numbers to exclude from rendering (e.g. `1`, `1,2`, `1; 3`). Leave empty to process all pages. Skipped pages are still scanned for base colors. |
| **2. Images** | Select one or more images (logos, illustrations). They are copied to `imagenes/` and inserted between text blocks. |
| **3. Project name** | Name of the output folder. |
| **Generate** | Prompts for a destination directory and creates the project folder with `index.html` and `imagenes/`. |

### Output Structure

```text
<destination>/<project-name>/
├── index.html
└── imagenes/
    └── ...
```

## Planned Improvements

- Improve layout handling for complex multi-column PDFs.
- Extract embedded PDF images automatically into the output folder.
- Generalize color and anchor detection for non-template documents.
