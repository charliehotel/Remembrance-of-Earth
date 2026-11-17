// README 스크린샷 촬영 1/2: 지도·연도별·기억 찾기. npm i puppeteer-core 후 node 로 실행(서버가 8765에서 떠 있어야 함). 사용: node scripts/capture_readme_1.mjs assets/readme
import puppeteer from "puppeteer-core";
const OUT = process.argv[2];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new",
  args: ["--use-angle=metal", "--enable-webgl", "--ignore-gpu-blocklist", "--window-size=1440,900"], defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 } });
const p = await b.newPage();
p.on("pageerror", e => console.log("pageerror", e.message));
await p.goto("http://localhost:8765/", { waitUntil: "load" }); await sleep(7000);
const shot = n => p.screenshot({ path: `${OUT}/${n}.png` });
const year = async v => { await p.evaluate(v => { const s = document.getElementById("slider"); s.value = v; s.dispatchEvent(new Event("input", { bubbles: true })); }, v); await sleep(3500); };
await shot("01_overview_2026");
await year(2000.5); await shot("02_time_2000");
await year(2012.5); await shot("02_time_2012");
await year(2026.84); await sleep(1500);
const click = sel => p.click(sel);
await click("#mode"); await sleep(5000); await shot("03_walk"); await click("#mode"); await sleep(3000);
// 기억 찾기
await p.type("#agText", "2010년경 독수리다방 앞 카레집");
await click("#agGo"); await sleep(25000); await shot("04_agent");
await b.close();
