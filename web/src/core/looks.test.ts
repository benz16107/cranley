import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pathIn, splitPath } from './looks.ts'

test('the first path segment is the look, the rest is the place', () => {
  assert.deepEqual(splitPath('/sheet'), { look: 'sheet', place: '/' })
  assert.deepEqual(splitPath('/sheet/'), { look: 'sheet', place: '/' })
  assert.deepEqual(splitPath('/a/map'), { look: 'a', place: '/map' })
  assert.deepEqual(splitPath('/c/scan/abc'), { look: 'c', place: '/scan/abc' })
  assert.deepEqual(splitPath('/scan/abc'), { look: null, place: '/scan/abc' }) // an old link
  assert.deepEqual(splitPath('/'), { look: null, place: '/' })
  assert.deepEqual(splitPath('/about'), { look: null, place: '/about' }) // "a" is a look, "about" is not
})

test('a place keeps its path when the look changes', () => {
  for (const url of ['/sheet', '/sheet/map', '/sheet/scan/abc']) assert.equal(pathIn('sheet', splitPath(url).place), url)
  assert.equal(pathIn('b', splitPath('/sheet/scan/abc').place), '/b/scan/abc')
  assert.equal(pathIn('a', splitPath('/sheet').place), '/a')
})
