import {test,expect} from '@playwright/test';
test('natural voice packs switch, cancel on mute and suppress during capture',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.speechSynthesis.speak=()=>{throw Error('System TTS must not be used')};window.__sounds=[];const Native=window.Audio;window.Audio=new Proxy(Native,{construct(Target,args){const audio=new Target(...args);window.__sounds.push(audio);return audio;}})});
 await page.goto('/');await expect(page.locator('#synkore-intro')).toHaveAttribute('data-sound','playing');
 expect(await page.locator('.app-shell').evaluate(e=>getComputedStyle(e).visibility)).toBe('hidden');
 await expect(page.locator('#synkore-intro')).toHaveCount(0,{timeout:6000});
 await expect(page.locator('.gesture-hint')).toHaveCount(0);
 const dimensions=await page.locator('#ghost-stage').evaluate(e=>({w:e.offsetWidth,h:e.offsetHeight,r:getComputedStyle(e).borderRadius}));expect(Math.abs(dimensions.w-dimensions.h)).toBeLessThan(2);expect(dimensions.r).toBe('50%');
 await page.locator('#preview-ghost-voice').click();await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-pack','gentle');
 await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','true');
 const motion=await page.locator('html').getAttribute('data-motion');
 await page.locator('#voice-pack-toggle').click();await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-pack','bright');
 await expect(page.locator('#voice-pack-toggle')).toHaveText('灵动');expect(await page.locator('html').getAttribute('data-motion')).toBe(motion);
 expect(await page.locator('#ghost-message').textContent()).toBe(await page.locator('#ghost-canvas').getAttribute('data-last-spoken'));
 await expect(page.locator('#voice-bright')).toHaveAttribute('aria-pressed','true');
 await page.waitForTimeout(450);expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('tingjian.workspace')).sound.pack)).toBe('bright');
 await page.locator('#toggle-ghost-voice').click();await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','false');expect(await page.evaluate(()=>window.__sounds.every(a=>a.paused))).toBe(true);
 await page.locator('#toggle-ghost-voice').click();await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','true');
 await page.locator('#ghost-canvas').evaluate(e=>e.dataset.captureActive='true');await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','false');
 await page.locator('#preview-ghost-voice').click();await page.waitForTimeout(250);expect(await page.evaluate(()=>window.__sounds.every(a=>a.paused))).toBe(true);
 await page.screenshot({path:'test-results/voice14.png',fullPage:true});expect(errors).toEqual([]);
});

test('new displayed sentence cancels old speech and reads exactly the new text',async({page})=>{
 await page.goto('/');await expect(page.locator('#synkore-intro')).toHaveCount(0,{timeout:6000});
 await page.locator('#preview-ghost-voice').click();await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','true');
 await page.evaluate(()=>{document.querySelector('#ghost-message').textContent='谢谢你，感觉好温暖。';document.dispatchEvent(new CustomEvent('synkore-message',{detail:{text:'谢谢你，感觉好温暖。'}}));});
 await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','false');
 await page.waitForTimeout(1800);await page.locator('#preview-ghost-voice').click();
 await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-last-spoken','谢谢你，感觉好温暖。');
 await expect(page.locator('#ghost-message')).toHaveText('谢谢你，感觉好温暖。');
});

test('saved effects mute also silences startup audio',async({page})=>{
 await page.addInitScript(()=>{localStorage.setItem('tingjian.workspace',JSON.stringify({userId:'voice-muted-test',live:[],course:[],sound:{effects:false,voice:false,pack:'gentle'}}));window.__sounds=[];const Native=window.Audio;window.Audio=new Proxy(Native,{construct(Target,args){const audio=new Target(...args);window.__sounds.push(args[0]);return audio;}})});
 await page.goto('/');await expect(page.locator('#synkore-intro')).toBeVisible();await page.waitForTimeout(350);expect(await page.evaluate(()=>window.__sounds.filter(s=>String(s).includes('synkore-intro.wav')).length)).toBe(0);
});

test('verification failure is shown and never starts speech',async({page})=>{
 await page.route('**/v1/companion/speech',r=>r.fulfill({status:502,contentType:'application/json',body:JSON.stringify({detail:'语音与文字核对未通过，已停止播报'})}));
 await page.goto('/');await expect(page.locator('#synkore-intro')).toHaveCount(0,{timeout:6000});
 await page.evaluate(()=>{document.querySelector('#ghost-message').textContent='未通过核对的测试句';document.dispatchEvent(new CustomEvent('synkore-message',{detail:{text:'未通过核对的测试句'}}));});
 await page.locator('#preview-ghost-voice').click();await expect(page.locator('#voice-availability')).toContainText('核对未通过');await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','false');
});

test('corrupted packaged speech is blocked by content hash',async({page})=>{
 await page.route('**/assets/voice16/**/*.wav',r=>r.fulfill({status:200,contentType:'audio/wav',body:'RIFF-corrupted'}));
 await page.goto('/');await expect(page.locator('#synkore-intro')).toHaveCount(0,{timeout:6000});await page.locator('#preview-ghost-voice').click();await expect(page.locator('#voice-availability')).toContainText('文件校验失败');await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-voice-speaking','false');
});
