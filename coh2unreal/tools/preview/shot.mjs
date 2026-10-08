import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const [,, url, out] = process.argv;
const b = await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const p = await b.newPage({viewport:{width:1280,height:800}});
p.on('console', m => console.log('console:', m.text()));
await p.goto(url); await p.waitForFunction('window.DONE', null, {timeout: 900000});
console.log(await p.evaluate('window.DONE')); await p.screenshot({path: out}); await b.close();
