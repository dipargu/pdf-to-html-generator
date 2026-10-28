"""Interfaz gráfica para convertir un PDF en un sitio HTML.

Permite seleccionar un PDF, varias imágenes y un nombre de proyecto.
Al pulsar "Generar" se crea la carpeta del proyecto con un index.html
generado a partir del texto y los estilos del PDF, una subcarpeta
imagenes/ con copias de las imágenes elegidas y un bloque <style> con
las clases CSS de los estilos que se repiten en el documento.
"""

# ===========================================================================
# IMPORTS
# ===========================================================================

import html
import os
import re
import shutil

import customtkinter as ctk
import pymupdf as fitz  # PyMuPDF
from tkinter import filedialog

# ===========================================================================
# CONFIGURACIÓN Y CONSTANTES GLOBALES
# ===========================================================================

ctk.set_appearance_mode("dark")          # "dark" | "light" | "system"
ctk.set_default_color_theme("blue")      # "blue" | "green" | "dark-blue"

# Paleta de colores usada en la interfaz
COLOR_PANEL = "#1f2937"
COLOR_PANEL_BORDER = "#374151"
COLOR_TEXT_MUTED = "#9ca3af"
COLOR_SUCCESS = "#10b981"
COLOR_ERROR = "#ef4444"
COLOR_ACCENT = "#2563eb"
COLOR_ACCENT_HOVER = "#1d4ed8"

IMAGE_FILETYPES = [
    ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.svg"),
    ("Todos los archivos", "*.*"),
]

PDF_FILETYPES = [
    ("Archivos PDF", "*.pdf"),
    ("Todos los archivos", "*.*"),
]

# ===========================================================================
# PATRONES (EXPRESIONES REGULARES) Y CONSTANTES DE ANÁLISIS
# ===========================================================================

# Nº mínimo de apariciones de un estilo para convertirlo en clase CSS
MIN_USOS_PARA_CLASE = 2

# Bandera de PyMuPDF que marca un span como negrita
FLAG_NEGRITA = 2**4

# Marca interna que representa un salto de línea real dentro de un bloque.
# Se usa un carácter del área privada de Unicode (1 solo carácter) para que no
# lo alteren ni el escape de HTML ni la normalización de espacios; al emitir el
# HTML se sustituye por la etiqueta <br>.
MARCADOR_SALTO = "\ue000"

# Viñetas que pueden iniciar un elemento de lista no ordenada
# (incluye los guiones unicode −, –, — y el guion normal)
PATRON_VINETA = re.compile(r"^([•·▪‣◦○●\-–—−*+oQ])\s+")

# Numeración romana que puede iniciar un elemento de lista ordenada.
# Sirve tanto con match() (marcador al inicio del bloque) como con finditer()
# (varios apartados numerados dentro de una misma línea, como en un índice).
PATRON_ROMANO = re.compile(r"(?<![A-Za-z])(?:X{1,3}|IX|IV|V|VI{1,3}|I{1,3})\.\s+")

# Bloques que solo contienen una viñeta suelta (ej: "o", "•", "-")
PATRON_MARCADOR_SUELTO = re.compile(r"^[•·▪‣◦○●\-–—−*+oQ.]{1,2}$")

# Encabezado del índice del documento ("Indice:")
PATRON_INDICE = re.compile(r"^\s*[ÍíI]ndice\s*:", re.IGNORECASE)

# Encabezados de apartado ("APARTADO 1", "Apartado 2"...)
PATRON_APARTADO = re.compile(r"^\s*APARTADO\s+(\d+)", re.IGNORECASE)

# Línea final del autor ("Autor:alumno/ iesmarenostrum")
PATRON_AUTOR = re.compile(r"Autor\s*:\s*(.+)$", re.IGNORECASE)

# Instrucciones de estilo que suelen aparecer en la página de análisis
# ("Color de fondo de los bloques: #6699FF", "El color del texto: #3333CC").
# De esa página solo se extraen estas variables; su texto no se imprime.
PATRON_COLOR_FONDO = re.compile(
    r"color\s+de\s+fondo(?:\s+de\s+los\s+bloques)?\s*:?\s*"
    r"(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})",
    re.IGNORECASE,
)
PATRON_COLOR_TEXTO = re.compile(
    r"color\s+del\s+texto\s*:?\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})",
    re.IGNORECASE,
)

# Textos que se convierten en enlaces internos (patrón -> ancla destino)
ENLACES_INTERNOS = [
    (re.compile(r"\(?\s*vuelve al inicio\s*\)?", re.IGNORECASE), "#inicio"),
    (re.compile(r"vuelve al [íi]ndice", re.IGNORECASE), "#indice"),
    (re.compile(r"ve hasta el final", re.IGNORECASE), "#final"),
]

# Imágenes que se envuelven en un enlace: nombre -> (destino, texto alternativo)
ENLACES_IMAGENES = {
    "enfermera21.jpg": ("enfermeria21.html", "Enfermería21 y Revista Metas"),
    "users1.gif": ("usuarios.html", "Enlace a página de usuarios"),
}

# ===========================================================================
# HOJA DE ESTILOS BASE DEL HTML GENERADO
# ===========================================================================

CSS_BASE = [
    "* { box-sizing: border-box; }",
    "body {",
    "    margin: 0;",
    "    background-color: #525659;",
    "    color: #111827;",
    "    padding: 20px 0;",
    "}",
    "h1, h2, h3 {",
    "    font-weight: normal;",
    "}",
    ".contenido {",
    "    background: #ffffff;",
    "    margin: 0 auto;",
    "    box-shadow: 0 4px 10px rgba(0,0,0,0.3);",
    "    padding: 50px 60px;",
    "}",
    ".imagen {",
    "    margin: 24px 0;",
    "    text-align: center;",
    "}",
    ".imagen img {",
    "    max-width: 100%;",
    "    height: auto;",
    "    border-radius: 8px;",
    "}",
    ".seccion-bloque {",
    "    margin: 0 0 32px 0;",
    "}",
    ".tabla-pdf {",
    "    border-collapse: collapse;",
    "    width: 100%;",
    "}",
    ".tabla-pdf th,",
    ".tabla-pdf td {",
    "    border: 1px solid #ccc;",
    "    padding: 8px;",
    "}",
]


# ===========================================================================
# LÓGICA DE EXTRACCIÓN DEL PDF
# ===========================================================================


def _color_a_hex(color: int) -> str:
    """Convierte un color sRGB entero de PyMuPDF a formato #rrggbb."""
    return f"#{color & 0xFFFFFF:06x}"


def _color_rgb_a_hex(color) -> str:
    """Convierte un color (r, g, b) con valores 0-1 a formato #rrggbb."""
    canales = (max(0, min(255, round(canal * 255))) for canal in color)
    return "#%02x%02x%02x" % tuple(canales)


def _fondos_pagina(pagina) -> list:
    """Detecta los rectángulos de color de fondo dibujados en una página.

    Devuelve una lista de tuplas (rectangulo, color #rrggbb) con los rellenos
    de color que pueden actuar como fondo de un bloque de texto.
    """
    fondos = []
    for dibujo in pagina.get_drawings():
        relleno = dibujo.get("fill")
        rectangulo = dibujo.get("rect")
        if relleno is None or rectangulo is None:
            continue
        rectangulo = fitz.Rect(rectangulo)
        # Se descartan los rellenos demasiado finos (líneas, subrayados...)
        if rectangulo.width < 10 or rectangulo.height < 5:
            continue
        color = _color_rgb_a_hex(relleno)
        if color == "#ffffff":            # el fondo blanco de la página
            continue
        fondos.append((rectangulo, color))
    return fondos


def _color_fondo(bbox: tuple, fondos: list):
    """Devuelve el color de fondo que cubre un bloque de texto, si lo hay."""
    if not fondos:
        return None
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if area <= 0:
        return None

    rectangulo = fitz.Rect(bbox)
    for fondo, color in fondos:
        interseccion = rectangulo.intersect(fondo)
        if interseccion.is_empty:
            continue
        # Se aplica el fondo si cubre al menos la mitad del bloque
        if interseccion.get_area() >= 0.5 * area:
            return color
    return None


def _alineacion(bloque: dict, ancho_pagina: float) -> str:
    """Deduce la alineación de un bloque a partir de sus coordenadas X.

    Se considera centrado cuando el punto medio de todas sus líneas cae en el
    centro de la página, con una tolerancia estrecha. Así se detectan tanto los
    títulos cortos como los que ocupan casi todo el ancho del texto (cuyo borde
    izquierdo coincide con el margen del cuerpo).
    """
    lineas = bloque.get("lines", [])
    if not lineas or ancho_pagina <= 0:
        return "left"

    tolerancia = max(3.0, ancho_pagina * 0.015)
    centro_pagina = ancho_pagina / 2

    for linea in lineas:
        x0, _, x1, _ = linea.get("bbox", (0, 0, 0, 0))
        if abs((x0 + x1) / 2 - centro_pagina) > tolerancia:
            # Alguna línea no está centrada: el bloque va a la izquierda
            return "left"
    return "center"


def _es_negrita(fuente: str, flags: int) -> bool:
    """Detecta negrita por las banderas de PyMuPDF o por el nombre de fuente."""
    return bool(flags & FLAG_NEGRITA) or "bold" in fuente.lower()


def _recortar_inicio(runs: list, caracteres: int) -> list:
    """Elimina los primeros caracteres de un bloque (el marcador de lista)."""
    restantes = []
    for texto, estilo in runs:
        if caracteres > 0:
            if len(texto) <= caracteres:
                caracteres -= len(texto)
                continue
            texto = texto[caracteres:]
            caracteres = 0
        restantes.append((texto, estilo))
    return restantes


def _normalizar_runs(runs: list) -> list:
    """Une espacios repetidos, recorta los extremos y descarta runs vacíos."""
    limpios = []
    for texto, estilo in runs:
        texto = re.sub(r"\s+", " ", texto)
        if not texto:
            continue
        if limpios and limpios[-1][1] == estilo:
            limpios[-1] = (limpios[-1][0] + texto, estilo)
        else:
            limpios.append((texto, estilo))

    if limpios:
        limpios[0] = (limpios[0][0].lstrip(), limpios[0][1])
        limpios[-1] = (limpios[-1][0].rstrip(), limpios[-1][1])
        limpios = [(texto, estilo) for texto, estilo in limpios if texto]
    return limpios


def _paginas_a_omitir(texto: str) -> set:
    """Convierte el texto del campo "Páginas a omitir" en un conjunto de números.

    Acepta valores separados por comas, punto y coma o espacios ("1", "1,2",
    "1, 3; 5"). Si el campo está vacío devuelve un conjunto vacío, de modo que
    se procesan todas las páginas del documento.
    """
    omitidas = set()
    for trozo in re.split(r"[,;\s]+", texto or ""):
        if trozo.isdigit():
            omitidas.add(int(trozo))
    return omitidas


def _salto_de_linea(bbox_previa: tuple, bbox_actual: tuple,
                    ancho_bloque: float) -> bool:
    """Deduce si entre dos líneas de un bloque hay un salto de línea real.

    Se considera salto real (en el HTML se separan con ``<br>``) cuando la
    línea anterior no ocupa el ancho del bloque —el autor cortó el texto a
    mano, como en un título de dos líneas— o cuando la separación vertical
    entre ambas líneas supera el interlineado habitual de un párrafo.

    Recibe el bbox de la línea anterior, el de la línea actual y el ancho de
    la línea más ancha del bloque. Devuelve True si el salto es real.
    """
    x0_previa, y0_previa, x1_previa, y1_previa = bbox_previa
    y0_actual = bbox_actual[1]

    alto_linea = max(y1_previa - y0_previa, 1.0)
    if y0_actual - y0_previa > alto_linea * 1.6:
        return True

    ancho_linea = max(x1_previa - x0_previa, 0.0)
    return ancho_linea < ancho_bloque * 0.85


def _variables_estilo(textos: list) -> dict:
    """Extrae las variables globales de estilo de las páginas de instrucciones.

    Las páginas marcadas como "a omitir" no se imprimen, pero sí se analizan
    para buscar frases como "Color de fondo de los bloques: #6699FF" o "El
    color del texto: #3333CC". Devuelve un diccionario con las claves "fondo"
    y/o "texto" (en minúsculas) solo si se han encontrado.
    """
    variables = {}
    for texto in textos:
        if "fondo" not in variables:
            coincidencia = PATRON_COLOR_FONDO.search(texto)
            if coincidencia:
                variables["fondo"] = coincidencia.group(1).lower()
        if "texto" not in variables:
            coincidencia = PATRON_COLOR_TEXTO.search(texto)
            if coincidencia:
                variables["texto"] = coincidencia.group(1).lower()
    return variables


def _tablas_pagina(pagina) -> list:
    """Detecta las tablas de una página con ``page.find_tables()``.

    Devuelve una lista de tuplas (rectangulo, filas, cabecera), donde el
    rectángulo es el área que ocupa la tabla (para poder descartar después los
    bloques de texto que caen dentro), las filas son listas de celdas ya
    limpias y ``cabecera`` indica si la primera fila es una fila de cabecera.
    """
    tablas = []
    try:
        buscador = pagina.find_tables()
    except Exception:                      # PDF sin capa de tabla detectable
        return tablas

    for tabla in buscador.tables:
        filas = [
            [re.sub(r"\s+", " ", celda or "").strip() for celda in fila]
            for fila in tabla.extract()
        ]
        if not any(celda for fila in filas for celda in fila):
            continue                       # tabla vacía: se ignora
        tablas.append((
            fitz.Rect(tabla.bbox),
            filas,
            getattr(tabla, "header", None) is not None,
        ))
    return tablas


def _tabla_que_contiene(bbox: tuple, tablas: list):
    """Devuelve el índice de la tabla que cubre un bloque de texto, si la hay."""
    if not tablas:
        return None
    rectangulo = fitz.Rect(bbox)
    area = rectangulo.get_area()
    if area <= 0:
        return None
    for indice, (rect_tabla, _, _) in enumerate(tablas):
        interseccion = rectangulo.intersect(rect_tabla)
        if not interseccion.is_empty and interseccion.get_area() >= 0.5 * area:
            return indice
    return None


def extraer_bloques_pdf(pdf_path: str, paginas_omitidas=None) -> tuple:
    """Extrae de la página los textos y las tablas en su orden de lectura.

    Todas las líneas y spans de un mismo bloque se unen en una única lista de
    runs, separando las líneas con un espacio para no cortar las frases.

    Devuelve una tupla ``(elementos, variables)``:
    - ``elementos`` es una lista de diccionarios, uno por elemento visible del
      documento:
      - ``{"tipo": "texto", "runs": ..., "tamano": ..., "alineacion": ...,
        "fondo": ..., "padding": ...}`` para los párrafos y títulos, donde cada
        run es una tupla (texto, estilo), la alineación es "center" o "left" y
        el fondo es un color #rrggbb o None.
      - ``{"tipo": "tabla", "filas": ..., "cabecera": ...}`` para las tablas.
    - ``variables`` es un diccionario con los valores de estilo base: los
      colores extraídos de la página de instrucciones ("fondo" y/o "texto") y
      el "ancho" real (en puntos) de la primera página válida del PDF.

    Los bloques de texto que caen dentro de una tabla se descartan, de modo que
    el contenido de la tabla no se duplica en el HTML.

    ``paginas_omitidas`` es un conjunto de números de página (1 = primera). Esas
    páginas no se imprimen, pero sí se analizan para extraer las variables
    globales de estilo (colores) que se aplican al resto del documento.
    """
    omitidas = set(paginas_omitidas or ())
    elementos = []
    with fitz.open(pdf_path) as documento:
        paginas = list(documento)

        # Páginas omitidas: modo "solo análisis". De ellas solo se leen las
        # instrucciones de estilo (colores); su texto no se imprime.
        textos_analisis = [
            pagina.get_text("text")
            for numero_pagina, pagina in enumerate(paginas, start=1)
            if numero_pagina in omitidas
        ]
        variables = _variables_estilo(textos_analisis)
        fondo_base = variables.get("fondo")

        for numero_pagina, pagina in enumerate(paginas, start=1):
            if numero_pagina in omitidas:
                continue                             # se omite su contenido

            # Ancho real de la primera página válida: define el ancho del folio
            if "ancho" not in variables:
                variables["ancho"] = round(float(pagina.rect.width), 2)

            bloques_pagina = pagina.get_text("dict").get("blocks", [])
            fondos = _fondos_pagina(pagina)
            tablas = _tablas_pagina(pagina)
            tablas_emitidas = set()

            for bloque in bloques_pagina:
                if bloque.get("type") != 0:          # 0 = bloque de texto
                    continue

                bbox = bloque.get("bbox", (0, 0, 0, 0))

                # El texto de dentro de una tabla se representa con la tabla
                indice_tabla = _tabla_que_contiene(bbox, tablas)
                if indice_tabla is not None:
                    if indice_tabla not in tablas_emitidas:
                        tablas_emitidas.add(indice_tabla)
                        _, filas, cabecera = tablas[indice_tabla]
                        elementos.append({
                            "tipo": "tabla",
                            "filas": filas,
                            "cabecera": cabecera,
                        })
                    continue

                lineas = bloque.get("lines", [])
                # Línea más ancha del bloque: sirve para distinguir un ajuste
                # automático de párrafo de un salto de línea escrito a mano.
                ancho_bloque = max(
                    (linea.get("bbox", (0, 0, 0, 0))[2]
                     - linea.get("bbox", (0, 0, 0, 0))[0] for linea in lineas),
                    default=0.0,
                )

                runs = []
                bbox_previa = None
                for linea in lineas:
                    bbox_linea = linea.get("bbox", (0, 0, 0, 0))
                    # Entre líneas: <br> si el salto es real, espacio si no
                    if (runs and bbox_previa is not None
                            and _salto_de_linea(bbox_previa, bbox_linea,
                                                ancho_bloque)):
                        # El espacio que se añadió al cerrar la línea anterior
                        # se sustituye por el salto para no dejar un hueco
                        # visible antes del <br>.
                        runs[-1] = (runs[-1][0].rstrip(" ") + MARCADOR_SALTO,
                                    runs[-1][1])

                    for span in linea.get("spans", []):
                        texto = span.get("text", "")
                        if not texto:
                            continue
                        fuente = span.get("font", "sans-serif")
                        estilo = (
                            fuente,
                            round(float(span.get("size", 12)), 1),
                            _color_a_hex(int(span.get("color", 0))),
                            _es_negrita(fuente, int(span.get("flags", 0))),
                        )
                        # Los spans de una misma línea van pegados; el espacio
                        # solo se añade al terminar cada línea del bloque
                        if runs and runs[-1][1] == estilo:
                            runs[-1] = (runs[-1][0] + texto, estilo)
                        else:
                            runs.append((texto, estilo))

                    if (runs
                            and not runs[-1][0].endswith((" ", "\n", MARCADOR_SALTO))):
                        runs[-1] = (runs[-1][0] + " ", runs[-1][1])
                    bbox_previa = bbox_linea

                runs = _normalizar_runs(runs)
                if not runs:
                    continue

                # Fondo del bloque: se detecta por los rectángulos dibujados
                # bajo el texto o, si no hay, se cruza con la regla extraída de
                # la página de instrucciones (títulos "APARTADO N").
                fondo = _color_fondo(bbox, fondos)
                es_apartado = bool(PATRON_APARTADO.match("".join(t for t, _ in runs)))
                if fondo is None and es_apartado and fondo_base:
                    fondo = fondo_base

                elemento = {
                    "tipo": "texto",
                    "runs": runs,
                    "tamano": max(estilo[1] for _, estilo in runs),
                    "alineacion": _alineacion(bloque, pagina.rect.width),
                    "fondo": fondo,
                }
                if es_apartado and fondo:
                    elemento["padding"] = "15px"     # el bloque de fondo respira
                elementos.append(elemento)

            # Una tabla sin bloques de texto propios se añade igualmente
            for indice, (_, filas, cabecera) in enumerate(tablas):
                if indice not in tablas_emitidas:
                    elementos.append({
                        "tipo": "tabla",
                        "filas": filas,
                        "cabecera": cabecera,
                    })
    return elementos, variables


def _es_marcador_suelto(runs: list) -> bool:
    """Detecta bloques que solo contienen una viñeta suelta, sin texto."""
    texto = "".join(t for t, _ in runs).strip()
    return bool(PATRON_MARCADOR_SUELTO.match(texto))


def _detectar_lista(runs: list) -> tuple:
    """Detecta si un bloque es un elemento de lista y quita su marcador.

    Devuelve (tipo, runs), donde tipo es "ul" (viñeta), "ol" (numeración
    romana) o None si el bloque es un párrafo normal.
    """
    texto = "".join(t for t, _ in runs)
    for patron, tipo in ((PATRON_ROMANO, "ol"), (PATRON_VINETA, "ul")):
        coincidencia = patron.match(texto)
        if coincidencia:
            resto = _recortar_inicio(runs, coincidencia.end())
            return tipo, _normalizar_runs(resto)
    return None, runs


def _dividir_runs(runs: list, cortes: list) -> list:
    """Divide una lista de runs en varios trozos según índices de carácter."""
    caracteres = []
    for texto, estilo in runs:
        caracteres.extend((caracter, estilo) for caracter in texto)

    limites = [0] + list(cortes) + [len(caracteres)]
    partes = []
    for inicio, fin in zip(limites, limites[1:]):
        trozo = []
        for caracter, estilo in caracteres[inicio:fin]:
            if trozo and trozo[-1][1] == estilo:
                trozo[-1] = (trozo[-1][0] + caracter, estilo)
            else:
                trozo.append((caracter, estilo))
        partes.append(_normalizar_runs(trozo))
    return partes


def _dividir_romanos(runs: list) -> tuple:
    """Separa los apartados numerados en romano de un mismo bloque.

    Un índice como "I. Apartado 1 (ASANEC) II. Apartado 2 (ACIR)" es un único
    bloque del PDF, pero debe generar un <li> por apartado. Devuelve
    (prefijo, apartados), donde prefijo es el texto anterior al primer
    apartado; ambos son None si el bloque no contiene varios apartados.
    """
    texto = "".join(t for t, _ in runs)
    coincidencias = list(PATRON_ROMANO.finditer(texto))
    if len(coincidencias) < 2:
        return None, None

    partes = _dividir_runs(runs, [m.start() for m in coincidencias])

    apartados = []
    for trozo in partes[1:]:
        # _detectar_lista limpia el marcador "I." que abre cada apartado
        _, limpio = _detectar_lista(trozo)
        if limpio:
            apartados.append(limpio)

    if not apartados:
        return None, None
    return (partes[0] or None), apartados


# ===========================================================================
# LÓGICA DE GENERACIÓN DE HTML/CSS
# ===========================================================================


def _estilo_a_css(estilo: tuple) -> str:
    """Convierte una tupla de estilo en declaraciones CSS."""
    fuente, tamano, color, negrita = estilo
    declaraciones = [
        f"font-family: '{fuente}', sans-serif",
        f"font-size: {tamano:g}pt",
        f"color: {color}",
    ]
    if negrita:
        declaraciones.append("font-weight: 700")
    return "; ".join(declaraciones) + ";"


def _atributo_estilo(estilo: tuple, conteo: dict, clases: dict) -> str:
    """Devuelve class="..." si el estilo se repite, o style="..." si es único."""
    if conteo[estilo] >= MIN_USOS_PARA_CLASE:
        return f'class="{clases[estilo]}"'
    return f'style="{_estilo_a_css(estilo)}"'


def _etiqueta_para_tamano(tamano: float, tamano_cuerpo: float) -> str:
    """Elige la etiqueta HTML según el tamaño de fuente respecto al cuerpo."""
    if tamano >= tamano_cuerpo * 1.8:
        return "h1"
    if tamano >= tamano_cuerpo * 1.4:
        return "h2"
    if tamano >= tamano_cuerpo * 1.15:
        return "h3"
    return "p"


def _indice_imagenes(total_bloques: int, num_imagenes: int) -> dict:
    """Reparte las imágenes entre los bloques de texto.

    La primera imagen (el logotipo) se coloca justo detrás del primer bloque,
    es decir, dentro de la sección de información a la que pertenece, y el
    resto se reparte de forma uniforme por el documento.
    """
    if total_bloques <= 0 or num_imagenes <= 0:
        return {}

    posiciones = {}
    for i in range(num_imagenes):
        if i == 0:
            indice = 1                    # junto a la cabecera/sección de información
        else:
            indice = round(i * total_bloques / num_imagenes)
        # La imagen nunca puede ir antes del primer bloque ni partir uno
        indice = max(1, min(total_bloques, indice))
        posiciones.setdefault(indice, []).append(i)
    return posiciones


def _figura_html(nombre: str, indent: str = "        ") -> list:
    """Devuelve las líneas HTML de una imagen de la carpeta imagenes/.

    Las imágenes con un enlace asociado (logotipo y usuarios) se envuelven en
    un <a> con su texto alternativo correspondiente.
    """
    seguro = html.escape(nombre)
    destino, alt = ENLACES_IMAGENES.get(nombre.lower(), (None, nombre))
    imagen = f'<img src="imagenes/{seguro}" alt="{html.escape(alt)}">'
    if destino:
        imagen = f'<a href="{destino}">{imagen}</a>'
    return [
        f'{indent}<figure class="imagen">',
        f"{indent}    {imagen}",
        f"{indent}</figure>",
    ]


def _tabla_html(filas: list, cabecera: bool, indent: str = "        ") -> list:
    """Devuelve las líneas HTML de una tabla detectada en el PDF.

    La tabla se genera con la estructura semántica completa (<table>, <tr> y
    <td>). Si el PDF marca la primera fila como cabecera, sus celdas se emiten
    con <th> en lugar de <td>.
    """
    lineas = [f'{indent}<table class="tabla-pdf">']
    for posicion, fila in enumerate(filas):
        celda = "th" if cabecera and posicion == 0 else "td"
        lineas.append(f"{indent}    <tr>")
        for valor in fila:
            lineas.append(
                f"{indent}        <{celda}>{html.escape(valor)}</{celda}>"
            )
        lineas.append(f"{indent}    </tr>")
    lineas.append(f"{indent}</table>")
    return lineas


def _runs_del_nodo(nodo: dict) -> list:
    """Devuelve todas las listas de runs contenidas en un nodo HTML.

    Las tablas no contienen runs de texto (sus celdas se emiten aparte), por lo
    que devuelven una lista vacía.
    """
    if nodo["tipo"] == "lista":
        return nodo["items"]
    if nodo["tipo"] == "tabla":
        return []
    return [nodo["runs"]]


def _texto_del_nodo(nodo: dict) -> str:
    """Devuelve el texto plano de un nodo, uniendo los runs con espacios.

    Las marcas de salto de línea se sustituyen por un espacio para las
    búsquedas de texto (anclajes, enlaces). Al seguir ocupando un solo
    carácter, los índices que se calculan sobre este texto coinciden con los
    de las listas de runs.
    """
    texto = " ".join(
        "".join(t for t, _ in runs) for runs in _runs_del_nodo(nodo)
    )
    return texto.replace(MARCADOR_SALTO, " ")


def _quitar_duplicados_consecutivos(nodos: list) -> list:
    """Elimina los párrafos consecutivos que repiten el mismo texto.

    Evita que al final del documento aparezcan dos veces seguidas frases como
    "Vuelve al índice" o "(Vuelve al inicio)". La comparación ignora los
    espacios sobrantes y las diferencias de mayúsculas.
    """
    limpios = []
    anterior = None
    for nodo in nodos:
        if nodo["tipo"] != "parrafo":
            anterior = None
            limpios.append(nodo)
            continue
        texto = re.sub(r"\s+", " ", _texto_del_nodo(nodo)).strip().casefold()
        if texto and texto == anterior:
            continue
        anterior = texto
        limpios.append(nodo)
    return limpios


def _estilo_dominante(items: list):
    """Devuelve el estilo más frecuente entre todos los runs de una lista."""
    frecuencia = {}
    for runs in items:
        for _, estilo in runs:
            frecuencia[estilo] = frecuencia.get(estilo, 0) + 1
    if not frecuencia:
        return None
    return max(frecuencia, key=frecuencia.get)


def _atributos_lista(items: list, conteo: dict, clases: dict,
                     centrada: bool = False) -> str:
    """Atributos del elemento <ol>/<ul>: color heredado y centrado.

    Los marcadores (puntos y números) toman el color del propio <ol>/<ul>, no
    del <span> interior, por lo que si no se fija el color en el padre el
    navegador los pinta en negro. Se aplica la clase del estilo dominante si
    existe o, si no, un color inline extraído de ese mismo estilo.

    Si la lista va precedida de un bloque centrado (el título del índice), se
    empaqueta con ``width: fit-content`` y se centra con ``margin: 0 auto``,
    manteniendo el texto de los elementos alineado a la izquierda.
    """
    estilo = _estilo_dominante(items)
    clase = ""
    if (estilo is not None
            and conteo.get(estilo, 0) >= MIN_USOS_PARA_CLASE
            and estilo in clases):
        clase = f' class="{clases[estilo]}"'

    declaraciones = []
    if estilo is not None and not clase:
        declaraciones.append(f"color: {estilo[2]}")
    if centrada:
        declaraciones.append("width: fit-content")
        declaraciones.append("margin: 0 auto")
        declaraciones.append("text-align: left")

    if not declaraciones:
        return clase
    return f'{clase} style="{"; ".join(declaraciones)};"'


def _texto_html(texto: str) -> str:
    """Escapa un texto para HTML y convierte las marcas de salto en <br>."""
    return html.escape(texto).replace(MARCADOR_SALTO, "<br>")


def _elemento_html(etiqueta: str, runs: list, conteo: dict, clases: dict,
                   indent: str = "        ", id_elemento=None, href=None,
                   segmentos=None, alineacion=None, fondo=None,
                   padding=None) -> str:
    """Construye una etiqueta HTML a partir de los runs de un bloque.

    Si el bloque tiene un único estilo, este se aplica a la etiqueta; si tiene
    varios (negritas, colores...), solo esas partes se envuelven en <span>
    sin romper el párrafo. Admite un id (ancla), un enlace que envuelve todo el
    contenido (href) o varios enlaces parciales dentro del texto (segmentos).
    La alineación, el color de fondo y el relleno del bloque se aplican como
    estilo inline del propio elemento.
    """
    atributo_id = f' id="{id_elemento}"' if id_elemento else ""

    declaraciones = []
    if alineacion:
        declaraciones.append(f"text-align: {alineacion}")
    if fondo:
        declaraciones.append(f"background-color: {fondo}")
    if padding:
        declaraciones.append(f"padding: {padding}")
    bloque_css = "; ".join(declaraciones) + ";" if declaraciones else ""
    atributo_bloque = f' style="{bloque_css}"' if bloque_css else ""

    if segmentos is None and len(runs) == 1 and not href:
        texto = _texto_html(runs[0][0])
        estilo = runs[0][1]
        if conteo[estilo] >= MIN_USOS_PARA_CLASE:
            atributo = f'class="{clases[estilo]}"{atributo_bloque}'
        else:
            css = _estilo_a_css(estilo)
            if bloque_css:
                css = f"{css} {bloque_css}"
            atributo = f'style="{css}"'
        return f"{indent}<{etiqueta}{atributo_id} {atributo}>{texto}</{etiqueta}>"

    if segmentos is None:
        segmentos = [(texto, estilo, None) for texto, estilo in runs]

    contenido = "".join(
        (f'<a href="{destino}">' if destino else "")
        + f"<span {_atributo_estilo(estilo, conteo, clases)}>{_texto_html(texto)}</span>"
        + ("</a>" if destino else "")
        for texto, estilo, destino in segmentos
    )
    if href:
        contenido = f'<a href="{href}">{contenido}</a>'
    return f"{indent}<{etiqueta}{atributo_id}{atributo_bloque}>{contenido}</{etiqueta}>"


def _agrupar_nodos(bloques: list, tamano_cuerpo: float) -> list:
    """Convierte los elementos del PDF en nodos HTML.

    Las viñetas y numeraciones consecutivas del mismo tipo se agrupan en una
    sola lista <ul>/<ol>, con un <li> por cada bloque de la lista, y las tablas
    detectadas se incorporan como un nodo propio en su orden de lectura.
    """
    nodos = []
    ultimo_texto = None

    def anadir(runs: list, tamano: float, alineacion: str = None,
               fondo: str = None, tipo_lista=None, padding: str = None) -> None:
        """Añade un bloque, descartando los duplicados consecutivos."""
        nonlocal ultimo_texto
        texto = "".join(t for t, _ in runs)
        if texto == ultimo_texto:
            return                                  # duplicado consecutivo

        if tipo_lista:
            ordenada = tipo_lista == "ol"
            if (nodos and nodos[-1]["tipo"] == "lista"
                    and nodos[-1]["ordenada"] == ordenada):
                nodos[-1]["items"].append(runs)
            else:
                # La lista se centra si el bloque inmediatamente anterior era
                # un bloque centrado (el título "Indice:" de la página)
                centrada = bool(
                    nodos
                    and nodos[-1]["tipo"] == "parrafo"
                    and nodos[-1].get("alineacion") == "center"
                )
                nodos.append({
                    "tipo": "lista",
                    "ordenada": ordenada,
                    "items": [runs],
                    "centrada": centrada,
                })
        else:
            nodos.append({
                "tipo": "parrafo",
                "etiqueta": _etiqueta_para_tamano(tamano, tamano_cuerpo),
                "runs": runs,
                "alineacion": alineacion,
                "fondo": fondo,
                "padding": padding,
            })
        ultimo_texto = texto

    for bloque in bloques:
        if bloque.get("tipo") == "tabla":
            nodos.append({
                "tipo": "tabla",
                "filas": bloque["filas"],
                "cabecera": bloque["cabecera"],
            })
            ultimo_texto = None
            continue

        runs = bloque["runs"]
        tamano = bloque["tamano"]
        alineacion = bloque["alineacion"]
        fondo = bloque["fondo"]
        padding = bloque.get("padding")

        # Índice con varios apartados romanos en la misma línea
        prefijo, apartados = _dividir_romanos(runs)
        if apartados:
            if prefijo:
                anadir(prefijo, tamano, alineacion, fondo, padding=padding)
            for apartado in apartados:
                anadir(apartado, tamano, tipo_lista="ol")
            continue

        tipo_lista, runs = _detectar_lista(runs)
        if not runs or _es_marcador_suelto(runs):
            # Bloques vacíos o formados solo por una viñeta suelta: se descartan
            continue
        anadir(runs, tamano, alineacion, fondo, tipo_lista=tipo_lista,
               padding=padding)

    return nodos


def _href_mailto(texto: str) -> str:
    """Construye un enlace mailto a partir del correo de la línea del autor.

    El PDF suele escribir el correo con una barra ("alumno/ iesmarenostrum"),
    que se convierte en "alumno@iesmarenostrum.com".
    """
    texto = texto.strip().rstrip(".")
    if not texto:
        return ""
    if "@" in texto:
        return f"mailto:{texto}"

    usuario, separador, dominio = texto.partition("/")
    if not separador:
        return f"mailto:{texto}"

    usuario = usuario.strip()
    dominio = dominio.strip().replace(" ", "")
    if dominio and "." not in dominio:
        dominio += ".com"
    if not usuario or not dominio:
        return ""
    return f"mailto:{usuario}@{dominio}"


def _coincidencias_enlaces(texto: str) -> list:
    """Busca los textos que deben convertirse en enlaces internos.

    Devuelve una lista de tuplas (inicio, fin, destino) por índice de carácter.
    Las marcas de salto se leen como espacios (siguen ocupando un carácter), de
    modo que los índices devueltos son válidos sobre las listas de runs.
    """
    texto = texto.replace(MARCADOR_SALTO, " ")
    coincidencias = []
    for patron, destino in ENLACES_INTERNOS:
        for coincidencia in patron.finditer(texto):
            coincidencias.append((coincidencia.start(), coincidencia.end(), destino))
    return coincidencias


def _quitar_tramos(runs: list, tramos: list) -> list:
    """Elimina de una lista de runs los tramos de carácter indicados."""
    caracteres = []
    for texto, estilo in runs:
        caracteres.extend((caracter, estilo) for caracter in texto)

    borrar = set()
    for inicio, fin in tramos:
        borrar.update(range(max(0, inicio), min(len(caracteres), fin)))

    restantes = []
    for indice, (caracter, estilo) in enumerate(caracteres):
        if indice in borrar:
            continue
        if restantes and restantes[-1][1] == estilo:
            restantes[-1] = (restantes[-1][0] + caracter, estilo)
        else:
            restantes.append((caracter, estilo))
    return restantes


def _quitar_enlaces_duplicados(runs: list) -> list:
    """Elimina los enlaces internos repetidos y seguidos de un mismo bloque.

    Cuando un bloque del PDF repite dos veces seguidas la misma frase de
    navegación ("Vuelve al índice", "Vuelve al inicio"...), solo se conserva
    la primera. Si no hay repeticiones devuelve los runs sin tocar.
    """
    texto = "".join(t for t, _ in runs)
    coincidencias = sorted(_coincidencias_enlaces(texto))
    if len(coincidencias) < 2:
        return runs

    repetidos = []
    ultimo = None
    for inicio, fin, destino in coincidencias:
        # ¿Es la misma frase que la anterior y solo la separan espacios?
        if (ultimo is not None and destino == ultimo[2]
                and not texto[ultimo[1]:inicio].strip()):
            repetidos.append((ultimo[1], fin))
            continue
        ultimo = (inicio, fin, destino)

    if not repetidos:
        return runs
    return _normalizar_runs(_quitar_tramos(runs, repetidos))


def _marcar_enlaces(runs: list, coincidencias: list) -> list:
    """Marca los tramos que deben ser enlace dentro de una lista de runs.

    ``coincidencias`` son tuplas (inicio, fin, destino) por índice de carácter.
    Devuelve segmentos (texto, estilo, destino), con destino None en los tramos
    que no forman parte de ningún enlace.
    """
    caracteres = []
    for texto, estilo in runs:
        caracteres.extend((caracter, estilo, None) for caracter in texto)

    for inicio, fin, destino in coincidencias:
        for indice in range(inicio, fin):
            caracteres[indice] = (caracteres[indice][0], caracteres[indice][1], destino)

    segmentos = []
    for caracter, estilo, destino in caracteres:
        if segmentos and segmentos[-1][1] == estilo and segmentos[-1][2] == destino:
            segmentos[-1] = (segmentos[-1][0] + caracter, estilo, destino)
        else:
            segmentos.append((caracter, estilo, destino))
    return segmentos


def _enlazar_nodos(nodos: list) -> None:
    """Añade los anclajes (id) y los enlaces internos de los nodos.

    Reglas aplicadas:
    - El encabezado "Indice:" recibe id="indice".
    - El primer bloque del documento recibe id="inicio".
    - Los encabezados "APARTADO N" reciben id="apartadoN".
    - El bloque final del autor recibe id="final" y su correo se enlaza mailto.
    - La lista del índice (<ol> de apartados) enlaza cada item a su apartado.
    - Los textos "Vuelve al inicio", "Vuelve al índice" y "Ve hasta el final"
      se convierten en enlaces internos.
    """
    # Encabezado del índice
    nodo_indice = None
    for nodo in nodos:
        if nodo["tipo"] == "parrafo" and PATRON_INDICE.match(_texto_del_nodo(nodo)):
            nodo_indice = nodo
            break
    if nodo_indice is not None:
        nodo_indice["id"] = "indice"

    # Primer párrafo/título del documento (se ignoran las tablas previas)
    for nodo in nodos:
        if nodo["tipo"] == "parrafo":
            if "id" not in nodo:
                nodo["id"] = "inicio"
            break

    # Encabezados de apartado y localización del bloque del autor
    nodo_autor = None
    for nodo in nodos:
        if nodo["tipo"] != "parrafo":
            continue
        texto = _texto_del_nodo(nodo)
        coincidencia = PATRON_APARTADO.match(texto)
        if coincidencia and "id" not in nodo:
            nodo["id"] = f"apartado{coincidencia.group(1)}"
        if nodo_autor is None and PATRON_AUTOR.search(texto):
            nodo_autor = nodo

    # Si no se detecta la línea del autor, se usa el último párrafo
    if nodo_autor is None:
        for nodo in reversed(nodos):
            if nodo["tipo"] == "parrafo":
                nodo_autor = nodo
                break

    # Bloque final del autor: ancla y enlace del correo
    if nodo_autor is not None:
        nodo_autor["id"] = "final"
        coincidencia = PATRON_AUTOR.search(_texto_del_nodo(nodo_autor))
        if coincidencia:
            destino = _href_mailto(coincidencia.group(1))
            if destino:
                nodo_autor["segmentos"] = _marcar_enlaces(
                    nodo_autor["runs"],
                    [(coincidencia.start(1), coincidencia.end(1), destino)],
                )

    # Lista del índice: cada <li> enlaza a su apartado
    for nodo in nodos:
        if nodo["tipo"] != "lista" or not nodo["ordenada"]:
            continue
        destinos = []
        for runs in nodo["items"]:
            texto = "".join(t for t, _ in runs).strip()
            coincidencia = PATRON_APARTADO.match(texto)
            destinos.append(
                f"#apartado{coincidencia.group(1)}" if coincidencia else None
            )
        if any(destinos):
            nodo["enlaces_item"] = destinos

    # Enlaces internos dentro de los párrafos
    for nodo in nodos:
        if nodo["tipo"] != "parrafo" or "segmentos" in nodo:
            continue
        # Si el bloque repite seguido la misma frase de navegación, se limpia
        nodo["runs"] = _quitar_enlaces_duplicados(nodo["runs"])
        coincidencias = _coincidencias_enlaces(_texto_del_nodo(nodo))
        if coincidencias:
            nodo["segmentos"] = _marcar_enlaces(nodo["runs"], coincidencias)


def construir_html(pdf_path: str, nombres_imagenes=None, paginas_omitidas=None) -> str:
    """Genera el código HTML a partir de los bloques de texto del PDF.

    Reglas aplicadas:
    - Cada bloque del PDF se convierte en un único <p>, <h1>-<h3> o elemento
      de lista, sin cortar las frases ni crear etiquetas inconexas.
    - Los bloques que empiezan por viñeta o numeración romana se limpian y se
      agrupan en <ul>/<ol>, con un <li> por elemento.
    - Las palabras con estilo propio dentro de un bloque solo se envuelven en
      un <span>, sin romper el párrafo.
    - Los estilos que se repiten 2 o más veces se convierten en clases CSS del
      <head>; los que aparecen una sola vez se aplican inline con style="...".
    - Las imágenes solo se insertan entre bloques, nunca dentro de un texto;
      la primera (el logotipo) queda junto a la cabecera y no al final.
    - Se descartan los párrafos consecutivos repetidos ("Vuelve al índice",
      "Vuelve al inicio"...) para no duplicar los enlaces de navegación.
    - Se añaden anclajes internos (inicio, índice, apartados y final) y enlaces
      internos ("Vuelve al inicio", "Vuelve al índice", "Ve hasta el final").
    - Se conserva la alineación (text-align) y el color de fondo de los bloques
      detectados en el PDF.
    - Las tablas detectadas con ``page.find_tables()`` se emiten como
      <table class="tabla-pdf"> y el texto que cae dentro de su área se
      descarta para no duplicarlo.
    - El contenido se agrupa en secciones <div class="seccion-bloque">: cada
      título principal (H1) abre una sección que engloba lo que le sigue.
    - Las listas romanas se emiten como <ol type="I"> y su color se aplica al
      propio <ol>/<ul> para que los marcadores no salgan en negro.
    - Los títulos "APARTADO N" reciben el color de fondo (detectado o extraído
      de las instrucciones) con un relleno de 15px.
    - ``paginas_omitidas`` permite excluir páginas concretas (1 = primera); esas
      páginas no se imprimen pero se analizan para extraer las variables de
      estilo (colores) que se aplican como base al resto del documento.
    """
    nombres_imagenes = nombres_imagenes or []
    bloques, variables = extraer_bloques_pdf(pdf_path, paginas_omitidas)

    # --- Tamaño del cuerpo = tamaño con más texto en el documento -----------
    volumen = {}
    for elemento in bloques:
        if elemento.get("tipo") != "texto":
            continue                                # las tablas no aportan texto
        for texto, estilo in elemento["runs"]:
            volumen[estilo[1]] = volumen.get(estilo[1], 0) + len(texto)
    tamano_cuerpo = max(volumen, key=volumen.get) if volumen else 12.0

    # --- Agrupación en nodos HTML (párrafos, títulos y listas) --------------
    nodos = _agrupar_nodos(bloques, tamano_cuerpo)

    # --- Se descartan los párrafos repetidos seguidos ("Vuelve al índice"...)
    nodos = _quitar_duplicados_consecutivos(nodos)

    # --- Anclajes y enlaces internos/externos --------------------------------
    _enlazar_nodos(nodos)

    # --- Recuento de estilos, ya sin los marcadores de lista ----------------
    conteo = {}
    for nodo in nodos:
        for runs in _runs_del_nodo(nodo):
            for _, estilo in runs:
                conteo[estilo] = conteo.get(estilo, 0) + 1

    # --- Asignación de clases CSS a los estilos repetidos -------------------
    clases = {}
    for nodo in nodos:
        for runs in _runs_del_nodo(nodo):
            for _, estilo in runs:
                if conteo[estilo] >= MIN_USOS_PARA_CLASE and estilo not in clases:
                    clases[estilo] = f"estilo-{len(clases) + 1}"

    # --- Reparto de las imágenes entre bloques ------------------------------
    posiciones = _indice_imagenes(len(nodos), len(nombres_imagenes))

    # --- Cabecera del documento ---------------------------------------------
    titulo = html.escape(os.path.splitext(os.path.basename(pdf_path))[0])
    salida = [
        "<!DOCTYPE html>",
        '<html lang="es">',
        "<head>",
        '    <meta charset="utf-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"    <title>{titulo}</title>",
        "    <style>",
    ]
    salida += [f"        {regla}" for regla in CSS_BASE]

    # Ancho dinámico del folio: el real de la primera página válida del PDF
    if variables.get("ancho"):
        salida.append("")
        salida.append("        /* Ancho real del folio tomado del PDF */")
        salida.append(f"        .contenido {{ width: {variables['ancho']:g}px; }}")

    # Color de texto base extraído de las instrucciones (página de análisis)
    if variables.get("texto"):
        salida.append("")
        salida.append("        /* Color base extraído de las instrucciones */")
        salida.append(f"        .contenido {{ color: {variables['texto']}; }}")

    if clases:
        salida.append("")
        salida.append("        /* Clases generadas a partir de estilos repetidos */")
        for estilo, nombre in clases.items():
            salida.append(f"        .{nombre} {{ {_estilo_a_css(estilo)} }}")

    salida += [
        "    </style>",
        "</head>",
        "<body>",
        '    <main class="contenido">',
    ]

    # --- Cuerpo del documento -----------------------------------------------
    # El contenido se agrupa en secciones <div class="seccion-bloque">: cada
    # título principal (H1) abre una sección nueva que engloba todo el texto,
    # las listas y las tablas que vienen a continuación.
    indent = "            "
    emitidos = 0
    seccion_abierta = False

    def cerrar_seccion() -> None:
        """Cierra la sección <div class="seccion-bloque"> si está abierta."""
        nonlocal seccion_abierta
        if seccion_abierta:
            salida.append("        </div>")
            seccion_abierta = False

    for nodo in nodos:
        es_titulo_principal = (nodo["tipo"] == "parrafo"
                               and nodo["etiqueta"] == "h1")
        if es_titulo_principal or not seccion_abierta:
            cerrar_seccion()
            salida.append('        <div class="seccion-bloque">')
            seccion_abierta = True

        if nodo["tipo"] == "tabla":
            salida += _tabla_html(nodo["filas"], nodo["cabecera"], indent=indent)
        elif nodo["tipo"] == "lista":
            etiqueta = "ol" if nodo["ordenada"] else "ul"
            # Las listas ordenadas son romanas: <ol type="I">
            atributo_tipo = ' type="I"' if etiqueta == "ol" else ""
            # El color va en el padre para que los marcadores lo hereden y, si
            # el bloque anterior estaba centrado, la lista se centra empaquetada
            atributos = _atributos_lista(
                nodo["items"], conteo, clases, nodo.get("centrada", False)
            )
            enlaces = nodo.get("enlaces_item")
            salida.append(f"{indent}<{etiqueta}{atributo_tipo}{atributos}>")
            for posicion, runs in enumerate(nodo["items"]):
                salida.append(_elemento_html(
                    "li", runs, conteo, clases, indent=indent + "    ",
                    href=enlaces[posicion] if enlaces else None,
                ))
            salida.append(f"{indent}</{etiqueta}>")
        else:
            salida.append(_elemento_html(
                nodo["etiqueta"], nodo["runs"], conteo, clases, indent=indent,
                id_elemento=nodo.get("id"), segmentos=nodo.get("segmentos"),
                alineacion=nodo.get("alineacion"), fondo=nodo.get("fondo"),
                padding=nodo.get("padding"),
            ))

        emitidos += 1

        # Las imágenes se insertan siempre entre bloques completos
        for indice in posiciones.get(emitidos, []):
            salida += _figura_html(nombres_imagenes[indice], indent=indent)

    cerrar_seccion()

    # Si el PDF no tenía texto, las imágenes se añaden igualmente
    if not nodos:
        for nombre in nombres_imagenes:
            salida += _figura_html(nombre)

    salida += [
        "    </main>",
        "</body>",
        "</html>",
    ]
    return "\n".join(salida) + "\n"


# ===========================================================================
# INTERFAZ GRÁFICA (GUI)
# ===========================================================================


class PdfToHtmlApp(ctk.CTk):
    """Ventana principal de la aplicación."""

    def __init__(self) -> None:
        """Inicializa el estado interno, la ventana y todos los paneles."""
        super().__init__()

        # Estado interno de la aplicación
        self.pdf_path = ""
        self.image_paths = []

        # -------------------------------------------------------------------
        # Configuración de la ventana
        # -------------------------------------------------------------------
        self.title("Generador de proyectos PDF → HTML")
        self.geometry("640x660")
        self.minsize(560, 620)

        # Permite que la columna central se expanda
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Contenedor principal con margen
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_pdf_section()
        self._build_images_section()
        self._build_project_section()
        self._build_generate_button()
        self._build_status_label()

    # -----------------------------------------------------------------------
    # Construcción de la interfaz
    # -----------------------------------------------------------------------
    def _build_header(self) -> None:
        """Cabecera con título y subtítulo."""
        title = ctk.CTkLabel(
            self.main_frame,
            text="Generador de proyectos PDF → HTML",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(
            self.main_frame,
            text="Selecciona un PDF, tus imágenes y ponle nombre al proyecto.",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT_MUTED,
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(2, 18))

    def _build_pdf_section(self) -> None:
        """Panel de selección del archivo PDF."""
        panel = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLOR_PANEL,
            corner_radius=12,
            border_width=1,
            border_color=COLOR_PANEL_BORDER,
        )
        panel.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        panel.grid_columnconfigure(1, weight=1)

        label = ctk.CTkLabel(
            panel,
            text="1. Archivo PDF",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        label.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4))

        button = ctk.CTkButton(
            panel,
            text="Cargar PDF",
            width=140,
            command=self.select_pdf,
        )
        button.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="w")

        self.pdf_label = ctk.CTkLabel(
            panel,
            text="Ningún archivo seleccionado",
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self.pdf_label.grid(row=1, column=1, padx=(0, 16), pady=(0, 16), sticky="ew")

        # Páginas que no deben incluirse en el HTML generado
        self.omit_label = ctk.CTkLabel(
            panel,
            text="Páginas a omitir (ej: 1 o 1,2)",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self.omit_label.grid(row=2, column=0, columnspan=2, sticky="w",
                             padx=16, pady=(0, 4))

        self.omit_entry = ctk.CTkEntry(
            panel,
            placeholder_text="Páginas a omitir (ej: 1 o 1,2)",
            height=38,
        )
        self.omit_entry.grid(row=3, column=0, columnspan=2, sticky="ew",
                             padx=16, pady=(0, 16))

    def _build_images_section(self) -> None:
        """Panel de selección múltiple de imágenes."""
        panel = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLOR_PANEL,
            corner_radius=12,
            border_width=1,
            border_color=COLOR_PANEL_BORDER,
        )
        panel.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        panel.grid_columnconfigure(1, weight=1)

        label = ctk.CTkLabel(
            panel,
            text="2. Imágenes",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        label.grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4))

        button = ctk.CTkButton(
            panel,
            text="Seleccionar imágenes",
            width=180,
            command=self.select_images,
        )
        button.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="w")

        self.images_label = ctk.CTkLabel(
            panel,
            text="0 imágenes seleccionadas",
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self.images_label.grid(row=1, column=1, padx=(0, 16), pady=(0, 16), sticky="ew")

    def _build_project_section(self) -> None:
        """Panel con el campo de texto para el nombre del proyecto."""
        panel = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLOR_PANEL,
            corner_radius=12,
            border_width=1,
            border_color=COLOR_PANEL_BORDER,
        )
        panel.grid(row=4, column=0, sticky="ew", pady=(0, 18))
        panel.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(
            panel,
            text="3. Nombre del proyecto",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        label.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        self.project_entry = ctk.CTkEntry(
            panel,
            placeholder_text="Ej: prueba",
            height=38,
        )
        self.project_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _build_generate_button(self) -> None:
        """Botón principal de acción."""
        self.generate_button = ctk.CTkButton(
            self.main_frame,
            text="Generar",
            height=46,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            corner_radius=10,
            command=self.generate,
        )
        self.generate_button.grid(row=5, column=0, sticky="ew")

    def _build_status_label(self) -> None:
        """Etiqueta inferior donde se muestran los mensajes de estado."""
        self.status_label = ctk.CTkLabel(
            self.main_frame,
            text="",
            font=ctk.CTkFont(size=13),
            wraplength=560,
            justify="left",
        )
        self.status_label.grid(row=6, column=0, sticky="ew", pady=(14, 0))

    # -----------------------------------------------------------------------
    # Acciones de los botones
    # -----------------------------------------------------------------------
    def select_pdf(self) -> None:
        """Abre el diálogo para elegir un PDF y muestra su nombre."""
        path = filedialog.askopenfilename(
            title="Selecciona un archivo PDF",
            filetypes=PDF_FILETYPES,
        )
        if not path:
            # El usuario canceló el diálogo
            return

        self.pdf_path = path
        self.pdf_label.configure(
            text=os.path.basename(path),
            text_color="#ffffff",
        )
        self._set_status("PDF cargado correctamente.", COLOR_SUCCESS)

    def select_images(self) -> None:
        """Abre el diálogo para elegir varias imágenes y las cuenta."""
        paths = filedialog.askopenfilenames(
            title="Selecciona las imágenes",
            filetypes=IMAGE_FILETYPES,
        )
        if not paths:
            return

        self.image_paths = list(paths)
        total = len(self.image_paths)
        self.images_label.configure(
            text=f"{total} imágenes seleccionadas",
            text_color="#ffffff",
        )
        self._set_status(f"{total} imágenes seleccionadas.", COLOR_SUCCESS)

    # -----------------------------------------------------------------------
    # Lógica principal
    # -----------------------------------------------------------------------
    def generate(self) -> None:
        """Crea la carpeta del proyecto con index.html e imagenes/."""
        project_name = self.project_entry.get().strip()
        paginas_omitidas = _paginas_a_omitir(self.omit_entry.get())

        # --- Validaciones ---------------------------------------------------
        if not self.pdf_path:
            self._set_status("Error: debes cargar un archivo PDF.", COLOR_ERROR)
            return

        if not project_name:
            self._set_status(
                "Error: debes escribir un nombre de proyecto.", COLOR_ERROR
            )
            return

        # Evita nombres inválidos o rutas fuera del directorio de destino
        if os.path.basename(project_name) != project_name or project_name in (".", ".."):
            self._set_status(
                "Error: el nombre del proyecto no es válido.", COLOR_ERROR
            )
            return

        # --- Carpeta de destino elegida por el usuario ----------------------
        destino = filedialog.askdirectory(
            title="Selecciona dónde guardar el proyecto"
        )
        if not destino:
            self._set_status(
                "Operación cancelada: no se ha seleccionado carpeta de destino.",
                COLOR_TEXT_MUTED,
            )
            return

        try:
            # --- Creación de la estructura ----------------------------------
            project_dir = os.path.join(destino, project_name)
            images_dir = os.path.join(project_dir, "imagenes")
            os.makedirs(images_dir, exist_ok=True)

            # --- Copia de imágenes ------------------------------------------
            nombres_imagenes = []
            for image_path in self.image_paths:
                if not os.path.isfile(image_path):
                    continue
                nombre = os.path.basename(image_path)
                shutil.copy2(image_path, os.path.join(images_dir, nombre))
                nombres_imagenes.append(nombre)

            # --- Lectura del PDF y generación del HTML ----------------------
            contenido_html = construir_html(
                self.pdf_path, nombres_imagenes, paginas_omitidas
            )

            index_path = os.path.join(project_dir, "index.html")
            with open(index_path, "w", encoding="utf-8", newline="\n") as archivo:
                archivo.write(contenido_html)

            # --- Mensaje de éxito -------------------------------------------
            self._set_status(
                f"Proyecto '{project_name}' generado correctamente "
                f"({len(nombres_imagenes)} imágenes copiadas).\n"
                f"Ruta: {index_path}",
                COLOR_SUCCESS,
            )

        except RuntimeError as error:
            # PyMuPDF lanza RuntimeError/FileDataError si el PDF no es válido
            self._set_status(f"Error al leer el PDF: {error}", COLOR_ERROR)
        except OSError as error:
            self._set_status(f"Error al generar el proyecto: {error}", COLOR_ERROR)

    # -----------------------------------------------------------------------
    # Utilidades
    # -----------------------------------------------------------------------
    def _set_status(self, message: str, color: str = COLOR_TEXT_MUTED) -> None:
        """Actualiza el texto y el color del mensaje de estado."""
        self.status_label.configure(text=message, text_color=color)


def main() -> None:
    """Punto de entrada de la aplicación."""
    app = PdfToHtmlApp()
    app.mainloop()


if __name__ == "__main__":
    main()
