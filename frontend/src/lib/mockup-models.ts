import * as THREE from 'three';
import type {MockupKind} from './mockup-types';

export type MockupModel = {
  group: THREE.Group;
  surface: THREE.MeshStandardMaterial;
  trim?: THREE.MeshStandardMaterial;
  print: THREE.BufferGeometry;
  printAspect: number;
};

type Point = (u: number, v: number) => [number, number, number];
const {sin, cos, abs, pow, PI} = Math;
const {lerp, smoothstep} = THREE.MathUtils;

function grid(columns: number, rows: number, point: Point, reverse = false) {
  const positions: number[] = [], uv: number[] = [], indices: number[] = [];
  for (let row = 0; row <= rows; row++) {
    for (let column = 0; column <= columns; column++) {
      const u = column / columns, v = row / rows;
      positions.push(...point(u, v));
      uv.push(u, v);
      if (row === rows || column === columns) continue;
      const a = row * (columns + 1) + column, b = a + 1, c = a + columns + 1, d = c + 1;
      indices.push(...(reverse ? [a, c, b, b, c, d] : [a, b, c, b, d, c]));
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function patch(point: Point, left: number, right: number, bottom: number, top: number, offset = 0.008) {
  return grid(34, 34, (u, v) => {
    const [x, y, z] = point(lerp(left, right, u), lerp(bottom, top, v));
    return [x, y, z + offset];
  });
}

function fabric() {
  return new THREE.MeshPhysicalMaterial({roughness: 0.89, sheen: 0.55, sheenRoughness: 0.85,
    sheenColor: new THREE.Color('#7e7a75'), side: THREE.DoubleSide});
}

function mesh(group: THREE.Group, geometry: THREE.BufferGeometry, material: THREE.Material) {
  const object = new THREE.Mesh(geometry, material);
  object.castShadow = true;
  object.receiveShadow = true;
  group.add(object);
  return object;
}

function tubing(group: THREE.Group, points: number[][], radius: number, material: THREE.Material) {
  const path = new THREE.CatmullRomCurve3(points.map(([x, y, z]) => new THREE.Vector3(x, y, z)));
  return mesh(group, new THREE.TubeGeometry(path, 44, radius, 12, false), material);
}

function garment(kind: MockupKind, name: string): MockupModel {
  const group = new THREE.Group();
  const surface = fabric();
  const trim = fabric();
  const hoodie = kind === 'hoodie';
  const dress = kind === 'dress';
  const onesie = kind === 'onesie';
  const tank = kind === 'tank-top' || /sleeveless/i.test(name);
  const longSleeve = hoodie || kind === 'sweatshirt' || kind === 'long-sleeve';
  const crop = /crop(ped)?\b/i.test(name);
  const hem = dress ? -1.28 : crop ? -0.76 : -1.24;
  const shoulders = onesie ? 0.59 : 0.70;
  const bulk = hoodie || kind === 'sweatshirt' ? 1.10 : 1;

  const torso: Point = (u, v) => {
    const a = (u - 0.5) * 2 * PI;
    const sx = sin(a), sz = cos(a);
    const neck = pow(smoothstep(v, 0.72, 1), 4.3);
    const waist = 0.048 * Math.exp(-pow((v - 0.37) * 4.5, 2));
    const shoulder = 0.052 * smoothstep(v, 0.38, 0.74);
    const width = (shoulders - waist + shoulder + (dress ? 0.39 * pow(1 - v, 2.1) : 0)) * bulk;
    const fold = (sin(13 * a + 4.7 * v) + 0.46 * sin(22 * a - 10 * v)) *
      (0.006 + 0.012 * abs(sx)) * (1 - neck);
    const drape =
      0.028 * sin(8 * a + 5.5 * v) * Math.exp(-pow((v - 0.27) * 3.2, 2)) +
      0.027 * sin(10 * a - 12 * v) * smoothstep(abs(sx), 0.42, 0.94) * sin(v * PI);
    const armhole = tank ? 1 - 0.32 * abs(sx) * smoothstep(v, 0.70, 0.88) * (1 - neck) : 1;
    const x = sx * lerp(width, 0.255, neck) * (1 + 0.016 * sin(5 * a + 4 * v)) * armhole;
    const depth = lerp((0.31 + 0.068 * smoothstep(v, 0.38, 0.78)) * bulk, 0.20, neck);
    const z = sz * (depth + fold + drape);
    const y = lerp(hem, 1.17, v) - (0.16 * Math.max(0, sz) + 0.02) * smoothstep(v, 0.86, 1)
      + 0.044 * abs(sx) * Math.exp(-pow((v - 0.83) * 8, 2))
      + (1 - smoothstep(v, 0, 0.2)) * 0.024 * cos(3 * a);
    return [x, y, z];
  };
  mesh(group, grid(112, 85, torso), surface);
  mesh(group, grid(100, 5, (u, v) => {
    const [x, y, z] = torso(u, 0.006 + v * 0.025);
    return [x * 1.009, y, z * 1.012];
  }), trim);
  mesh(group, grid(100, 5, (u, v) => {
    const [x, y, z] = torso(u, 0.987 + v * 0.013);
    return [x * (1.027 - 0.012 * v), y + 0.018 * v, z * (1.028 - 0.016 * v)];
  }), trim);

  if (!tank) {
    for (const side of [-1, 1]) {
      const sleeve = (u: number, v: number, edge = 0): [number, number, number] => {
        const a = u * 2 * PI;
        const offset = longSleeve ? 0.73 : 0.72;
        const drop = longSleeve ? 1.59 : 0.40;
        const length = Math.hypot(offset, drop);
        const attachment = smoothstep(v, 0, 0.28);
        const r = lerp((onesie ? 0.235 : longSleeve ? 0.275 : 0.31) * bulk, longSleeve ? 0.145 : 0.218, v)
          * lerp(0.83, 1, attachment) + edge;
        const ripple = 1 + (0.017 * sin(6 * a + 8 * v) + 0.014 * sin(9 * a - 5 * v)) * smoothstep(v, 0, 0.52);
        const shoulderX = shoulders * (longSleeve ? 0.47 : 0.61);
        return [
          side * (shoulderX + offset * v + sin(a) * r * ripple * drop / length),
          0.72 + 0.03 * attachment - drop * v + sin(a) * r * ripple * offset / length,
          cos(a) * r * 0.95 * ripple,
        ];
      };
      mesh(group, grid(56, 42, sleeve, side === 1), surface);
      mesh(group, grid(56, 6, (u, v) => sleeve(u, 0.961 + v * 0.039, 0.006), side === 1), trim);
    }
  }

  if (hoodie) {
    const hood: Point = (u, v) => {
      const a = lerp(0.57, 2 * PI - 0.57, u);
      const radius = lerp(0.72, 1, smoothstep(v, 0, 0.34)) * pow(cos(v * PI / 2), 0.60);
      return [sin(a) * 0.45 * radius, 1.03 + v * 0.64 - 0.055 * cos(a) * radius,
        cos(a) * 0.37 * radius - 0.090];
    };
    mesh(group, grid(60, 35, hood), surface);
    for (const side of [-1, 1]) {
      tubing(group, [[side * 0.18, 1.13, 0.255], [side * 0.20, 0.9, 0.438],
        [side * 0.16, 0.65, 0.462], [side * 0.20, 0.51, 0.474]], 0.012, trim);
    }
    mesh(group, grid(38, 23, (u, v) => {
      const [x, y, z] = torso(0.5 + (u - 0.5) * lerp(0.24, 0.16, v), lerp(0.15, 0.30, v));
      return [x, y, z + 0.010 + 0.012 * sin(u * PI) * sin(v * PI)];
    }), trim);
  }
  if (kind === 'polo') {
    for (const side of [-1, 1]) {
      mesh(group, grid(16, 12, (u, v) => [
        side * lerp(0.045, 0.34, u),
        lerp(1.13 - 0.10 * u, 0.89 + 0.09 * u, v),
        0.235 + v * 0.07 - 0.045 * u,
      ], side === 1), trim);
    }
    for (const y of [0.83, 0.91]) mesh(group, new THREE.SphereGeometry(0.017, 12, 8), trim).position.set(0, y, 0.37);
  }
  if (onesie) {
    for (const x of [-0.08, 0, 0.08]) mesh(group, new THREE.SphereGeometry(0.015, 12, 8), trim).position.set(x, -1.15, 0.32);
  }
  const print = patch(torso, 0.392, 0.608, hoodie ? 0.36 : 0.22, 0.73);
  if (hoodie) group.position.y = -0.15;
  return {group, surface, trim, print, printAspect: hoodie ? 1.07 : 0.78};
}

function roundware(kind: MockupKind, name: string): MockupModel {
  const group = new THREE.Group();
  const surface = new THREE.MeshPhysicalMaterial({roughness: 0.28, clearcoat: 0.25, clearcoatRoughness: 0.26});
  const trim = new THREE.MeshStandardMaterial({roughness: 0.42});
  const mug = kind === 'mug';
  const jar = /jar|vase|glass|candle/i.test(name);
  const vase = /vase/i.test(name);
  const tall = !mug && !/shot|rocks|candle/i.test(name);
  const height = tall ? 2.35 : 1.64;
  const radius = mug ? 0.75 : tall ? 0.55 : 0.71;
  const bottomRadius = radius * (mug ? 0.96 : 0.84);
  const rim = radius * (vase ? 0.68 : 1);
  const half = height / 2;
  const profile = [
    [0, -half], [bottomRadius - 0.04, -half], [bottomRadius, -half + 0.038],
    [bottomRadius, -half + 0.076], [radius, half * 0.40],
    [rim, half - 0.048], [rim - 0.008, half - 0.013], [rim - 0.033, half],
    [rim - 0.062, half - 0.016], [rim - 0.077, half - 0.064],
    [bottomRadius - 0.08, -half + 0.14], [0, -half + 0.13],
  ].map(([r, y]) => new THREE.Vector2(r, y));
  mesh(group, new THREE.LatheGeometry(profile, 100), surface);
  if (mug || /with straw|mason/.test(name.toLowerCase())) {
    tubing(group, [[radius * 0.92, half * 0.61, 0], [radius + 0.29, half * 0.64, 0], [radius + 0.48, 0.23, 0],
      [radius + 0.46, -0.25, 0], [radius + 0.25, -half * 0.58, 0], [radius * 0.9, -half * 0.59, 0]], 0.083, mug ? surface : trim);
    group.position.x = -0.12;
  }
  if (!mug && !jar) {
    mesh(group, new THREE.CylinderGeometry(radius * 1.019, radius * 1.019, 0.10, 80), trim).position.y = half;
    if (/straw/i.test(name)) tubing(group, [[0.15, half, 0], [0.15, half + 0.30, 0], [0.08, half + 0.36, 0]], 0.028, trim);
  }
  const bottom = -half + 0.15, top = half * (vase ? 0.39 : 0.81);
  const print = grid(65, 20, (u, v) => {
    const y = lerp(bottom, top, v);
    const r = (y <= half * 0.4
      ? lerp(bottomRadius, radius, (y + half - 0.076) / (1.4 * half - 0.076))
      : lerp(radius, rim, (y - half * 0.4) / (half * 0.6 - 0.048))) + 0.004;
    const a = (u - 0.5) * 2.25;
    return [sin(a) * r, y, cos(a) * r];
  });
  return {group, surface, trim, print, printAspect: radius * 2.25 / (top - bottom)};
}

function roundedShape(width: number, height: number, radius: number) {
  const x = width / 2, y = height / 2;
  const shape = new THREE.Shape();
  shape.moveTo(-x + radius, -y);
  shape.lineTo(x - radius, -y); shape.quadraticCurveTo(x, -y, x, -y + radius);
  shape.lineTo(x, y - radius); shape.quadraticCurveTo(x, y, x - radius, y);
  shape.lineTo(-x + radius, y); shape.quadraticCurveTo(-x, y, -x, y - radius);
  shape.lineTo(-x, -y + radius); shape.quadraticCurveTo(-x, -y, -x + radius, -y);
  return shape;
}

function solid(shape: THREE.Shape, depth: number, bevel: number) {
  const geometry = new THREE.ExtrudeGeometry(shape, {depth, bevelEnabled: bevel > 0, bevelSize: bevel,
    bevelThickness: bevel, bevelSegments: 4, curveSegments: 28});
  geometry.translate(0, 0, -depth / 2);
  return geometry;
}

function plate(kind: MockupKind, name: string): MockupModel {
  const group = new THREE.Group();
  const framed = /framed|picture frame/.test(name);
  const ornament = kind === 'ornament';
  const phone = kind === 'phone-case';
  const circular = /circle|\bround\b|clock|medallion/.test(name);
  const aspectText = name.match(/(\d+):(\d+)/);
  const aspect = phone ? 0.57 : aspectText ? Number(aspectText[1]) / Number(aspectText[2])
    : /portrait|notebook|oval/.test(name) ? 0.72 : /landscape|rectangle|insert card/.test(name) ? 1.5 : 1;
  let width = 2.08 * Math.min(1, aspect), height = 2.08 * Math.min(1, 1 / aspect);
  if (kind === 'sticker') { width *= 0.86; height *= 0.86; }
  const surface = new THREE.MeshStandardMaterial({roughness: ornament ? 0.38 : 0.77});
  const trim = new THREE.MeshStandardMaterial({roughness: 0.60});
  const depth = phone ? 0.15 : framed || /canvas|block|plaque|box/.test(name) ? 0.16
    : kind === 'sticker' ? 0.014 : 0.056;
  const bevel = phone ? 0.026 : 0.012;
  const shape = roundedShape(width, height, phone ? 0.14 : ornament ? 0.055 : 0.024);
  let outline = shape;
  if (circular || /oval/.test(name)) {
    outline = new THREE.Shape();
    outline.absellipse(0, 0, width / 2, height / 2, 0, 2 * PI, false, 0);
  } else if (/heart|star/.test(name) && ornament) {
    outline = new THREE.Shape();
    if (/star/.test(name)) {
      for (let i = 0; i < 10; i++) {
        const a = i * PI / 5, r = i % 2 ? 0.50 : 1.02;
        if (!i) outline.moveTo(0, r);
        else outline.lineTo(-sin(a) * r, cos(a) * r);
      }
      outline.closePath();
    } else {
      outline.moveTo(0, -0.92);
      outline.bezierCurveTo(-0.38, -0.62, -1.04, -0.15, -1.01, 0.40);
      outline.bezierCurveTo(-1.00, 1.00, -0.25, 1.09, 0, 0.59);
      outline.bezierCurveTo(0.25, 1.09, 1.00, 1.00, 1.01, 0.40);
      outline.bezierCurveTo(1.04, -0.15, 0.38, -0.62, 0, -0.92);
    }
  }
  mesh(group, solid(outline, depth, bevel), surface);
  const front = depth / 2 + bevel;
  if (framed) {
    const frame = roundedShape(width + 0.11, height + 0.11, 0.04);
    const opening = new THREE.Path(roundedShape(width - 0.12, height - 0.12, 0.03).getPoints());
    frame.holes.push(opening);
    mesh(group, solid(frame, 0.07, 0.014), trim).position.z = front - 0.01;
  }
  if (phone) {
    const camera = mesh(group, solid(roundedShape(0.47, 0.49, 0.09), 0.038, 0.01), trim);
    camera.position.set(-width * 0.225, height * 0.32, front);
    const lens = new THREE.MeshStandardMaterial({color: '#202426', metalness: 0.25, roughness: 0.28});
    for (const [x, y] of [[-0.34, 0.78], [-0.18, 0.68], [-0.34, 0.58]]) {
      const glass = mesh(group, new THREE.CylinderGeometry(0.063, 0.063, 0.025, 24), lens);
      glass.position.set(x, y, front + 0.03);
      glass.rotateX(PI / 2);
    }
  }
  if (ornament && /ornament|keychain|charm|suncatcher/.test(name)) {
    const ring = mesh(group, new THREE.TorusGeometry(/keychain/.test(name) ? 0.16 : 0.09, 0.021, 10, 35), trim);
    ring.position.set(0, height / 2 + 0.095, 0);
  }
  if (ornament && /night light/.test(name)) {
    mesh(group, solid(roundedShape(width + 0.10, 0.21, 0.06), 0.60, 0.03), trim).position.y = -height / 2;
  }
  if (kind === 'card' && /folded/.test(name)) {
    const back = mesh(group, solid(shape, 0.018, 0.009), trim);
    back.position.z = -0.06;
    back.rotateX(-0.17);
  }
  const simpleShape = circular || /oval|heart|star/.test(name);
  const printWidth = width * (simpleShape ? 0.55 : phone ? 0.84 : 0.88);
  const printHeight = height * (simpleShape ? 0.49 : phone ? 0.62 : 0.87);
  const print = new THREE.PlaneGeometry(printWidth, printHeight);
  print.translate(0, phone ? -0.18 : 0, front + 0.006);
  return {group, surface, trim, print, printAspect: printWidth / printHeight};
}

function fabricObject(kind: MockupKind, name: string): MockupModel {
  const group = new THREE.Group();
  const surface = fabric();
  const trim = fabric();
  const bag = kind === 'bag';
  const pillow = kind === 'pillow';
  const backpack = /backpack/.test(name);
  const compactBag = /fanny|crossbody/.test(name);
  const landscape = /horizontal|landscape|rectangle|rug|doormat|mouse|\bmat\b/.test(name);
  const width = pillow || landscape ? 2.25 : bag ? 1.72 : 1.61;
  const height = backpack ? 1.88 : bag ? compactBag ? 1.03 : 1.6 : landscape ? 1.39 : pillow ? 1.89 : 2.26;
  const puff = pillow ? 0.35 : backpack ? 0.39 : bag ? 0.22 : 0.024;
  const panel: Point = (u, v) => {
    const s = (u - 0.5) * 2, t = (v - 0.5) * 2;
    const edge = pow(Math.max(0, sin(u * PI) * sin(v * PI)), 0.65);
    return [
      s * width / 2 * (1 - 0.06 * pow(abs(t), 6)),
      t * height / 2 * (1 - 0.07 * pow(abs(s), 6)) - (bag ? 0.20 : 0),
      0.04 + puff * edge + sin(14 * s + 5 * t) * (pillow ? 0.014 : 0.025) * sin(v * PI),
    ];
  };
  mesh(group, grid(55, 55, panel), surface);
  mesh(group, grid(55, 55, (u, v) => {
    const [x, y, z] = panel(u, v);
    return [x, y, -z + 0.08];
  }, true), surface);
  if (bag && !compactBag) {
    for (const side of [-1, 1]) tubing(group, [[-0.54, 0.39, side * 0.18], [-0.51, 0.89, side * 0.17],
      [-0.36, 1.29, side * 0.16], [0, 1.34, side * 0.16], [0.36, 1.29, side * 0.16],
      [0.51, 0.89, side * 0.17], [0.54, 0.39, side * 0.18]], 0.054, trim);
  }
  if (compactBag) tubing(group, [[-0.78, 0.05, 0], [-1.04, 0.28, -0.20],
    [0, 0.69, -0.66], [1.04, 0.28, -0.20], [0.78, 0.05, 0]], 0.046, trim);
  if (backpack) tubing(group, [[-0.73, -0.31, 0.29], [0, -0.24, 0.453], [0.73, -0.31, 0.29]], 0.020, trim);
  if (/flag|banner/.test(name)) {
    const bar = mesh(group, new THREE.CylinderGeometry(0.021, 0.021, width + 0.22, 20), trim);
    bar.position.y = height / 2; bar.rotateZ(PI / 2);
  }
  if (/apron/.test(name)) tubing(group, [[-0.42, 0.78, 0], [-0.31, 1.19, 0], [0, 1.35, 0],
    [0.31, 1.19, 0], [0.42, 0.78, 0]], 0.042, trim);
  const print = patch(panel, 0.11, 0.89, 0.13, 0.87);
  return {group, surface, trim, print, printAspect: width / height};
}

function cap(name: string): MockupModel {
  const group = new THREE.Group();
  const surface = fabric();
  const trim = fabric();
  const bucket = /bucket/.test(name);
  const crown: Point = (u, v) => {
    const a = (u - 0.5) * 2 * PI, polar = v * PI / 2;
    const r = bucket ? lerp(1, 0.78, v) : Math.max(0.012, cos(polar));
    return [1.03 * r * sin(a), -0.36 + (bucket ? 0.82 * v : 1.16 * sin(polar)),
      0.78 * r * cos(a) - 0.22];
  };
  mesh(group, grid(96, 44, crown), surface);
  if (bucket) {
    const top = mesh(group, new THREE.CircleGeometry(0.803, 72), surface);
    top.rotateX(-PI / 2); top.scale.y = 0.76; top.position.set(0, 0.46, -0.22);
  }
  const brim = grid(70, 19, (u, v) => {
    const a = (u - 0.5) * (bucket ? 2 * PI : 2.72);
    return [sin(a) * (1.03 + v * (bucket ? 0.30 : -0.16)),
      -0.36 - v * (bucket ? 0.24 : 0.13) - (1 - cos(a)) * v * 0.07,
      cos(a) * (0.78 + v * (bucket ? 0.29 : 0.72)) - 0.22];
  }, true);
  mesh(group, brim, trim);
  if (!bucket) {
    mesh(group, new THREE.SphereGeometry(0.052, 22, 12), trim).position.set(0, 0.79, -0.22);
  }
  const print = patch(crown, 0.391, 0.609, 0.12, 0.53);
  return {group, surface, trim, print, printAspect: 1.78};
}

function bottoms(name: string): MockupModel {
  const group = new THREE.Group();
  const surface = fabric(), trim = fabric();
  const skirt = /skirt/.test(name);
  const short = /short|boxer/.test(name);
  const top = 0.95, lower = short ? -0.44 : -1.23;
  const waist: Point = (u, v) => {
    const a = (u - 0.5) * 2 * PI;
    const flare = skirt ? 1 + (1 - v) * 0.52 : 1;
    return [0.76 * flare * sin(a), lerp(skirt ? -0.95 : 0.25, top, v),
      (0.28 + (skirt ? 0.051 * cos(a * 12) : 0)) * flare * cos(a)];
  };
  mesh(group, grid(64, 36, waist), surface);
  mesh(group, patch(waist, 0, 1, 0.91, 1, 0.001), trim);
  if (!skirt) {
    for (const side of [-1, 1]) {
      mesh(group, grid(54, 48, (u, v) => {
        const a = (u - 0.5) * 2 * PI;
        const r = lerp(short ? 0.30 : 0.19, 0.39, v) + sin(9 * v + 5 * a) * 0.017;
        return [side * (0.41 - 0.05 * v) + r * sin(a), lerp(lower, 0.59, v), r * 0.75 * cos(a)];
      }), surface);
    }
  }
  return {group, surface, trim, print: patch(waist, 0.39, 0.61, 0.26, 0.80), printAspect: skirt ? 1.05 : 1.7};
}

function shoe(): MockupModel {
  const group = new THREE.Group();
  const surface = fabric();
  const trim = new THREE.MeshStandardMaterial({roughness: 0.85});
  const upper = new THREE.Shape();
  upper.moveTo(-1.14, -0.47);
  upper.quadraticCurveTo(-1.21, -0.05, -0.79, -0.03);
  upper.quadraticCurveTo(-0.48, 0.02, -0.22, 0.39);
  upper.quadraticCurveTo(-0.02, 0.60, 0.20, 0.44);
  upper.quadraticCurveTo(0.55, 0.27, 0.98, 0.43);
  upper.quadraticCurveTo(1.21, 0.28, 1.11, -0.48);
  upper.closePath();
  mesh(group, solid(upper, 0.65, 0.08), surface);
  mesh(group, solid(roundedShape(2.35, 0.22, 0.105), 0.77, 0.043), trim).position.y = -0.52;
  for (let i = 0; i < 4; i++) {
    const x = -0.49 + i * 0.102, y = 0.04 + i * 0.104;
    tubing(group, [[x, y + 0.005, -0.275], [x + 0.074, y + 0.036, 0], [x, y + 0.005, 0.275]], 0.016, trim);
  }
  const print = new THREE.PlaneGeometry(0.84, 0.48);
  print.translate(0.50, -0.15, 0.412);
  return {group, surface, trim, print, printAspect: 1.75};
}

function accessory(name: string): MockupModel {
  const group = new THREE.Group();
  const surface = fabric();
  const trim = fabric();
  if (/jewelry box/.test(name)) {
    const shape = roundedShape(1.94, 1.27, 0.14);
    mesh(group, solid(shape, 0.69, 0.048), surface).position.z = -0.07;
    mesh(group, solid(shape, 0.12, 0.036), trim).position.z = 0.34;
    const print = new THREE.PlaneGeometry(1.61, 0.98).translate(0, 0, 0.444);
    return {group, surface, trim, print, printAspect: 1.64};
  }
  if (/tree skirt|pet collar/.test(name)) {
    const collar = /pet collar/.test(name);
    const outer = collar ? 1.1 : 1.25, inner = collar ? 0.91 : 0.29;
    const ring: Point = (u, v) => {
      const a = lerp(-PI * 0.94, PI * 0.94, u), r = lerp(inner, outer, v);
      return [r * sin(a), r * cos(a) * (collar ? 0.72 : 0.92), 0.05 + 0.06 * sin(7 * a)];
    };
    mesh(group, grid(84, 15, ring), surface);
    if (collar) {
      mesh(group, solid(roundedShape(0.40, 0.24, 0.035), 0.13, 0.025), trim).position.set(0, 0.72, 0.07);
    }
    return {group, surface, trim,
      print: patch(ring, collar ? 0.66 : 0.39, collar ? 0.92 : 0.61, 0.11, 0.89),
      printAspect: collar ? 8.1 : 1.8};
  }
  const sleeve = /arm sleeve/.test(name);
  const profile: Point = (u, v) => {
    const angle = (u - 0.5) * 2 * PI;
    const r = 0.34 + 0.10 * v + 0.017 * sin(8 * angle + 7 * v);
    const foot = sleeve ? 0 : 0.51 * (1 - smoothstep(v, 0.05, 0.45));
    return [sin(angle) * r - foot, lerp(-1.2, 1.11, v), cos(angle) * r * 0.68];
  };
  mesh(group, grid(72, 60, profile), surface);
  mesh(group, grid(70, 7, (u, v) => {
    const [x, y, z] = profile(u, 0.878 + 0.122 * v);
    return [x * 1.02, y, z * 1.03];
  }), trim);
  const print = patch(profile, 0.33, 0.67, 0.34, 0.84);
  return {group, surface, trim, print, printAspect: 0.67};
}

export function createMockupModel(kind: MockupKind, productName = ''): MockupModel {
  const name = productName.toLowerCase();
  switch (kind) {
    case 't-shirt': case 'hoodie': case 'sweatshirt': case 'long-sleeve':
    case 'polo': case 'tank-top': case 'onesie': case 'dress':
      return garment(kind, name);
    case 'mug': case 'tumbler': return roundware(kind, name);
    case 'bag': case 'pillow': case 'textile': return fabricObject(kind, name);
    case 'cap': return cap(name);
    case 'bottoms': return bottoms(name);
    case 'shoes': return shoe();
    case 'accessory': return accessory(name);
    default: return plate(kind, name);
  }
}
