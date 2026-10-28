# PDF → HTML

Herramienta de escritorio (GUI) que convierte un archivo PDF en un sitio HTML listo
para publicar, conservando la estructura del documento original: títulos, párrafos,
listas, **tablas** y estilos.

## Descripción

La aplicación analiza el PDF página a página con PyMuPDF y genera un `index.html`
semántico junto a una carpeta `imagenes/` con los recursos copiados. Entre sus
características principales:

- **Detección de tablas**: usa `page.find_tables()` para reconstruir las tablas como
  HTML semántico (`<table>`, `<tr>`, `<th>` y `<td>`), evitando que su texto aparezca
  duplicado.
- **Clases CSS inteligentes**: los estilos que se repiten en el documento se agrupan
  en clases (`.estilo-1`, `.estilo-2`, …) dentro de un `<style>`; los estilos únicos se
  aplican inline. Así el HTML queda limpio y ligero.
- **Secciones lógicas**: el contenido se agrupa en bloques `<div class="seccion-bloque">`
  encabezados por cada título principal.
- **Páginas de instrucciones**: las páginas marcadas como "a omitir" no se imprimen,
  pero sí se analizan para extraer los colores base (`Color de fondo de los bloques`,
  `El color del texto`) que se aplican al resto del documento.
- **Navegación interna**: se añaden anclajes (`inicio`, `indice`, `apartadoN`, `final`)
  y se enlazan automáticamente los textos de navegación y el correo del autor.

## Requisitos previos

- **Python 3.9 o superior** instalado en el sistema.
  Puedes comprobarlo con:

  ```bash
  python --version
  ```

## Instalación

Sigue estos pasos desde la terminal, en el directorio donde quieras alojar el proyecto.

### 1. Clonar el repositorio

```bash
git clone https://github.com/usuario/pdf-a-html-app.git
cd pdf-a-html-app
```

> Sustituye la URL por la de tu repositorio.

### 2. Crear un entorno virtual

```bash
python -m venv venv
```

### 3. Activar el entorno virtual

**Windows (PowerShell):**

```powershell
venv\Scripts\Activate.ps1
```

**Windows (CMD):**

```bat
venv\Scripts\activate.bat
```

**Linux / macOS:**

```bash
source venv/bin/activate
```

### 4. Instalar las dependencias

```bash
pip install -r requirements.txt
```

## Uso

Ejecuta la aplicación:

```bash
python main.py
```

Se abrirá una ventana con los siguientes campos:

| Campo | Para qué sirve |
| --- | --- |
| **1. Archivo PDF** | Selecciona el PDF de origen que se va a convertir. Pulsa **Cargar PDF**. |
| **Páginas a omitir (ej: 1 o 1,2)** | Números de las páginas que **no** se imprimirán (1 = primera). Se pueden indicar varias separadas por comas, punto y coma o espacios (`1`, `1,2`, `1; 3`). Déjalo vacío para procesar todo. Esas páginas se siguen analizando para extraer los colores base. |
| **2. Imágenes** | Selecciona una o varias imágenes (logotipos, ilustraciones…). Se copian a la carpeta `imagenes/` y se insertan en el HTML intercaladas entre los bloques de texto. |
| **3. Nombre del proyecto** | Nombre de la carpeta que se creará con el resultado. |
| **Generar** | Pregunta dónde guardar el proyecto y crea allí la carpeta con el `index.html` y la subcarpeta `imagenes/`. |

### Resultado

Al finalizar se genera la siguiente estructura dentro de la carpeta que hayas elegido:

```
<destino>/<nombre-del-proyecto>/
├── index.html
└── imagenes/
    ├── ...
```

Abre `index.html` en cualquier navegador para ver el resultado.
