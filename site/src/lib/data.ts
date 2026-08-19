import type { ArchivoParte, EntradaCategoria, Indice, Lookup, Noticia, Portada, Tarjeta } from "./types";

/**
 * Lee un JSON del dataset publicado junto al sitio.
 *
 * En Cloudflare Pages los ficheros de `public/` los sirve el CDN antes de
 * llegar al worker, asi que una peticion al propio origen no se realimenta.
 */
async function leerJson<T>(ruta: string, origen: URL): Promise<T | null> {
  try {
    const respuesta = await fetch(new URL(ruta, origen));
    if (!respuesta.ok) return null;
    return (await respuesta.json()) as T;
  } catch {
    return null;
  }
}

export const obtenerIndice = (origen: URL) => leerJson<Indice>("/data/index.json", origen);
export const obtenerPortada = (origen: URL) => leerJson<Portada>("/data/latest.json", origen);

const obtenerParte = (categoria: string, parte: number, origen: URL) =>
  leerJson<ArchivoParte>(`/data/${categoria}/part-${String(parte).padStart(4, "0")}.json`, origen);

/** Ordena de mas reciente a mas antigua. */
function porFecha<T extends { published_at: string | null }>(articulos: T[]): T[] {
  return [...articulos].sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
}

export interface PaginaCategoria {
  articulos: Noticia[];
  total: number;
  pagina: number;
  paginas: number;
}

/**
 * Devuelve una pagina de noticias de una categoria.
 *
 * Los archivos se recorren del mas reciente al mas antiguo y solo se descargan
 * los que cubren la pagina pedida, de modo que el coste no depende del tamaño
 * total del archivo historico.
 */
export async function obtenerPaginaCategoria(
  categoria: EntradaCategoria,
  pagina: number,
  porPagina: number,
  origen: URL,
): Promise<PaginaCategoria> {
  const archivos = [...categoria.files].reverse();
  const paginas = Math.max(1, Math.ceil(categoria.articles / porPagina));
  const actual = Math.min(Math.max(1, pagina), paginas);

  const desde = (actual - 1) * porPagina;
  const hasta = desde + porPagina;

  const articulos: Noticia[] = [];
  let recorridos = 0;
  let inicioDelPrimero: number | null = null;

  for (const archivo of archivos) {
    const fin = recorridos + archivo.count;
    const intersecta = fin > desde && recorridos < hasta;

    if (intersecta) {
      if (inicioDelPrimero === null) inicioDelPrimero = recorridos;
      const numero = Number(archivo.file.match(/part-(\d+)\.json$/)?.[1] ?? 1);
      const parte = await obtenerParte(categoria.category, numero, origen);
      if (parte) articulos.push(...porFecha(parte.articles));
    }

    recorridos = fin;
    if (recorridos >= hasta) break;
  }

  const corte = desde - (inicioDelPrimero ?? 0);
  return {
    articulos: articulos.slice(corte, corte + porPagina),
    total: categoria.articles,
    pagina: actual,
    paginas,
  };
}

/** Busca una noticia concreta resolviendo antes en que archivo vive. */
export async function obtenerNoticia(
  categoria: string,
  id: string,
  origen: URL,
): Promise<Noticia | null> {
  const lookup = await leerJson<Lookup>(`/data/${categoria}/lookup.json`, origen);
  const numero = lookup?.parts?.[id];
  if (!numero) return null;

  const parte = await obtenerParte(categoria, numero, origen);
  return parte?.articles.find((articulo) => articulo.id === id) ?? null;
}

/** Noticias relacionadas: misma categoria, excluyendo la actual. */
export async function obtenerRelacionadas(
  actual: Noticia,
  origen: URL,
  limite = 4,
): Promise<Tarjeta[]> {
  const portada = await obtenerPortada(origen);
  if (!portada) return [];
  return portada.articles
    .filter((a) => a.category === actual.category && a.id !== actual.id)
    .slice(0, limite);
}
