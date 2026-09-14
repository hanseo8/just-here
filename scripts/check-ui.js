// 배포 전 정적 점검: index.html과 app.js/styles.css의 참조 불일치 찾기
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "web/styles.css"), "utf8");

// 정적 마크업 + app.js가 주입하는 마크업 둘 다 id 출처로 본다
const ids = new Set([
  ...[...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]),
  ...[...js.matchAll(/id="([^"]+)"/g)].map((m) => m[1]),
]);
const usedIds = new Set([...js.matchAll(/\$\("([^"]+)"\)/g)].map((m) => m[1]));
const missingIds = [...usedIds].filter((id) => !ids.has(id));

const classes = new Set(
  [...html.matchAll(/class="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/))
);
const unstyled = [...classes].filter(
  (c) => c && c !== "hidden" && !css.includes("." + c)
);

console.log("app.js가 찾는데 HTML에 없는 id:", missingIds);
console.log("CSS 규칙이 없는 HTML class:", unstyled);
console.log("중괄호 균형:", css.split("{").length - css.split("}").length);

process.exit(missingIds.length ? 1 : 0);
