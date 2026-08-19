export interface Imagen {
  url: string;
  caption?: string;
}

/** Registro completo tal y como lo guarda el scraper. */
export interface Noticia {
  id: string;
  url: string;
  category: string;
  category_path: string[];
  section: string;
  breadcrumbs: string[];
  title: string;
  standfirst: string;
  summary: string;
  body: string;
  paragraphs: string[];
  word_count: number;
  authors: string[];
  tags: string[];
  published_at: string | null;
  modified_at: string | null;
  language: string;
  images: Imagen[];
  videos: string[];
  is_premium: boolean;
  source: string;
  scraped_at: string;
}

/** Version ligera que viaja en latest.json, sin cuerpo. */
export interface Tarjeta {
  id: string;
  url: string;
  category: string;
  title: string;
  standfirst: string;
  summary: string;
  authors: string[];
  published_at: string | null;
  is_premium: boolean;
  image: string | null;
}

export interface ArchivoParte {
  category: string;
  part: number;
  count: number;
  updated_at: string;
  articles: Noticia[];
}

export interface EntradaCategoria {
  category: string;
  articles: number;
  files: { file: string; count: number }[];
}

export interface Indice {
  source: string;
  generated_at: string;
  total_articles: number;
  total_categories: number;
  categories: EntradaCategoria[];
}

export interface Portada {
  generated_at: string;
  count: number;
  articles: Tarjeta[];
}

export interface Lookup {
  category: string;
  count: number;
  parts: Record<string, number>;
}
