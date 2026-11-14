import { test } from 'node:test'
import assert from 'node:assert/strict'
import { captureImage, droneImage, floorplanImage, panoEquirect, panoFace } from './api.ts'

test('an id is one path segment, whatever is in it', () => {
  assert.equal(panoFace('abc', 'p1', 2), '/api/scan/abc/pano/p1/2.jpg?res=2k') // an ordinary id is unchanged
  assert.equal(panoFace('a/b', 'p?x#y'), '/api/scan/a%2Fb/pano/p%3Fx%23y/1.jpg?res=2k')
  assert.equal(panoEquirect('../workspace', 'p 1', 1024, 'defurnished'), '/api/scan/..%2Fworkspace/pano/p%201/equirect.jpg?w=1024&view=defurnished')
  assert.equal(floorplanImage('s', 'f/1'), '/api/scan/s/floorplan/f%2F1.jpg?flags=photogramy')
  assert.equal(droneImage('s?', 'DJI 0001.JPG', 800), '/api/scan/s%3F/drone/DJI%200001.JPG?w=800')
})

test('a capture ref is an id, or an id and a frame number', () => {
  assert.equal(captureImage('cap_1'), '/api/capture/cap_1/file')
  assert.equal(captureImage('cap_1#3'), '/api/capture/cap_1/frame/3.jpg')
  assert.equal(captureImage('cap/../x#3/4'), '/api/capture/cap%2F..%2Fx/frame/3%2F4.jpg')
})
