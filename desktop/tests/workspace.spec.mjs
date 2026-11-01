import {test,expect} from '@playwright/test';
test('three workflows, genuine WebGL mascot, persistence and export',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await expect(page.locator('#connection-label')).toHaveText('模型已配置');
  await expect(page.locator('#ghost-canvas')).toHaveAttribute('data-loaded','true',{timeout:20000});
  expect(Number(await page.locator('#ghost-canvas').getAttribute('data-mesh-count'))).toBeGreaterThan(5);
  await page.getByRole('button',{name:'打个招呼',exact:true}).click();await expect(page.locator('#ghost-message')).not.toHaveText('今天，也一起认真听课吧。');
  await page.locator('#spin-ghost').click();await expect(page.locator('#ghost-message')).toHaveText('转一圈，换个好心情。');
  await page.screenshot({path:'test-results/01-listen.png',fullPage:true});
  await page.getByRole('tab',{name:'输入文字'}).click();await page.locator('#listen-text').fill('体积功等于外压乘以体积变化。');await page.locator('#process-text').click();await expect(page.locator('.result-final').first()).toHaveText('体积功等于外压乘以体积变化。');await expect(page.locator('.result-meta').first()).toContainText('已整理');
  const download=page.waitForEvent('download');await page.locator('#export-live').click();expect((await download).suggestedFilename()).toMatch(/\.md$/);
  await page.locator('[data-view=teachers]').click();await page.locator('[data-teacher-input=text]').click();await page.locator('#teacher-name').fill('验收 · 物理老师');await page.locator('#teacher-transcript').fill('同学们，今天我们从一个简单的例子开始，体积功等于外压乘以体积变化。');await page.locator('#create-teacher').click();await expect(page.locator('#teacher-profiles')).toContainText('验收 · 物理老师');
  await page.locator('.profile-item').filter({hasText:'验收 · 物理老师'}).locator('[data-profile-detail]').click();await expect(page.locator('#profile-detail')).toContainText('保留公式');await page.locator('[data-close=profile-dialog]').click();await page.screenshot({path:'test-results/02-teachers.png',fullPage:true});
  await page.locator('.profile-item').filter({hasText:'验收 · 物理老师'}).locator('[data-use-profile]').click();await expect(page.locator('#view-course')).toBeVisible();
  const samples=Buffer.alloc(32000);const wav=Buffer.alloc(44+samples.length);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples.length,40);
  await page.locator('#course-file').setInputFiles({name:'lesson.wav',mimeType:'audio/wav',buffer:wav});await page.locator('#start-course').click();await expect(page.locator('#course-percent')).toHaveText('100%',{timeout:20000});await expect(page.locator('#course-results .result-final').last()).toContainText('体积功');await page.screenshot({path:'test-results/03-course.png',fullPage:true});
  await page.waitForTimeout(600);await page.reload();await page.locator('[data-view=listen]').click();await expect(page.locator('#live-results')).toContainText('体积功');expect(errors).toEqual([]);
});
test('microphone capture can pause and stop, and unsupported audio is rejected',async({page})=>{
  await page.goto('/');await page.locator('#start-listen').click();await expect(page.locator('#capture-status')).toHaveText('正在聆听');await page.locator('#pause-listen').click();await expect(page.locator('#capture-status')).toHaveText('已暂停');await page.locator('#pause-listen').click();await expect(page.locator('#capture-status')).toHaveText('正在聆听');await page.locator('#stop-listen').click();await expect(page.locator('#start-listen')).toBeVisible();
  await page.locator('[data-input=file]').click();await page.locator('#listen-file').setInputFiles({name:'bad.txt',mimeType:'text/plain',buffer:Buffer.from('not audio')});await expect(page.locator('.toast')).toContainText('WAV、MP3 或 M4A');
});
