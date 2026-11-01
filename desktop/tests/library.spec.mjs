import {test,expect} from '@playwright/test';
test('public profiles, six course options and shared selection work without reloading',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await page.locator('[data-view=teachers]').click();
 await expect(page.locator('#teacher-profiles')).toContainText('一数');
 await expect(page.locator('#teacher-profiles')).toContainText('宋浩');
 await expect(page.locator('#teacher-profiles')).toContainText('李永乐');
 await page.locator('[data-profile-detail="preset-yishu"]').click();
 await expect(page.locator('#profile-detail')).toContainText('不是本人生成');
 await expect(page.locator('[data-public-source]').first()).toHaveAttribute('data-public-source',/bilibili/);
 await page.locator('[data-close=profile-dialog]').click();
 await page.locator('[data-use-profile="preset-songhao"]').click();
 await expect(page.locator('#library-course option')).toHaveCount(6);
 await page.locator('#library-course').selectOption('calculus-1');
 await page.locator('.library-preview summary').click();
 await expect(page.locator('#library-text')).toContainText('1/3');
 await page.locator('#library-start').click();
 await expect(page.locator('#library-job-text')).toContainText('已完成',{timeout:20000});
 await expect(page.locator('#course-results')).toContainText('极限');
 // Simulate the same selection endpoint used by the board; the page must follow it.
 const user=await page.evaluate(()=>JSON.parse(localStorage.getItem('tingjian.workspace')).userId);
 await page.request.put('/v1/library/selection',{data:{user_id:user,profile_id:'preset-liyongle',course_id:'python'}});
 await expect(page.locator('#course-profile')).toHaveValue('preset-liyongle');
 await expect(page.locator('#library-course')).toHaveValue('python');
 await page.screenshot({path:'test-results/15-course-library.png',fullPage:true});
 await page.reload();await page.locator('[data-view=course]').click();
 await expect(page.locator('#library-course')).toHaveValue('python');
 expect(errors).toEqual([]);
});
