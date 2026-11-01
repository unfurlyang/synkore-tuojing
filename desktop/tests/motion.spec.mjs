import {test,expect} from '@playwright/test';
test('pet, high five, sleep, wake and drag are real 3D reactions',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/');const canvas=page.locator('#ghost-canvas');await expect(canvas).toHaveAttribute('data-loaded','true');
  await page.locator('[data-ghost-action=pet]').click();await expect(canvas).toHaveAttribute('data-interaction','pet');await expect(page.locator('#ghost-message')).toContainText('谢谢你');expect(Number(await canvas.getAttribute('data-bursts'))).toBeGreaterThan(0);
  await page.locator('[data-ghost-action=highfive]').click();await expect(canvas).toHaveAttribute('data-interaction','highfive');await expect(page.locator('#ghost-message')).toContainText('默契');await page.waitForTimeout(250);await page.screenshot({path:'test-results/04-highfive.png',fullPage:true});
  await page.locator('[data-ghost-action=sleep]').click();await expect(canvas).toHaveAttribute('data-asleep','true');await expect(page.locator('[data-ghost-action=sleep]')).toHaveAttribute('aria-pressed','true');await page.locator('[data-ghost-action=sleep]').click();await expect(canvas).toHaveAttribute('data-asleep','false');
  const rect=await canvas.boundingBox();await page.mouse.move(rect.x+rect.width*.4,rect.y+rect.height*.5);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.75,rect.y+rect.height*.56,{steps:9});await page.mouse.up();await expect(canvas).toHaveAttribute('data-interaction','drag');
  await page.locator('[data-view=teachers]').click();await expect(page.locator('html')).toHaveAttribute('data-motion-view','view-teachers');expect(errors).toEqual([]);
});
test('header switches voice independently of animation and system reduced motion is respected',async({page})=>{
  await page.goto('/');await page.locator('#voice-pack-toggle').click();await expect(page.locator('#voice-pack-toggle')).toHaveText('灵动');await expect(page.locator('html')).toHaveAttribute('data-motion','full');await page.waitForTimeout(500);await page.reload();await expect(page.locator('#voice-pack-toggle')).toHaveText('灵动');
  await page.emulateMedia({reducedMotion:'reduce'});await expect(page.locator('html')).toHaveAttribute('data-motion','subtle');const before=Number(await page.locator('#ghost-canvas').getAttribute('data-bursts'))||0;await page.locator('[data-ghost-action=pet]').click();expect(Number(await page.locator('#ghost-canvas').getAttribute('data-bursts'))||0).toBe(before);
});
