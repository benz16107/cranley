import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decodeSegment, pathIn, scanIn, sharedToken, splitPath } from './looks.ts'

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

test('a read-only link is the place /shared/<token>', () => {
  assert.equal(sharedToken(splitPath('/app/shared/q1w2e3r4t5y6u7i8o9p0aA').place), 'q1w2e3r4t5y6u7i8o9p0aA')
  assert.equal(sharedToken('/shared/Ab_c-123456/'), 'Ab_c-123456')
  assert.equal(sharedToken('/shared/'), null)
  assert.equal(sharedToken('/shared/a b'), null) // not a token: nothing is asked of the server
  assert.equal(sharedToken('/investigations/ws_12345678'), null)
})

test('a malformed link is read as it stands, it does not throw', () => {
  assert.equal(scanIn('/scan/abc%20def/more'), 'abc def')
  assert.equal(scanIn('/scan/%E0%A4%A'), '%E0%A4%A') // a broken escape: decodeURIComponent alone throws URIError here
  assert.equal(scanIn('/map'), null)
  assert.equal(decodeSegment('100%'), '100%')
})
