# Generador de tabuladores por ruta

App web local que lee **un tabulador** (matriz de precios) desde un CSV y genera
**una imagen PNG por cada ruta de salida**, con el título
`SALIDAS DESDE <RUTA>` y los destinos agrupados en **una columna por cada tarifa**
(`ZONA 1`, `ZONA 2`, …).

## Cómo está armado el dato

El CSV **no es una ruta**: es el tabulador completo.

```
De\A                     | 01 - Casco central | 02 - Bella Vista | ...
01 - Casco central       | 1.5                | 2                | ...
02 - Ruta Media (Bella)  | 2                  | 1.5              | ...
```

- **Columna A** → origen (cada fila es una ruta de salida).
- **Fila 1 desde la columna B** → destinos.
- **Cruce** → costo del viaje origen → destino.

Por eso ya están *todas* las rutas cargadas en un solo archivo: la app lista las
25 salidas y genera la imagen que elijas.

## Arrancar

```bash
cd tabuladores
python3 app.py           # http://127.0.0.1:8765
python3 app.py --port 9000
```

### Sincronizar entre dispositivos

**Opción A — Carpeta sincronizada (Dropbox/OneDrive/Drive para escritorio):**

```bash
python3 app.py --data-dir "/ruta/a/tu/carpeta/sincronizada"
```

La app lee y escribe el CSV en esa carpeta; el servicio de nube sincroniza.
También puedes cambiar la carpeta desde la interfaz (botón **Cambiar carpeta
de datos**); la ruta se recuerda en `settings.json`.

**Opción B — Google Drive directo (sin cliente de escritorio):**

1. Crea un proyecto en https://console.cloud.google.com
2. Activa la API "Google Drive".
3. Crea credenciales OAuth 2.0 de tipo **Aplicación de escritorio**.
4. Copia el `client_id` y `client_secret`.
5. En la app, sección **Google Drive**, pégalos y pulsa **Guardar credenciales**.
6. Pulsa **Conectar Google Drive**: se abre el navegador, autorizas y vuelves.
7. Pulsa **Sincronizar ahora** para subir/descargar el tabulador.

El tabulador se guarda en Drive como `tabulador.csv` y se descarga
automáticamente al iniciar si hay conexión.

Solo requiere Python 3 + Pillow. Los PNG quedan en `salidas/`.

## Usar

1. Busca o filtra las rutas en el cuadro de búsqueda; ordena por nombre, tabulador
   o cantidad de destinos. Marca una o varias (o **Todas** / **Ninguna**; cada
   grupo tiene su casilla para seleccionar todas las salidas de ese tabulador).
2. Elige el **estilo**: `Referencia` (azul marino/carmesí, por defecto) o `Claro`
   (crema/naranja).
3. **Vista previa** abre la imagen de la primera ruta seleccionada sin guardarla.
4. **Generar imágenes** crea los PNG (se guardan en `salidas/`).
5. **Descargar todo (ZIP)** baja las rutas seleccionadas con el estilo elegido.

Atajos: `Ctrl+Enter` genera, `Ctrl+A` selecciona todas, `Esc` cierra la vista previa.

### Datos y configuración

- Solo existe **un tabulador**. Si importas un CSV nuevo, **reemplaza** al actual
  (se sobrescribe el archivo de datos); no se acumulan varios.
- **Importar CSV** carga un tabulador desde un archivo CSV con el mismo formato
  (no hace falta reiniciar).
- **Editor de tabulador** (pestaña) muestra la matriz origen × destino con
  celdas editables: cambia los precios y pulsa **Guardar tabulador** para
  escribir el CSV en `data/`. Incluye **Agregar zona** para ampliar la matriz
  y **Exportar CSV** para descargar el tabulador editado.
- **Exportar config** guarda la selección y el estilo en un JSON.
- **Importar config** restaura esa selección y estilo desde el JSON.

## Qué muestra cada imagen

- **Cabecera** azul marino con textura: isotipo circular, `EXPRESS` y el eslogan
  `TU PEDIDO, NUESTRA RUTA` con el icono de reparto.
- **Cinta carmesí** con esquinas en ángulo y el título
  `SALIDAS DESDE <ORIGEN>` en mayúsculas y blanco.
- **Una columna por tarifa**: si una salida tiene 7 precios distintos, salen 7
  columnas numeradas `ZONA 1` … `ZONA 7`, ordenadas de menor a mayor precio.
  Cada encabezado lleva flecha desplegable y cada columna muestra su precio en la
  **franja inferior** azul marino (p. ej. `$1.50`, `$3.50`, `$5.50`).
- Filas zebra (blanco / celeste muy claro); los nombres largos se reparten en dos
  líneas. Los destinos usan **Inter SemiBold** (incluida en `assets/fonts/`), una
  tipografía con mayor altura de x que se reconoce mejor en tamaño pequeño.
- Ancho base 2000 px; si hay muchas tarifas la imagen se ensancha para que las
  columnas sigan siendo legibles. Alto automático según la tarifa con más destinos.

Los destinos se agrupan por el precio de esa salida, sin límite de tarifas.

## Versión HTML (sin servidor)

`dist/Tabuladores-WualaExpress.html` (en la carpeta `dist/` del proyecto, un
nivel arriba de `tabuladores/`) es la misma app en **un solo archivo**: se
abre con doble clic en cualquier navegador, ya trae el tabulador y el logo
incrustados y genera las imágenes con `<canvas>` (sin Python ni internet).

- Misma interfaz, mismos estilos y mismo diseño que la versión Python.
- Descarga cada PNG o todas las seleccionadas en un ZIP.
- El botón **Otro CSV** permite cargar uno o varios tabuladores mientras la
  página esté abierta; **Restaurar tabulador incluido** vuelve al original.

Para regenerarlo después de cambiar el CSV o el logo:

```bash
python3 build_html.py
# opciones: --csv data/otro.csv --out /ruta/salida.html
```

El código fuente de la página está en `html/app.html` (con los marcadores
`__CSV_JSON__` y `__LOGO_DATA_URI__` que rellena el script).

## Agregar o reemplazar un tabulador

Suelta otro CSV en `data/` y recarga la página (no hace falta reiniciar):

```csv
# nombre: Tabulador por zona (general)
# id: tabulador-general
De\A,01 - Casco central,02 - Ruta Media (Bella Vista)
01 - Casco central,1.5,2
02 - Ruta Media (Bella Vista),2,1.5
```

- `# nombre:` / `# id:` son opcionales; si faltan se usa el nombre del archivo.
- Varios CSV conviven: la interfaz los agrupa por tabulador.
- Una celda vacía se dibuja como `—`.

## Estructura

```
tabuladores/
├── app.py        # servidor HTTP (stdlib) + API
├── render.py     # dibujo del PNG (Pillow)
├── store.py      # lectura del tabulador y rutas
├── build_html.py # empaqueta la versión HTML de un solo archivo
├── html/app.html # plantilla de la versión HTML
├── data/         # CSV del tabulador
├── assets/       # logo y tipografía de los destinos
├── salidas/      # PNG generados
└── static/       # interfaz
```
