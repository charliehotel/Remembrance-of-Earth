// README 스크린샷 촬영 3/3: 걷기 모드(2008년·앞모습·올려다보기). 사용법은 capture_readme_1.mjs 와 같다
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
await year(2008.5);
await p.click("#mode"); await sleep(3000); await p.mouse.click(700, 640); await sleep(4000);
await p.keyboard.down("w"); await sleep(3500); await p.keyboard.up("w"); await sleep(1500);
await shot("03_walk_2008");
// 뒤로 걷기: 캐릭터가 돌아서 앞모습으로 걸어온다
await p.keyboard.down("s"); await sleep(2500); await shot("03_walk_front"); await p.keyboard.up("s");
// 위를 올려다보기(R)
await p.keyboard.down("r"); await sleep(1800); await p.keyboard.up("r"); await sleep(800); await shot("03_walk_look_up");
await b.close();
