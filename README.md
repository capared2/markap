# markap — archivo de noticias de marca.com

Scraper de las noticias de [marca.com](https://www.marca.com/) que guarda cada
noticia en JSON, **partiendo el dataset por categoría** para que ningún archivo
se vuelva inmanejable, se ejecuta solo mediante **GitHub Actions**, y se navega
en un sitio hecho con Astro y desplegado en Cloudflare.

| Pieza | Dónde |
| --- | --- |
| Scraper | `scraper/` — ver este documento |
| Dataset | `data/` — un JSON por categoría, partido en trozos |
| Sitio | `site/` — ver [`site/README.md`](site/README.md) |
| Automatización | `.github/workflows/` |

## Cómo queda organizado el dataset

```
data/
├── index.json                       # catálogo: categorías, archivos y totales
├── latest.json                      # las 200 más recientes, sin cuerpo (portada)
├── futbol/
│   ├── real-madrid/
│   │   ├── part-0001.json           # 400 noticias por archivo (configurable)
│   │   ├── part-0002.json
│   │   └── lookup.json              # id de noticia → archivo que la contiene
│   ├── barcelona/part-0001.json
│   └── primera-division/part-0001.json
├── baloncesto/nba/part-0001.json
├── motor/formula1/part-0001.json
└── tenis/part-0001.json
```

La categoría sale de la propia URL de la noticia: de
`marca.com/futbol/real-madrid/2026/08/19/68a1….html` se toman los segmentos
previos a la fecha, o sea `futbol/real-madrid`. Con `--category-depth 1` todo
`futbol/*` se agruparía en una sola categoría `futbol`.

Cuando un archivo llega a `--shard-size` noticias (400 por defecto) se abre el
siguiente `part-NNNN.json`, así que los archivos se mantienen en pocos MB.

### Formato de cada archivo

```jsonc
{
  "category": "futbol/real-madrid",
  "part": 1,
  "count": 400,
  "updated_at": "2026-08-19T22:10:04Z",
  "articles": [
    {
      "id": "68a1b2c3ca4741f1234b45a8",
      "url": "https://www.marca.com/futbol/real-madrid/2026/08/19/68a1….html",
      "category": "futbol/real-madrid",
      "category_path": ["futbol", "real-madrid"],
      "section": "Real Madrid",
      "breadcrumbs": ["Marca", "Fútbol", "Real Madrid"],
      "title": "…",
      "standfirst": "…",        // entradilla
      "summary": "…",
      "body": "texto completo con saltos de párrafo",
      "paragraphs": ["…", "…"],
      "word_count": 512,
      "authors": ["…"],
      "tags": ["…"],
      "content_type": "opinion",
      "published_at": "2026-08-19T20:47:00Z",   // siempre UTC ISO-8601
      "modified_at": "2026-08-19T23:10:00Z",
      "language": "es",
      "images": [{"url": "…", "caption": "…"}],
      "videos": ["…"],
      "is_premium": false,
      "source": "marca.com",
      "scraped_at": "2026-08-19T23:12:41Z"
    }
  ]
}
```

Los datos se extraen del JSON-LD (`NewsArticle`) que publica Marca, con
Open Graph, `<meta>` y el HTML del cuerpo como respaldo si falta algo.

El cuerpo se toma de `div.ue-c-article__body`, que es solo la noticia: quedan
fuera los titulares de otras noticias que Marca intercala, la barra de firma,
los botones de compartir, las etiquetas y las relacionadas. Las etiquetas se
leen de la lista que Marca publica al pie, no de las palabras del slug.

Si Marca cambia su maquetación, el workflow **Inspeccionar página** vuelca la
estructura de cualquier noticia en `tools/ultima-inspeccion.txt` para poder
reajustar los selectores.

## De dónde salen las noticias

Tres fuentes que se complementan y se pueden combinar con `--sources`:

| Fuente | Qué aporta |
| --- | --- |
| `sitemap` | Los sitemaps de `robots.txt` (índices incluidos). Es la vía para el archivo histórico completo. |
| `rss` | Los feeds RSS de cada sección, más los que anuncie la portada. Lo más rápido para lo recién publicado. |
| `crawl` | Recorrido por las portadas de sección, para lo que no aparezca en las otras dos. |

El descubrimiento tiene su propio límite: consume como mucho el 40 % de
`--time-budget`, así que una ejecución siempre reserva tiempo para descargar y
guardar noticias en vez de quedarse explorando. El crawl además tiene un techo
de 300 páginas de sección por ejecución.

## Ejecución en GitHub Actions

El workflow [`Scrape Marca`](.github/workflows/scrape.yml) corre **cada 2 horas**
y publica los JSON en el propio repositorio con un commit automático.

Para lanzarlo a mano: pestaña **Actions → Scrape Marca → Run workflow**. Ahí se
puede elegir modo, fuentes, tope de artículos, presupuesto de tiempo y fecha
mínima.

### Bajar todo el archivo histórico

Un archivo completo no entra en una sola ejecución, así que el scraper es
**reanudable**: lo que no llega a procesar queda encolado en `state/pending.txt`
y la ejecución siguiente sigue por donde quedó.

1. Lanzá el workflow a mano con `mode = full`. Esa corrida recorre todos los
   sitemaps y llena la cola.
2. Volvé a lanzarlo con `skip_discovery = true` tantas veces como haga falta
   (cada corrida consume ~55 minutos de cola), o simplemente dejá que lo vacíen
   las corridas programadas.

El progreso se ve en `state/run.json` (`pending` = cuánto falta).

## Ejecución local

```bash
pip install -r requirements.txt

# lo publicado en las últimas horas
python -m scraper

# prueba corta
python -m scraper --max-articles 20 --verbose

# histórico completo, empezando por lo más reciente
python -m scraper --mode full --time-budget 0

# solo desde 2024, agrupando por sección principal
python -m scraper --mode full --since 2024-01-01 --category-depth 1
```

Opciones útiles: `--workers`, `--delay`, `--shard-size`, `--category-depth`,
`--time-budget`, `--since`, `--sources`, `--skip-discovery`, `--summary-file`.
La lista completa está en `python -m scraper --help`.

## Estado entre ejecuciones

```
state/
├── seen.txt      # URLs ya guardadas: nunca se vuelven a descargar
├── pending.txt   # cola de URLs descubiertas y todavía sin procesar
├── failed.json   # URLs con fallos y su contador (se abandonan al 3er intento)
└── run.json      # resumen de la última ejecución
```

Como está versionado en el repo, cada corrida arranca sabiendo exactamente qué
falta. Para rehacer el dataset desde cero, borrá `state/` y `data/`.

## El sitio

`site/` es un frontend en **Astro 7 + TypeScript + Tailwind 4** que se despliega
en **Cloudflare Pages** conectando este repositorio desde su panel:

| Ajuste | Valor |
| --- | --- |
| Root directory | `site` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| `NODE_VERSION` | `22` |

Cada vez que el scraper commitea noticias nuevas, Cloudflare reconstruye el
sitio. Los detalles están en [`site/README.md`](site/README.md).

## Tests

```bash
python -m pytest tests -q
```

Los tests son offline: usan un marca.com simulado (`tests/fake_site.py`) y un
artículo de ejemplo, así que cubren el pipeline entero —descubrimiento, parseo,
particionado por categoría, índice y reanudación— sin pegarle al sitio real.

## Buen comportamiento

El scraper respeta `robots.txt` (incluido `Crawl-delay`), se identifica con un
User-Agent propio, espacia las peticiones (`--delay`) y reintenta con backoff
exponencial. Bajá `--workers` y subí `--delay` si querés ser aún más suave.

Los contenidos de marca.com son de Unidad Editorial y están sujetos a sus
condiciones de uso: este repositorio es para uso personal y de investigación,
no para republicar sus noticias.
