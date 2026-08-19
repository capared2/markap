// Copia el dataset scrapeado a public/ para que quede publicado junto al sitio
// y las paginas puedan leerlo en tiempo de ejecucion.
import { cp, mkdir, rm, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const origen = resolve(here, "../../data");
const destino = resolve(here, "../public/data");

try {
  await stat(origen);
} catch {
  console.error(`No existe ${origen}. Ejecuta el scraper antes de construir el sitio.`);
  process.exit(1);
}

await rm(destino, { recursive: true, force: true });
await mkdir(dirname(destino), { recursive: true });
await cp(origen, destino, { recursive: true });
console.log(`Dataset copiado a ${destino}`);
