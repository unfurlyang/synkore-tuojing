import {test,expect} from '@playwright/test';
test('3D render and desktop-sized layout inspection',async({page})=>{
  page.on('console',msg=>{if(msg.type()==='error'||msg.type()==='warning')console.log('BROWSER',msg.text().slice(0,250))});
  await page.goto('/');await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-loaded','true');await page.waitForTimeout(1700);
  expect(Number(await page.locator('#ghost-canvas').getAttribute('data-render-calls'))).toBeGreaterThan(5);
  await page.screenshot({path:'test-results/visual-desktop.png',fullPage:true});
  await page.setViewportSize({width:1120,height:780});await page.waitForTimeout(300);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'test-results/visual-compact.png',fullPage:true});
});
