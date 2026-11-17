// README 스크린샷 촬영 2/2: 걷기 모드·골목의 연대기 리포트·질문. 사용법은 capture_readme_1.mjs 와 같다
import puppeteer from "puppeteer-core";
const OUT = process.argv[2];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "new",
  args: ["--use-angle=metal", "--enable-webgl", "--ignore-gpu-blocklist", "--window-size=1440,900"], defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 1 } });
const p = await b.newPage();
p.on("pageerror", e => console.log("pageerror", e.message));
await p.goto("http://localhost:8765/", { waitUntil: "load" }); await sleep(7000);
const shot = n => p.screenshot({ path: `${OUT}/${n}.png` });
// 걷기 모드: 길 위에 캐릭터를 내려놓고 앞으로 걷는다
await p.click("#mode"); await sleep(3000); await p.mouse.click(700, 640); await sleep(4000);
await p.keyboard.down("w"); await sleep(2500); await p.keyboard.up("w"); await sleep(1500);
await shot("03_walk");
await p.keyboard.press("Escape"); await sleep(1500);
await p.evaluate(() => { const m = document.getElementById("mode"); if (/날기|취소/.test(m.textContent) === false) {} });
await p.reload({ waitUntil: "load" }); await sleep(7000);
// 골목의 연대기
await p.click("#agMode"); await sleep(800);
await p.click("#sideWide"); await sleep(900);
await p.click('#areaTools button[data-shape="rect"]'); await sleep(500);
await p.mouse.move(640, 130); await p.mouse.down(); await p.mouse.move(900, 300, { steps: 12 }); await p.mouse.move(1180, 560, { steps: 12 }); await p.mouse.up();
await sleep(3500); await shot("05_report_top");
await p.evaluate(() => { const e = document.getElementById("arLog"); (e.scrollIntoView ? e.scrollIntoView() : 0); });
const sc = await p.evaluateHandle(() => document.querySelector("#sideBody") || document.getElementById("side"));
await p.evaluate(el => { el.scrollTop = 520; }, sc); await sleep(800); await shot("05_report_composition");
await p.evaluate(el => { el.scrollTop = 1100; }, sc); await sleep(800); await shot("05_report_survival");
await p.evaluate(el => { el.scrollTop = 0; }, sc);
await p.click("#agText"); await p.type("#agText", "이 골목 업종이 어떻게 바뀌었어?");
await p.click("#agGo"); await sleep(25000);
await p.evaluate(el => { el.scrollTop = el.scrollHeight; }, sc); await sleep(800); await shot("06_question");
await b.close();
