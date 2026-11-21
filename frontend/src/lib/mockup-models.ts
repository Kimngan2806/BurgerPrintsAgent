import * as THREE from 'three';
import {DecalGeometry} from 'three/addons/geometries/DecalGeometry.js';

export type MockupKind = 't-shirt' | 'mug';

export type MockupModel = {
  group: THREE.Group;
  surface: THREE.MeshStandardMaterial;
  trim?: THREE.MeshStandardMaterial;
  createPrint: (scale: number) => THREE.BufferGeometry;
};

function shirt(): MockupModel {
  const outline = new THREE.Shape();
  outline.moveTo(0, 1.02);
  outline.quadraticCurveTo(0.25, 1.02, 0.36, 1.27);
  outline.quadraticCurveTo(0.63, 1.22, 0.84, 1.15);
  outline.lineTo(1.23, 0.91);
  outline.quadraticCurveTo(1.30, 0.84, 1.32, 0.76);
  outline.lineTo(1.14, 0.30);
  outline.quadraticCurveTo(0.94, 0.34, 0.76, 0.52);
  outline.quadraticCurveTo(0.70, -0.08, 0.79, -1.00);
  outline.quadraticCurveTo(0.78, -1.09, 0, -1.09);
  outline.quadraticCurveTo(-0.77, -1.07, -0.79, -1.00);
  outline.quadraticCurveTo(-0.70, -0.08, -0.76, 0.52);
  outline.quadraticCurveTo(-0.97, 0.33, -1.16, 0.32);
  outline.lineTo(-1.34, 0.76);
  outline.quadraticCurveTo(-1.32, 0.86, -1.23, 0.93);
  outline.lineTo(-0.84, 1.15);
  outline.quadraticCurveTo(-0.63, 1.22, -0.36, 1.27);
  outline.quadraticCurveTo(-0.25, 1.02, 0, 1.02);
  outline.closePath();

  const geometry = new THREE.ExtrudeGeometry(outline, {
    depth: 0.30,
    steps: 1,
    curveSegments: 16,
    bevelEnabled: true,
    bevelSegments: 7,
    bevelSize: 0.035,
    bevelThickness: 0.065,
  });
  geometry.translate(0, 0, -0.15);
  const surface = new THREE.MeshStandardMaterial({roughness: 0.94});
  const trim = new THREE.MeshStandardMaterial({roughness: 1});
  const body = new THREE.Mesh(geometry, surface);
  body.castShadow = true;
  body.receiveShadow = true;

  const group = new THREE.Group();
  group.add(body);
  for (const front of [-1, 1]) {
    const neck = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(-0.33, 1.20, front * 0.205),
      new THREE.Vector3(0, 0.86, front * 0.22),
      new THREE.Vector3(0.33, 1.20, front * 0.205),
    );
    group.add(new THREE.Mesh(new THREE.TubeGeometry(neck, 30, 0.035, 8, false), trim));
  }
  return {
    group, surface, trim,
    createPrint: scale => new DecalGeometry(
      body,
      new THREE.Vector3(0, 0.13, 0.215),
      new THREE.Euler(),
      new THREE.Vector3(0.88 * scale, 0.88 * scale, 0.19),
    ),
  };
}

function mug(): MockupModel {
  const profile = [
    [0, -0.66], [0.48, -0.66], [0.59, -0.65], [0.63, -0.62], [0.65, -0.55],
    [0.65, 0.58], [0.646, 0.62], [0.63, 0.645], [0.603, 0.648],
    [0.58, 0.635], [0.57, 0.60], [0.57, -0.49], [0.55, -0.52], [0, -0.53],
  ].map(([radius, y]) => new THREE.Vector2(radius, y));
  const surface = new THREE.MeshStandardMaterial({roughness: 0.30});
  const body = new THREE.Mesh(new THREE.LatheGeometry(profile, 96), surface);
  const handleCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.54, 0.37, 0),
    new THREE.Vector3(0.93, 0.42, 0),
    new THREE.Vector3(1.10, 0.24, 0),
    new THREE.Vector3(1.07, -0.12, 0),
    new THREE.Vector3(0.88, -0.36, 0),
    new THREE.Vector3(0.54, -0.37, 0),
  ]);
  const handle = new THREE.Mesh(new THREE.TubeGeometry(handleCurve, 48, 0.073, 14, false), surface);
  body.castShadow = handle.castShadow = true;
  body.receiveShadow = handle.receiveShadow = true;
  const group = new THREE.Group();
  group.add(body, handle);
  group.scale.setScalar(1.50);
  group.position.x = -0.18;
  return {
    group, surface,
    createPrint: scale => {
      const radius = 0.652;
      const height = 0.78 * scale;
      const angle = height / radius;
      return new THREE.CylinderGeometry(radius, radius, height, 48, 1, true, -angle / 2, angle);
    },
  };
}

export function createMockupModel(kind: MockupKind): MockupModel {
  return kind === 'mug' ? mug() : shirt();
}
