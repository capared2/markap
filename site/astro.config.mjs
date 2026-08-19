// @ts-check
import { defineConfig } from "astro/config";
import cloudflare from "@astrojs/cloudflare";
import tailwindcss from "@tailwindcss/vite";

// Render en servidor sobre Cloudflare Workers: el archivo crece sin limite y
// prerenderizar una pagina por noticia chocaria con el tope de ficheros de
// Cloudflare Pages. Cada respuesta se cachea en el edge (ver Base.astro).
export default defineConfig({
  output: "server",
  adapter: cloudflare({ imageService: "passthrough" }),
  vite: { plugins: [tailwindcss()] },
});
