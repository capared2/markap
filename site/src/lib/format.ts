const FECHA = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Europe/Madrid",
});

const FECHA_HORA = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Madrid",
});

export function fecha(iso: string | null, conHora = false): string {
  if (!iso) return "";
  const valor = new Date(iso);
  if (Number.isNaN(valor.getTime())) return "";
  return (conHora ? FECHA_HORA : FECHA).format(valor);
}

/** "hace 3 h", "ayer"… para las tarjetas de portada. */
export function haceCuanto(iso: string | null): string {
  if (!iso) return "";
  const valor = new Date(iso).getTime();
  if (Number.isNaN(valor)) return "";

  const minutos = Math.round((Date.now() - valor) / 60000);
  if (minutos < 1) return "ahora";
  if (minutos < 60) return `hace ${minutos} min`;

  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;

  const dias = Math.round(horas / 24);
  if (dias === 1) return "ayer";
  if (dias < 30) return `hace ${dias} días`;
  return fecha(iso);
}

/** "futbol/real-madrid" -> "Fútbol · Real Madrid" */
export function nombreCategoria(clave: string): string {
  return clave.split("/").map(titulo).join(" · ");
}

/** Ultimo tramo de la categoria, para etiquetas cortas. */
export function etiquetaCategoria(clave: string): string {
  const partes = clave.split("/");
  return titulo(partes[partes.length - 1]!);
}

const ACENTOS: Record<string, string> = {
  futbol: "Fútbol",
  baloncesto: "Baloncesto",
  atletico: "Atlético",
  formula1: "Fórmula 1",
  motogp: "MotoGP",
  nba: "NBA",
  nfl: "NFL",
  acb: "ACB",
  mls: "MLS",
  f1: "F1",
  "mas-deporte": "Más Deporte",
  "vuelta-espana": "Vuelta a España",
  "copa-del-rey": "Copa del Rey",
  "champions-league": "Champions League",
  "europa-league": "Europa League",
  "conference-league": "Conference League",
  "primera-division": "Primera División",
  "segunda-division": "Segunda División",
  seleccion: "Selección",
  malaga: "Málaga",
  cadiz: "Cádiz",
  leganes: "Leganés",
  almeria: "Almería",
  alaves: "Alavés",
  "futbol-internacional": "Fútbol Internacional",
  "juegos-olimpicos": "Juegos Olímpicos",
  esports: "eSports",
  tiramillas: "Tiramillas",
  // Ediciones internacionales de Marca, que cuelgan de su propio prefijo.
  co: "Marca Colombia",
  mx: "Marca México",
  us: "Marca USA",
  en: "Marca English",
  ar: "Marca Argentina",
  cl: "Marca Chile",
  pe: "Marca Perú",
  ve: "Marca Venezuela",
  "claro-sports": "Claro Sports",
  "combates-ufc": "Combates / UFC",
};

// Palabras que no llevan mayuscula dentro de un nombre de seccion.
const MINUSCULAS = new Set(["y", "de", "del", "la", "el", "en", "los", "las", "a"]);

function titulo(texto: string): string {
  if (ACENTOS[texto]) return ACENTOS[texto]!;
  return texto
    .split("-")
    .map((palabra, indice) =>
      indice > 0 && MINUSCULAS.has(palabra)
        ? palabra
        : palabra.charAt(0).toUpperCase() + palabra.slice(1),
    )
    .join(" ");
}

export function enlaceNoticia(categoria: string, id: string): string {
  return `/noticia/${categoria}/${id}`;
}

export function enlaceCategoria(clave: string, pagina = 1): string {
  return pagina > 1 ? `/categoria/${clave}?p=${pagina}` : `/categoria/${clave}`;
}

export function numero(valor: number): string {
  return new Intl.NumberFormat("es-ES").format(valor);
}

/**
 * Acento por seccion: da a cada vertical una identidad reconocible, como en
 * cualquier portada de diario deportivo.
 */
const COLORES: Record<string, string> = {
  futbol: "#d8232a",
  baloncesto: "#e8730c",
  motor: "#1668c4",
  tenis: "#1a8f4b",
  ciclismo: "#8c4bc9",
  golf: "#0f8f86",
  atletismo: "#c2185b",
  balonmano: "#0277a8",
  nfl: "#5a3ec8",
  esports: "#00a3a3",
  tiramillas: "#b8860b",
  apuestas: "#4a5568",
};

export function colorSeccion(clave: string): string {
  return COLORES[clave.split("/")[0]!] ?? "var(--color-marca)";
}

/** "jueves, 20 de agosto de 2026" con una sola mayuscula inicial. */
export function fechaLarga(valor: Date): string {
  const texto = new Intl.DateTimeFormat("es-ES", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Europe/Madrid",
  }).format(valor);
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
