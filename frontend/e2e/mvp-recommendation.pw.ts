import { expect, test } from '@playwright/test'

test('isolated semantic MVP recommendations render through authenticated SSE', async ({ page }) => {
  page.on('dialog', (dialog) => void dialog.accept())
  await page.addInitScript(() => {
    const target = window as Window & { __mvpSseBodies: string[] }
    target.__mvpSseBodies = []
    const originalFetch = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const response = await originalFetch(input, init)
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.includes('/api/conversations/') && url.endsWith('/messages')) {
        void response.clone().text().then((body) => target.__mvpSseBodies.push(body))
      }
      return response
    }
  })
  await page.goto('/')

  await page.getByRole('button', { name: '회원가입' }).click()
  await page.getByLabel('이메일').fill('mvp-e2e@example.test')
  await page.getByLabel('이름').fill('MVP E2E')
  await page.getByLabel('비밀번호').fill('mvp-e2e-password-123')
  await page.getByRole('button', { name: '회원가입' }).click()
  await expect(page.getByRole('heading', { name: '로그인' })).toBeVisible()

  await page.getByLabel('이메일').fill('mvp-e2e@example.test')
  await page.getByLabel('비밀번호').fill('mvp-e2e-password-123')
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByLabel('점심 추천 요청')).toBeVisible()

  const prompts = [
    { query: '떡볶이 먹고 싶어', reason: /떡볶이 메뉴가 확인/ },
    { query: '혼밥하면서 떡볶이 먹고 싶어', reason: /떡볶이 메뉴가 확인/ },
    { query: '가성비 좋은 곳', reason: /가성비/ },
  ]
  for (const { query, reason } of prompts) {
    await page.getByLabel('점심 추천 요청').fill(query)
    await page.getByRole('button', { name: '메시지 전송' }).click()
    const recommendationList = page.getByLabel('추천 음식점').last()
    await expect(recommendationList).toBeVisible({ timeout: 45_000 })
    await expect(recommendationList.getByText('마성김밥 논현역점')).toBeVisible()
    await expect(recommendationList.locator('.recommendation-card')).toHaveCount(1)
    const reasonText = recommendationList.locator('.recommendation-card p').last()
    await expect(reasonText).toHaveText(reason)
    const eventIndex = prompts.findIndex((item) => item.query === query)
    await expect.poll(() => page.evaluate(() => (window as Window & { __mvpSseBodies: string[] }).__mvpSseBodies.length)).toBe(eventIndex + 1)
    const sseBody = await page.evaluate((index) => (window as Window & { __mvpSseBodies: string[] }).__mvpSseBodies[index], eventIndex)
    expect(sseBody).toContain('event:recommendations')
    const recommendationEvent = sseBody.match(/event:recommendations\s+data:(.+)/)?.[1]
    expect(recommendationEvent).toBeTruthy()
    const payload = JSON.parse(recommendationEvent!) as { items: Array<{ restaurantId: number; reason: string }> }
    expect(payload.items).toHaveLength(1)
    expect(payload.items[0].restaurantId).toBe(9617)
    expect(payload.items[0].reason).toBe(await reasonText.innerText())
    console.log(`MVP_E2E_QUERY_RESULT ${JSON.stringify({ query, restaurantIds: payload.items.map((item) => item.restaurantId), reason: payload.items[0].reason, recommendationCount: payload.items.length, sseEvent: 'recommendations' })}`)
  }
})
