import {build} from "esbuild";
import {readFile, writeFile, mkdir, rm} from "node:fs/promises";
import {basename, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const assets = resolve(root, "dist", "assets");
await rm(assets, {recursive: true, force: true});
await mkdir(assets, {recursive: true});
const result = await build({
  absWorkingDir: root,
  entryPoints: ["src/main.tsx"],
  outdir: assets,
  entryNames: "app-[hash]",
  chunkNames: "chunk-[hash]",
  bundle: true,
  splitting: true,
  format: "esm",
  minify: true,
  target: ["chrome120", "edge120", "firefox121", "safari17"],
  metafile: true,
});
const main = Object.entries(result.metafile.outputs).find(([, output]) => output.entryPoint === "src/main.tsx");
if (!main?.[1].cssBundle) throw new Error("Expected the observatory script and stylesheet");
const html = await readFile(resolve(root, "index.html"), "utf8");
await writeFile(resolve(root, "dist", "index.html"), html
  .replace("</head>", `<link rel="stylesheet" href="/assets/${basename(main[1].cssBundle)}"></head>`)
  .replace("/src/main.tsx", `/assets/${basename(main[0])}`));
for (const [file, entry] of Object.entries(result.metafile.outputs)) console.log(`${file} (${entry.bytes} bytes)`);
