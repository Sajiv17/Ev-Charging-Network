// Render the ER diagram (from the LIVE schema) and the EER specialization diagram to SVG + PNG.
//
//   cd scripts/db/diagrams && npm install && node render_diagrams.mjs
//
// The ER diagram is generated from information_schema on the Bangalore node (all nodes have an
// identical schema, see run_db_tests.sh), so it can never drift from the DDL. Every column, PK,
// UNIQUE and FK is drawn; replicated tables are blue, fragmented tables are green.
// Crow's-foot ends: child side "zero or many", parent side "exactly one" (or "zero or one" when
// the FK column is nullable).
// Outputs: docs/images/er_diagram.{svg,png}, docs/images/eer_users.{svg,png}
// No browser needed: Graphviz runs as WebAssembly and resvg rasterises the SVG.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Graphviz } from "@hpcc-js/wasm-graphviz";
import { Resvg } from "@resvg/resvg-js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, "../../../docs/images");
const NODE = process.env.EV_NODE || "ev-mysql-bangalore";
const DB = process.env.EV_DB || "ev_bangalore";
const ROOT_PW = process.env.MYSQL_ROOT_PASSWORD || "evcharge_root_2024";

const REPLICATED = new Set(["cities", "connector_types", "pricing_plans", "corridors", "users", "vehicles"]);
const COLORS = { replicated: "#D6E6F7", fragmented: "#DDF1DA" };
const FONT = "Arial";

function query(sql) {
  const out = execFileSync(
    "docker",
    ["exec", NODE, "mysql", "-uroot", `-p${ROOT_PW}`, "-N", "-B", DB, "-e", sql],
    { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
  );
  return out.trim().split("\n").filter(Boolean).map((line) => line.split("\t"));
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function erDot() {
  const cols = query(`
    SELECT table_name, column_name, column_type, column_key, is_nullable
      FROM information_schema.columns WHERE table_schema = DATABASE()
     ORDER BY table_name, ordinal_position`);
  const fks = query(`
    SELECT table_name, column_name, referenced_table_name, referenced_column_name
      FROM information_schema.key_column_usage
     WHERE table_schema = DATABASE() AND referenced_table_name IS NOT NULL
     ORDER BY table_name, column_name`);
  const uniques = new Set(
    query(`SELECT table_name, column_name FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND non_unique = 0 AND index_name <> 'PRIMARY'`)
      .map(([t, c]) => `${t}.${c}`),
  );
  const fkSet = new Set(fks.map(([t, c]) => `${t}.${c}`));
  const nullable = new Set(cols.filter((c) => c[4] === "YES").map(([t, c]) => `${t}.${c}`));

  const tables = new Map();
  for (const [t, c, type, key] of cols) {
    if (!tables.has(t)) tables.set(t, []);
    tables.get(t).push({ c, type: type.replace(/^enum\(.*\)$/, "enum").replace(/ unsigned/, ""), pk: key === "PRI" });
  }

  const lines = [
    "digraph er {",
    `  graph [rankdir=LR, splines=true, nodesep=0.35, ranksep=1.1, fontname="${FONT}", bgcolor="white",`,
    `         label=<<b>EV Charging Network: MySQL schema (identical on every city node)</b><br/>` +
      `<font point-size="11">blue = replicated (same rows and IDs on every node), green = fragmented by city (IDs repeat across nodes)` +
      `<br/>PK primary key, FK foreign key, UQ unique; generated from information_schema</font>>, labelloc=t, fontsize=18];`,
    `  node [shape=plain, fontname="${FONT}", fontsize=11];`,
    `  edge [dir=both, color="#555555", arrowsize=0.8];`,
  ];
  for (const [t, columns] of tables) {
    const color = REPLICATED.has(t) ? COLORS.replicated : COLORS.fragmented;
    const kind = REPLICATED.has(t) ? "replicated" : "fragmented";
    const rows = columns.map(({ c, type, pk }) => {
      const tags = [pk && "PK", fkSet.has(`${t}.${c}`) && "FK", uniques.has(`${t}.${c}`) && "UQ"].filter(Boolean);
      const name = pk ? `<b><u>${esc(c)}</u></b>` : esc(c);
      // Graphviz rejects an empty <b></b> and then silently drops the whole label.
      const tagCell = tags.length ? `<font color="#1F5FA8"><b>${tags.join(" ")}</b></font>` : " ";
      return `<tr><td port="${c}" align="left">${name}</td><td align="left"><font color="#666666">${esc(type)}</font></td>` +
        `<td align="left">${tagCell}</td></tr>`;
    });
    lines.push(
      `  ${t} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="3" color="#888888">` +
        `<tr><td colspan="3" bgcolor="${color}"><b>${t}</b>  <font point-size="9">(${kind})</font></td></tr>` +
        rows.join("") + "</table>>];",
    );
  }
  for (const [t, c, rt, rc] of fks) {
    const parentEnd = nullable.has(`${t}.${c}`) ? "teeodot" : "teetee";
    lines.push(`  ${t}:${c} -> ${rt}:${rc} [arrowtail=crowodot, arrowhead=${parentEnd}];`);
  }
  lines.push("}");
  return lines.join("\n");
}

function eerDot() {
  return fs.readFileSync(path.join(HERE, "eer_users.dot"), "utf8");
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const gv = await Graphviz.load();
  for (const [name, dot] of [["er_diagram", erDot()], ["eer_users", eerDot()]]) {
    const svg = gv.dot(dot);
    fs.writeFileSync(path.join(OUT, `${name}.svg`), svg);
    const png = new Resvg(svg, {
      background: "white",
      fitTo: { mode: "zoom", value: 2 },
      font: { loadSystemFonts: true, defaultFontFamily: FONT },
    }).render().asPng();
    fs.writeFileSync(path.join(OUT, `${name}.png`), png);
    console.log(`wrote docs/images/${name}.svg and .png`);
  }
}

main();
