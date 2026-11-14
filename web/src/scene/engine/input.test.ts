import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isTrackpad } from './input.ts'

const wheel = (o: { deltaX?: number; deltaY?: number; deltaMode?: number; wheelDeltaY?: number }) =>
  ({ deltaX: 0, deltaY: 0, deltaMode: 0, ...o }) as unknown as WheelEvent

test('a mouse wheel notch is not a trackpad, a small or sideways scroll is', () => {
  assert.equal(isTrackpad(wheel({ deltaY: 100, wheelDeltaY: -120 })), false)
  assert.equal(isTrackpad(wheel({ deltaY: 3, deltaMode: 1 })), false) // line mode: Firefox's mouse wheel
  assert.equal(isTrackpad(wheel({ deltaY: 4, wheelDeltaY: -12 })), true)
  assert.equal(isTrackpad(wheel({ deltaX: 2, deltaY: 0 })), true)
  assert.equal(isTrackpad(wheel({ deltaY: 6 })), true) // no wheelDeltaY: small steps mean a trackpad
})
