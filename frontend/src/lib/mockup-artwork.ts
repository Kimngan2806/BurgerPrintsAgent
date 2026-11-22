function brightness(pixels: Uint8ClampedArray, index: number) {
  return (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3;
}

function neutral(pixels: Uint8ClampedArray, index: number, tolerance: number) {
  const r = pixels[index], g = pixels[index + 1], b = pixels[index + 2];
  return Math.max(r, g, b) - Math.min(r, g, b) <= tolerance;
}

export function removeLightBackground(image: ImageData): boolean {
  const {data, width, height} = image;
  // Transparency in the file takes precedence, including intentional white ink.
  for (let i = 3; i < data.length; i += 4) {
    if (data[i] < 250) return false;
  }

  const edges = [
    Array.from({length: width}, (_, i) => i),
    Array.from({length: width}, (_, i) => (height - 1) * width + i),
    Array.from({length: height}, (_, i) => i * width),
    Array.from({length: height}, (_, i) => i * width + width - 1),
  ];
  const border = edges.flat();
  const samples = border
    .filter(pixel => neutral(data, pixel * 4, 16) && brightness(data, pixel * 4) >= 160)
    .map(pixel => brightness(data, pixel * 4)).sort((a, b) => a - b);
  if (samples.length < border.length * 0.64) return false;

  const low = samples[Math.floor(samples.length * 0.15)];
  const high = samples[Math.floor(samples.length * 0.85)];
  const midpoint = (low + high) / 2;
  const alternatingEdges = edges.filter(edge => {
    let previous = -1;
    let switches = 0;
    for (const pixel of edge) {
      const next = brightness(data, pixel * 4) >= midpoint ? 1 : 0;
      if (previous >= 0 && next !== previous) switches++;
      previous = next;
    }
    return switches >= 6;
  }).length;
  const checkerboard = high - low >= 8 && alternatingEdges >= 2;
  const plainWhite = samples.filter(value => value >= 234).length >= border.length * 0.58;
  if (!checkerboard && !plainWhite) return false;

  const minimum = checkerboard ? Math.max(155, low - 17) : 228;
  const visited = new Uint8Array(width * height);
  const queue = new Int32Array(width * height);
  let head = 0;
  let tail = 0;
  function visit(pixel: number) {
    if (visited[pixel]) return;
    visited[pixel] = 1;
    const index = pixel * 4;
    if (brightness(data, index) < minimum || !neutral(data, index, checkerboard ? 23 : 19)) return;
    queue[tail++] = pixel;
    data[index + 3] = 0;
  }
  for (const pixel of border) visit(pixel);
  while (head < tail) {
    const pixel = queue[head++];
    const x = pixel % width;
    if (x > 0) visit(pixel - 1);
    if (x < width - 1) visit(pixel + 1);
    if (pixel >= width) visit(pixel - width);
    if (pixel + width < width * height) visit(pixel + width);
  }
  // A solid white or pale image can itself be the design.
  if (tail > width * height * 0.995) {
    for (let i = 0; i < tail; i++) data[queue[i] * 4 + 3] = 255;
    return false;
  }
  return tail > 0;
}

export function prepareArtwork(image: HTMLImageElement, removeBackground: boolean) {
  const source = document.createElement('canvas');
  const ratio = Math.min(1, 1016 / Math.max(image.naturalWidth, image.naturalHeight));
  source.width = Math.max(1, Math.round(image.naturalWidth * ratio));
  source.height = Math.max(1, Math.round(image.naturalHeight * ratio));
  const context = source.getContext('2d', {willReadFrequently: true});
  if (!context) return null;
  context.drawImage(image, 0, 0, source.width, source.height);
  const pixels = context.getImageData(0, 0, source.width, source.height);
  const removed = removeBackground && removeLightBackground(pixels);
  if (removed) context.putImageData(pixels, 0, 0);

  let left = source.width;
  let top = source.height;
  let right = -1;
  let bottom = -1;
  for (let y = 0; y < source.height; y++) {
    for (let x = 0; x < source.width; x++) {
      if (pixels.data[(y * source.width + x) * 4 + 3] < 8) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x);
      bottom = y;
    }
  }
  if (right < left) return null;

  const canvas = document.createElement('canvas');
  const width = right - left + 1;
  const height = bottom - top + 1;
  canvas.width = width + 8;
  canvas.height = height + 8;
  const target = canvas.getContext('2d');
  if (!target) return null;
  target.drawImage(source, left, top, width, height, 4, 4, width, height);
  return {canvas, removed};
}
