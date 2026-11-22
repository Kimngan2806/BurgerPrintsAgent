'use client';

import {useEffect, useRef, useState} from 'react';
import {Check, MousePointer2, Move, Pause, Play, RotateCcw, RotateCw, Scan} from 'lucide-react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {createMockupModel, type MockupModel} from '@/lib/mockup-models';
import {prepareArtwork} from '@/lib/mockup-artwork';
import {centeredArtwork, mockupLabels, type MockupKind, type Placement} from '@/lib/mockup-types';

type ViewerProps = {
  kind: MockupKind;
  color: string;
  productName?: string;
  artworkUrl?: string;
  removeBackground: boolean;
  scale: number;
  position: Placement;
  onPositionChange: (position: Placement) => void;
};

function disposeModel(model: MockupModel) {
  const materials = new Set<THREE.Material>();
  materials.add(model.surface);
  if (model.trim) materials.add(model.trim);
  model.group.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    object.geometry.dispose();
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      materials.add(material);
    }
  });
  materials.forEach(material => material.dispose());
}

function softShadow() {
  const size = 96;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const radius = Math.hypot((x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1);
      data[(y * size + x) * 4 + 3] = 69 * Math.max(0, 1 - radius * radius) ** 3;
    }
  }
  const texture = new THREE.DataTexture(data, size, size);
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({map: texture, transparent: true, depthWrite: false, toneMapped: false}));
  shadow.rotateX(-Math.PI / 2);
  return shadow;
}

function makeViewer(
  host: HTMLDivElement,
  onPositionChange: ViewerProps['onPositionChange'],
  stopSpin: () => void,
  onPlacingChange: (active: boolean) => void,
) {
  const renderer = new THREE.WebGLRenderer({alpha: true, antialias: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  const canvas = renderer.domElement;
  canvas.setAttribute('aria-hidden', 'true');
  host.appendChild(canvas);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 24);
  const controls = new OrbitControls(camera, canvas);
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.minPolarAngle = 0.35;
  controls.maxPolarAngle = Math.PI - 0.35;
  controls.autoRotateSpeed = 1.3;

  scene.add(new THREE.HemisphereLight(0xffffff, 0xc8c5c0, 1.62));
  const keyLight = new THREE.DirectionalLight(0xfffdfb, 2.05);
  keyLight.position.set(-3.2, 5.1, 3.3);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(1024, 1024);
  keyLight.shadow.camera.left = keyLight.shadow.camera.bottom = -2.25;
  keyLight.shadow.camera.right = keyLight.shadow.camera.top = 2.25;
  keyLight.shadow.bias = -0.00022;
  keyLight.shadow.normalBias = 0.031;
  const fill = new THREE.DirectionalLight(0xe7ecff, 0.34);
  fill.position.set(4, 1.2, 2.5);
  const rim = new THREE.DirectionalLight(0xffffff, 0.90);
  rim.position.set(1.5, 3, -4);
  const shadow = softShadow();
  scene.add(keyLight, fill, rim, shadow);

  const printMaterial = new THREE.MeshStandardMaterial({
    transparent: true, alphaTest: 0.002, depthWrite: false, roughness: 0.86,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
  });
  const guideMaterial = new THREE.MeshBasicMaterial({
    color: '#f59e0b', transparent: true, opacity: 0.17, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
  });
  let model: MockupModel | undefined;
  let print: THREE.Mesh | undefined;
  let guide: THREE.Mesh | undefined;
  let artAspect = 1;
  let scale = 1;
  let position = centeredArtwork;
  let placementPreview: Placement | undefined;
  const span = new THREE.Vector2(0.58, 0.58);
  const center = new THREE.Vector2(0.5, 0.5);
  const raycaster = new THREE.Raycaster();
  const cursor = new THREE.Vector2();
  let drag: {pointer: number; offset: THREE.Vector2} | undefined;
  let needsRender = true;
  const requestRender = () => {needsRender = true;};
  controls.addEventListener('change', requestRender);
  canvas.addEventListener('webglcontextrestored', requestRender);

  function updatePrint() {
    const texture = printMaterial.map;
    if (print) print.visible = Boolean(texture);
    if (guide) guide.visible = Boolean(texture && placementPreview);
    if (texture && model) {
      const aspect = artAspect / model.printAspect;
      const size = Math.min(0.95, 0.58 * scale);
      span.set(size * Math.min(1, aspect), size * Math.min(1, 1 / aspect));
      const next = placementPreview ?? position;
      center.set(0.5 + (1 - span.x) * next.x / 2, 0.5 + (1 - span.y) * next.y / 2);
      texture.repeat.set(1 / span.x, 1 / span.y);
      texture.offset.set(0.5 - center.x / span.x, 0.5 - center.y / span.y);
    }
    requestRender();
  }

  function pointOnPrint(event: PointerEvent) {
    if (!print?.visible || !model) return undefined;
    const rect = canvas.getBoundingClientRect();
    cursor.set((event.clientX - rect.left) / rect.width * 2 - 1, 1 - (event.clientY - rect.top) / rect.height * 2);
    raycaster.setFromCamera(cursor, camera);
    return raycaster.intersectObject(print, false)[0]?.uv;
  }

  function hitsArtwork(uv: THREE.Vector2) {
    return Math.abs(uv.x - center.x) <= span.x / 2 && Math.abs(uv.y - center.y) <= span.y / 2;
  }

  function coordinatesAt(uv: THREE.Vector2, offsetX = 0, offsetY = 0): Placement {
    return {
      x: THREE.MathUtils.clamp(2 * (uv.x - offsetX - 0.5) / (1 - span.x), -1, 1),
      y: THREE.MathUtils.clamp(2 * (uv.y - offsetY - 0.5) / (1 - span.y), -1, 1),
    };
  }

  function finishPlacing(commit: boolean) {
    if (!placementPreview) return;
    if (commit) position = placementPreview;
    placementPreview = undefined;
    const pointer = drag?.pointer;
    drag = undefined;
    if (pointer !== undefined && canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
    controls.enabled = true;
    host.dataset.artCursor = '';
    onPlacingChange(false);
    updatePrint();
    if (commit) onPositionChange(position);
  }

  function beginDrag(event: PointerEvent) {
    if (!event.isPrimary || event.button !== 0) return;
    const uv = pointOnPrint(event);
    if (!uv || (!placementPreview && !hitsArtwork(uv))) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const offset = placementPreview ? new THREE.Vector2() : uv.clone().sub(center);
    drag = {pointer: event.pointerId, offset};
    controls.enabled = false;
    controls.autoRotate = false;
    stopSpin();
    host.dataset.artCursor = 'dragging';
    canvas.setPointerCapture(event.pointerId);
    if (placementPreview) {
      placementPreview = coordinatesAt(uv);
      updatePrint();
    }
  }

  function movePointer(event: PointerEvent) {
    if (!event.isPrimary) return;
    const uv = pointOnPrint(event);
    if (placementPreview) {
      host.dataset.artCursor = uv ? (drag ? 'dragging' : 'place') : 'outside';
      if (uv) {
        placementPreview = coordinatesAt(uv);
        updatePrint();
      }
      return;
    }
    if (!drag) {
      host.dataset.artCursor = uv && hitsArtwork(uv) ? 'move' : '';
      return;
    }
    if (!uv || event.pointerId !== drag.pointer) return;
    position = coordinatesAt(uv, drag.offset.x, drag.offset.y);
    updatePrint();
  }

  function endDrag(event: PointerEvent) {
    if (event.pointerId !== drag?.pointer) return;
    drag = undefined;
    controls.enabled = !placementPreview;
    host.dataset.artCursor = '';
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (placementPreview) {
      if (event.type === 'pointerup' && pointOnPrint(event)) finishPlacing(true);
    } else {
      onPositionChange(position);
    }
  }
  canvas.addEventListener('pointerdown', beginDrag, true);
  canvas.addEventListener('pointermove', movePointer);
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('lostpointercapture', endDrag);

  const observer = new ResizeObserver(() => {
    const {clientWidth: width, clientHeight: height} = host;
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.zoom = Math.min(1, camera.aspect * 1.10);
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    requestRender();
  });
  observer.observe(host);
  let visible = true;
  const intersection = new IntersectionObserver(entries => {visible = entries[0].isIntersecting;});
  intersection.observe(host);
  let lastFrame = 0;
  renderer.setAnimationLoop((time: number) => {
    const delta = Math.min(0.05, (time - (lastFrame || time)) / 1000);
    lastFrame = time;
    if (!visible) return;
    if (!drag && !placementPreview) controls.update(delta);
    if (needsRender) {
      renderer.render(scene, camera);
      needsRender = false;
    }
  });

  return {
    controls,
    startPlacing() {
      if (!print?.visible || placementPreview || drag) return;
      placementPreview = position;
      controls.autoRotate = false;
      stopSpin();
      controls.reset();
      controls.enabled = false;
      onPlacingChange(true);
      updatePrint();
    },
    finishPlacing,
    turn(degrees: number) {
      const offset = camera.position.clone().sub(controls.target);
      offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad(degrees));
      camera.position.copy(controls.target).add(offset);
      controls.update();
    },
    setProduct(kind: MockupKind, name?: string) {
      finishPlacing(false);
      if (model) {
        guide?.removeFromParent();
        print?.removeFromParent();
        print?.geometry.dispose();
        model.group.removeFromParent();
        disposeModel(model);
      }
      model = createMockupModel(kind, name);
      model.group.position.set(0, 0, 0);
      const bounds = new THREE.Box3().setFromObject(model.group);
      const size = bounds.getSize(new THREE.Vector3());
      const factor = 2.67 / Math.max(size.y, size.x * 0.92);
      model.group.scale.setScalar(factor);
      model.group.position.copy(bounds.getCenter(new THREE.Vector3())).multiplyScalar(-factor);
      print = new THREE.Mesh(model.print, printMaterial);
      print.renderOrder = 2;
      print.receiveShadow = true;
      guide = new THREE.Mesh(model.print, guideMaterial);
      guide.renderOrder = 1;
      model.group.add(guide, print);
      scene.add(model.group);
      shadow.position.y = -size.y * factor / 2 - 0.20;
      shadow.scale.set(Math.max(2.25, size.x * factor * 1.4), Math.max(1.25, size.z * factor * 1.7), 1);
      const drinkware = kind === 'mug' || kind === 'tumbler';
      camera.position.set(drinkware || kind === 'cap' ? 1.12 : 0.59, drinkware || kind === 'cap' ? 1.20 : 0.52, 5.24);
      controls.target.set(0, -0.04, 0);
      controls.update();
      controls.saveState();
      updatePrint();
    },
    setColor(color: string) {
      model?.surface.color.set(color);
      model?.trim?.color.set(color).multiplyScalar(0.88);
      requestRender();
    },
    setLayout(nextScale: number, nextPosition: Placement) {
      scale = nextScale;
      position = nextPosition;
      updatePrint();
    },
    setArt(prepared: ReturnType<typeof prepareArtwork>) {
      if (!prepared) finishPlacing(false);
      printMaterial.map?.dispose();
      if (prepared) {
        const texture = new THREE.CanvasTexture(prepared.canvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        // The clear outer pixels keep the surface transparent outside the decal.
        texture.generateMipmaps = false;
        texture.minFilter = THREE.LinearFilter;
        printMaterial.map = texture;
        artAspect = prepared.canvas.width / prepared.canvas.height;
      } else {
        printMaterial.map = null;
      }
      printMaterial.needsUpdate = true;
      updatePrint();
    },
    dispose() {
      intersection.disconnect();
      observer.disconnect();
      controls.removeEventListener('change', requestRender);
      canvas.removeEventListener('webglcontextrestored', requestRender);
      canvas.removeEventListener('pointerdown', beginDrag, true);
      canvas.removeEventListener('pointermove', movePointer);
      canvas.removeEventListener('pointerup', endDrag);
      canvas.removeEventListener('pointercancel', endDrag);
      canvas.removeEventListener('lostpointercapture', endDrag);
      controls.dispose();
      renderer.setAnimationLoop(null);
      guide?.removeFromParent();
      print?.removeFromParent();
      print?.geometry.dispose();
      if (model) disposeModel(model);
      printMaterial.map?.dispose();
      printMaterial.dispose();
      guideMaterial.dispose();
      shadow.geometry.dispose();
      shadow.material.map?.dispose();
      shadow.material.dispose();
      keyLight.shadow.dispose();
      renderer.dispose();
      canvas.remove();
    },
  };
}

export default function MockupViewer({kind, color, productName, artworkUrl, removeBackground, scale, position, onPositionChange}: ViewerProps) {
  const host = useRef<HTMLDivElement>(null);
  const viewer = useRef<ReturnType<typeof makeViewer> | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [artState, setArtState] = useState<'none' | 'ready' | 'cleaned' | 'error'>('none');
  const [spinning, setSpinning] = useState(false);
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    if (!host.current) return;
    try {
      viewer.current = makeViewer(host.current, onPositionChange, () => setSpinning(false), setPlacing);
    } catch {
      setUnavailable(true);
    }
    return () => {
      viewer.current?.dispose();
      viewer.current = null;
    };
  }, [onPositionChange]);

  useEffect(() => {viewer.current?.setProduct(kind, productName);}, [kind, productName]);
  useEffect(() => {viewer.current?.setColor(color);}, [color, kind, productName]);
  useEffect(() => {viewer.current?.setLayout(scale, position);}, [scale, position]);
  useEffect(() => {
    if (viewer.current) viewer.current.controls.autoRotate = spinning;
  }, [spinning]);
  useEffect(() => {
    const current = viewer.current;
    if (!current) return;
    setArtState('none');
    current.setArt(null);
    if (!artworkUrl) return;
    const image = new Image();
    if (new URL(artworkUrl, window.location.href).origin !== window.location.origin &&
        !artworkUrl.startsWith('blob:')) image.crossOrigin = 'use-credentials';
    image.onload = () => {
      try {
        const prepared = prepareArtwork(image, removeBackground);
        current.setArt(prepared);
        setArtState(prepared ? prepared.removed ? 'cleaned' : 'ready' : 'error');
      } catch {
        setArtState('error');
      }
    };
    image.onerror = () => setArtState('error');
    image.src = artworkUrl;
    return () => {image.onload = image.onerror = null;};
  }, [artworkUrl, removeBackground]);

  const hasPrint = artState === 'ready' || artState === 'cleaned';
  return <section className="mockup-viewer" aria-label="Xem sản phẩm 3D" onKeyDown={event => {
    if (placing && event.key === 'Escape') {
      event.stopPropagation();
      viewer.current?.finishPlacing(false);
    }
  }}>
    <div className="mockup-stage">
      <div className="mockup-canvas" ref={host} />
      <div className="mockup-product-label"><strong>{productName || mockupLabels[kind]}</strong></div>
      {unavailable && <div className="mockup-fallback" role="status">
        {artworkUrl && <img src={artworkUrl} alt="Ảnh thiết kế" />}
        <p>Trình duyệt hoặc thiết bị này chưa hỗ trợ xem 3D.</p>
      </div>}
    </div>
    {!unavailable && <div className="mockup-toolbar">
      <button type="button" className="mockup-place" aria-pressed={placing} disabled={!hasPrint}
        title={hasPrint ? undefined : 'Tải ảnh để đặt vị trí'}
        onClick={() => placing ? viewer.current?.finishPlacing(true) : viewer.current?.startPlacing()}>
        {placing ? <Check size={16} /> : <Move size={16} />} {placing ? 'Xong' : 'Đặt vị trí ảnh'}
      </button>
      <div className="mockup-rotation" role="group" aria-label="Xoay mô hình">
        <button type="button" disabled={placing} aria-label="Xoay sang trái" title="Xoay sang trái" onClick={() => viewer.current?.turn(-45)}><RotateCcw size={17} /></button>
        <button type="button" disabled={placing} aria-label="Xoay sang phải" title="Xoay sang phải" onClick={() => viewer.current?.turn(45)}><RotateCw size={17} /></button>
        <button type="button" disabled={placing} aria-label="Về góc nhìn ban đầu" title="Về góc nhìn ban đầu" onClick={() => {setSpinning(false); viewer.current?.controls.reset();}}><Scan size={17} /></button>
        <button type="button" disabled={placing} aria-label={spinning ? 'Dừng tự xoay' : 'Tự xoay'} aria-pressed={spinning}
          title={spinning ? 'Dừng tự xoay' : 'Tự xoay'} onClick={() => setSpinning(value => !value)}>
          {spinning ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>
    </div>}
    <div className="mockup-caption">
      {!unavailable && <p className="mockup-drag-hint" aria-live="polite"><MousePointer2 size={14} />
        {placing ? 'Di chuột trong vùng tô màu rồi bấm để đặt. Bạn cũng có thể chạm trực tiếp.'
          : hasPrint ? 'Kéo hình in để di chuyển. Kéo phần còn lại để xoay.' : 'Kéo để xoay mẫu.'}
      </p>}
      {artState === 'error' && <p role="alert">Ảnh thiết kế trống hoặc chưa tải được.</p>}
      {artState === 'cleaned' && <p role="status">Đã bỏ nền trắng hoặc caro trong bản xem thử.</p>}
      <p>{kind === 'other' ? 'Sản phẩm này dùng phôi minh họa.' : 'Hình dáng mô phỏng theo nhóm sản phẩm.'} Vùng in thực tế theo mẫu của xưởng.</p>
    </div>
  </section>;
}
