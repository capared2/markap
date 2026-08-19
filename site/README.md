# markap · sitio

Frontend del archivo, hecho con **Astro 7 + TypeScript + Tailwind 4** y
renderizado en el servidor con el adaptador de **Cloudflare**.

## Por qué SSR y no páginas estáticas

El archivo crece sin límite. Prerenderizar una página por noticia chocaría con
el tope de 20.000 ficheros por despliegue de Cloudflare Pages, así que las
páginas se generan en el edge y se cachean allí (`Cache-Control` con
`s-maxage` y `stale-while-revalidate`). Los únicos ficheros que se despliegan
son el worker, los assets y los JSON del dataset: unos cientos, no cientos de
miles.

Cada página lee solo lo que necesita:

| Página | Lee |
| --- | --- |
| Portada | `data/latest.json` (200 noticias, sin cuerpo) |
| Categoría | `data/index.json` + los `part-NNNN.json` que cubren esa página |
| Noticia | `data/<categoria>/lookup.json` + el único `part` que la contiene |

## Desarrollo

```bash
cd site
npm install
npm run dev      # copia ../data a public/ y arranca en localhost:4321
npm run build
```

## Despliegue en Cloudflare Pages

Conectando el repositorio desde el panel de Cloudflare, con esta configuración:

| Ajuste | Valor |
| --- | --- |
| Framework preset | Astro |
| Root directory | `site` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Variable de entorno | `NODE_VERSION` = `22` |

El `prebuild` copia `../data` a `public/data`, así que cada despliegue publica
el dataset que haya en el repositorio en ese momento. Cada vez que el workflow
de scraping commitea noticias nuevas, Cloudflare reconstruye el sitio solo.

## Estructura

```
src/
├── layouts/Base.astro          cabecera, pie, tema claro/oscuro, cache
├── components/                 tarjetas, rejilla, bandas de sección, última hora
├── lib/data.ts                 lectura del dataset (paginación e id → fichero)
├── lib/format.ts               fechas en español, nombres y colores de sección
└── pages/
    ├── index.astro             portada: apertura + última hora + bandas
    ├── categoria/[...clave]    listado paginado por categoría
    ├── noticia/[...ruta]       noticia completa y relacionadas
    ├── categorias.astro        directorio del archivo
    └── buscar.astro            búsqueda sobre las noticias recientes
```
