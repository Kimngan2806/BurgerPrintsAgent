import assert from 'node:assert/strict';
import test from 'node:test';
import {removeLightBackground} from '../src/lib/mockup-artwork.ts';

function image(width, height, colorAt) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      data.set(colorAt(x, y), (y * width + x) * 4);
    }
  }
  return {width, height, data};
}

const alpha = ({width, data}, x, y) => data[(y * width + x) * 4 + 3];
const gray = (value, opacity = 255) => [value, value, value, opacity];

test('removes framed checkerboard even inside enclosed parts of a design', () => {
  const artwork = image(100, 108, (x, y) => {
    if (x === 99 || y === 107) return gray(65);
    if (y === 106) return gray(252);
    const checker = gray((Math.floor(x / 5) + Math.floor(y / 5)) % 2 ? 199 : 253);
    if (x >= 35 && x < 63 && y >= 41 && y < 67) return checker;
    if (x >= 24 && x < 76 && y >= 22 && y < 86) return [146, 60, 31, 255];
    return checker;
  });

  assert.equal(removeLightBackground(artwork), true);
  assert.equal(alpha(artwork, 99, 36), 0);
  assert.equal(alpha(artwork, 43, 107), 0);
  assert.equal(alpha(artwork, 5, 5), 0);
  assert.equal(alpha(artwork, 49, 52), 0);
  assert.equal(alpha(artwork, 29, 52), 255);
});

test('removes a white backdrop and preserves white detail inside the artwork', () => {
  const artwork = image(80, 80, (x, y) => {
    if (x >= 31 && x <= 48 && y >= 31 && y <= 48) return gray(255);
    if (x >= 22 && x <= 57 && y >= 22 && y <= 57) return [184, 66, 33, 255];
    return gray(255);
  });

  assert.equal(removeLightBackground(artwork), true);
  assert.equal(alpha(artwork, 0, 0), 0);
  assert.equal(alpha(artwork, 40, 40), 255);
});

test('keeps the source when it already has transparency or is solid artwork', () => {
  const transparent = image(80, 80, (x, y) => gray(255, x < 3 && y < 3 ? 0 : 255));
  const solid = image(80, 80, () => gray(255));
  for (const artwork of [transparent, solid]) {
    const original = artwork.data.slice();
    assert.equal(removeLightBackground(artwork), false);
    assert.deepEqual(artwork.data, original);
  }
});
