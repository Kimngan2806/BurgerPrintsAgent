function brightness(pixels: Uint8ClampedArray, index: number) {
  return (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3;
}

function neutral(pixels: Uint8ClampedArray, index: number, tolerance: number) {
  const r = pixels[index], g = pixels[index + 1], b = pixels[index + 2];
  return Math.max(r, g, b) - Math.min(r, g, b) <= tolerance;
}

type Bounds = {left: number; right: number; top: number; bottom: number};

function imageEdges(width: number, {left, right, top, bottom}: Bounds) {
  return [
    Array.from({length: right - left + 1}, (_, i) => top * width + left + i),
    Array.from({length: right - left + 1}, (_, i) => bottom * width + left + i),
    Array.from({length: bottom - top + 1}, (_, i) => (top + i) * width + left),
    Array.from({length: bottom - top + 1}, (_, i) => (top + i) * width + right),
  ];
}

// A screenshot of a transparency grid can contain the viewer's thin outline.
// Inspect the next rows and columns inwards before sampling the background.
function insideFrame({data, width, height}: ImageData): Bounds {
  const bounds = {left: 0, right: width - 1, top: 0, bottom: height - 1};
  const sides = ['top', 'bottom', 'left', 'right'] as const;
  const limit = Math.min(8, Math.floor(Math.min(width, height) * 0.028));
  for (let inset = 0; inset < limit; inset++) {
    const edges = imageEdges(width, bounds);
    let moved = false;
    sides.forEach((side, i) => {
      const line = edges[i];
      const dark = line.filter(pixel => brightness(data, pixel * 4) < 145 && neutral(data, pixel * 4, 20));
      if (dark.length < line.length * 0.94) return;
      bounds[side] += side === 'top' || side === 'left' ? 1 : -1;
      moved = true;
    });
    if (!moved) break;
  }
  return bounds;
}

function checkerStep(data: Uint8ClampedArray, lines: number[][], midpoint: number, palette: (pixel: number) => boolean) {
  let step = 0, best = 0.69;
  for (let distance = 2; distance <= 28; distance++) {
    for (const line of lines) {
      let pairs = 0, alternating = 0;
      for (let i = 0; i < line.length - distance; i++) {
        const first = line[i], second = line[i + distance];
        if (!palette(first) || !palette(second)) continue;
        const a = brightness(data, first * 4) - midpoint, b = brightness(data, second * 4) - midpoint;
        if (Math.abs(a) < 4 || Math.abs(b) < 4) continue;
        pairs++;
        if (a * b < 0) alternating++;
      }
      if (pairs < 30) continue;
      const score = alternating / pairs - distance * 0.004;
      if (score > best) {
        step = distance;
        best = score;
      }
    }
  }
  return step;
}

// Compression can tint the checker grid right beside the silhouette. Only
// discard pale remnants too narrow to be joined to a solid part of the design.
function removeCheckerFringe({data, width, height}: ImageData, minimum: number) {
  const radius = Math.min(3, Math.max(1, Math.round(Math.min(width, height) / 130)));
  const core = new Uint8Array(width * height);
  let hasCore = false;
  for (let y = radius; y < height - radius; y++) {
    for (let x = radius; x < width - radius; x++) {
      const pixel = y * width + x;
      if (data[pixel * 4 + 3] && data[(pixel - radius) * 4 + 3] &&
          data[(pixel + radius) * 4 + 3] && data[(pixel - radius * width) * 4 + 3] &&
          data[(pixel + radius * width) * 4 + 3]) {
        core[pixel] = 1;
        hasCore = true;
      }
    }
  }
  if (!hasCore) return;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const index = (y * width + x) * 4;
      if (!data[index + 3] || !neutral(data, index, 47) || brightness(data, index) < minimum - 48) continue;
      let supported = false;
      for (let row = Math.max(0, y - radius); row <= Math.min(height - 1, y + radius) && !supported; row++) {
        for (let col = Math.max(0, x - radius); col <= Math.min(width - 1, x + radius); col++) {
          if (!core[row * width + col]) continue;
          supported = true;
          break;
        }
      }
      if (!supported) data[index + 3] = 0;
    }
  }
}

export function removeLightBackground(image: ImageData): boolean {
  const {data, width, height} = image;
  // Transparency in the file takes precedence, including intentional white ink.
  for (let i = 3; i < data.length; i += 4) {
    if (data[i] < 250) return false;
  }

  const bounds = insideFrame(image);
  const {left, right, top, bottom} = bounds;
  const edges = imageEdges(width, bounds);
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

  const minimum = checkerboard ? Math.max(155, low - 20) : 228;
  const isBackground = (pixel: number) => brightness(data, pixel * 4) >= minimum &&
    neutral(data, pixel * 4, checkerboard ? 23 : 19);
  const visited = new Uint8Array(width * height);
  const queue = new Int32Array(width * height);
  let head = 0;
  let tail = 0;
  function visit(pixel: number) {
    if (visited[pixel]) return;
    visited[pixel] = 1;
    if (!isBackground(pixel)) return;
    queue[tail++] = pixel;
  }
  function fill() {
    while (head < tail) {
      const pixel = queue[head++];
      const x = pixel % width;
      const y = Math.floor(pixel / width);
      if (x > left) visit(pixel - 1);
      if (x < right) visit(pixel + 1);
      if (y > top) visit(pixel - width);
      if (y < bottom) visit(pixel + width);
    }
  }
  for (const pixel of border) visit(pixel);
  fill();

  if (checkerboard) {
    const dx = checkerStep(data, edges.slice(0, 2), midpoint, isBackground);
    const dy = checkerStep(data, edges.slice(2), midpoint, isBackground);
    if (dx && dy) {
      const isOpposite = (pixel: number, shade: number) => isBackground(pixel) &&
        (brightness(data, pixel * 4) - midpoint) * shade < -36;
      // A pocket between parts of the subject need not touch any outside edge.
      // Seed it only where the grid repeats in both directions.
      for (let y = top + dy; y <= bottom - dy; y++) {
        for (let x = left + dx; x <= right - dx; x++) {
          const pixel = y * width + x;
          if (visited[pixel] || !isBackground(pixel)) continue;
          const shade = brightness(data, pixel * 4) - midpoint;
          if (Math.abs(shade) < 8) continue;
          if (isOpposite(pixel - dx, shade) && isOpposite(pixel + dx, shade) &&
              isOpposite(pixel - dy * width, shade) && isOpposite(pixel + dy * width, shade)) visit(pixel);
        }
      }
      fill();
    }
  }

  // Leave solid artwork intact when there is no identifiable foreground.
  if (!tail || tail > (right - left + 1) * (bottom - top + 1) * 0.995) return false;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (x < left || x > right || y < top || y > bottom) data[(y * width + x) * 4 + 3] = 0;
    }
  }
  for (let i = 0; i < tail; i++) data[queue[i] * 4 + 3] = 0;
  if (checkerboard) removeCheckerFringe(image, minimum);
  return true;
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
