import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = join(dirname(fileURLToPath(import.meta.url)), '..')
const readFrontendFile = (...segments) =>
  readFileSync(join(frontend, ...segments), 'utf8')

test('portal links preserve the standalone presales workbench MPA path', () => {
  const portal = readFrontendFile('src', 'App.vue')
  const workbenchEntry = readFrontendFile('presales', 'workbench', 'index.html')
  const viteConfig = readFrontendFile('vite.config.js')

  assert.match(portal, /href: '\/presales\/workbench\/'/)
  assert.match(portal, /href: '\/presales\/workbench\/\?view=agent'/)
  assert.doesNotMatch(portal, /href: '\/presales\/workbench'(?![/?])/)
  assert.match(workbenchEntry, /\/src\/presales\/main\.js/)
  assert.match(viteConfig, /presales\/workbench\/index\.html/)
})

test('presales empty states never pass null to Ant Design Vue AEmpty', () => {
  const workbench = readFrontendFile('src', 'presales', 'PresalesWorkbench.vue')

  assert.match(workbench, /<a-empty v-if="!loadingProjects && !filteredProjects\.length"/)
  assert.doesNotMatch(workbench, /:image="null"/)
})
