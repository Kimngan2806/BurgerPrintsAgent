'use client';

import {useEffect, useRef, useState} from 'react';
import {MousePointer2, Pause, Play, RotateCcw, RotateCw, Scan} from 'lucide-react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {createMockupModel, type MockupKind, type MockupModel} from '@/lib/mockup-models';

type ViewerProps = {
  kind: MockupKind;
  color: string;
  productName?: string;
  artworkUrl?: string;
  scale: number;
};

function disposeModel(model: MockupModel) {
  model.group.traverse(object => {
    if (object instanceof THREE.Mesh) object.geometry.dispose();
  });
  model.surface.dispose();
  model.trim?.dispose();
}

function artworkTexture(image: HTMLImageElement) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1024;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const scale = 1016 / Math.max(image.naturalWidth, image.naturalHeight);
  const width = image.naturalWidth * scale;
  const height = image.naturalHeight * scale;
  context.drawImage(image, (canvas.width - width) / 2, (canvas.height - height) / 2, width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function makeViewer(host: HTMLDivElement) {
  const renderer = new THREE.WebGLRenderer({alpha: true, antialias: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(37, 1, 0.1, 32);
  camera.position.set(1.45, 1.17, 4.65);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.minPolarAngle = 0.28;
  controls.maxPolarAngle = Math.PI - 0.35;
  controls.autoRotateSpeed = 1.3;
  controls.target.set(0, 0.06, 0);
  controls.update();
  controls.saveState();

  scene.add(new THREE.HemisphereLight(0xffffff, 0xb3bbc6, 2.05));
  const keyLight = new THREE.DirectionalLight(0xfff8ee, 2.0);
  keyLight.position.set(-3, 7, 4);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(768, 768);
  keyLight.shadow.camera.left = keyLight.shadow.camera.bottom = -2.5;
  keyLight.shadow.camera.right = keyLight.shadow.camera.top = 2.5;
  keyLight.shadow.bias = -0.00035;
  const rimLight = new THREE.DirectionalLight(0xe5edff, 1.0);
  rimLight.position.set(3, 3, -3);
  scene.add(keyLight, rimLight);

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(22, 22), new THREE.ShadowMaterial({opacity: 0.12}));
  floor.rotateX(-Math.PI / 2);
  floor.position.y = -1.13;
  floor.receiveShadow = true;
  scene.add(floor);

  const printMaterial = new THREE.MeshStandardMaterial({
    transparent: true, alphaTest: 0.015, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -3, roughness: 0.83,
  });
  let model: MockupModel | undefined;
  let print: THREE.Mesh | undefined;
  let printScale = 1;
  let needsRender = true;
  const requestRender = () => {needsRender = true;};
  controls.addEventListener('change', requestRender);
  renderer.domElement.addEventListener('webglcontextrestored', requestRender);
  function applyPrint() {
    requestRender();
    if (print) {
      print.removeFromParent();
      print.geometry.dispose();
      print = undefined;
    }
    if (!model || !printMaterial.map) return;
    model.group.updateMatrixWorld(true);
    print = new THREE.Mesh(model.createPrint(printScale), printMaterial);
    print.renderOrder = 1;
    model.group.add(print);
  }

  const observer = new ResizeObserver(() => {
    const {clientWidth: width, clientHeight: height} = host;
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.zoom = Math.min(1, camera.aspect * 1.04);
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
    controls.update(delta);
    if (needsRender) {
      renderer.render(scene, camera);
      needsRender = false;
    }
  });

  return {
    controls,
    turn(degrees: number) {
      const offset = camera.position.clone().sub(controls.target);
      offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad(degrees));
      camera.position.copy(controls.target).add(offset);
      controls.update();
    },
    setProduct(kind: MockupKind) {
      if (print) {
        print.removeFromParent();
        print.geometry.dispose();
        print = undefined;
      }
      if (model) {
        model.group.removeFromParent();
        disposeModel(model);
      }
      model = createMockupModel(kind);
      scene.add(model.group);
      controls.reset();
      applyPrint();
    },
    setColor(color: string) {
      model?.surface.color.set(color);
      model?.trim?.color.set(color).multiplyScalar(0.85);
      requestRender();
    },
    setScale(scale: number) {
      printScale = scale;
      applyPrint();
    },
    setArt(texture: THREE.Texture | null) {
      printMaterial.map?.dispose();
      printMaterial.map = texture;
      printMaterial.needsUpdate = true;
      applyPrint();
    },
    dispose() {
      intersection.disconnect();
      observer.disconnect();
      controls.removeEventListener('change', requestRender);
      renderer.domElement.removeEventListener('webglcontextrestored', requestRender);
      controls.dispose();
      renderer.setAnimationLoop(null);
      if (model) disposeModel(model);
      printMaterial.map?.dispose();
      printMaterial.dispose();
      floor.geometry.dispose();
      floor.material.dispose();
      keyLight.shadow.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}

export default function MockupViewer({kind, color, productName, artworkUrl, scale}: ViewerProps) {
  const host = useRef<HTMLDivElement>(null);
  const viewer = useRef<ReturnType<typeof makeViewer> | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [artError, setArtError] = useState(false);
  const [spinning, setSpinning] = useState(false);

  useEffect(() => {
    if (!host.current) return;
    try {
      viewer.current = makeViewer(host.current);
    } catch {
      setUnavailable(true);
    }
    return () => {
      viewer.current?.dispose();
      viewer.current = null;
    };
  }, []);

  useEffect(() => { viewer.current?.setProduct(kind); }, [kind]);
  useEffect(() => { viewer.current?.setColor(color); }, [color, kind]);
  useEffect(() => { viewer.current?.setScale(scale); }, [scale]);
  useEffect(() => {
    if (viewer.current) viewer.current.controls.autoRotate = spinning;
  }, [spinning]);
  useEffect(() => {
    const current = viewer.current;
    if (!current) return;
    current.setArt(null);
    setArtError(false);
    if (!artworkUrl) return;
    const image = new Image();
    if (new URL(artworkUrl, window.location.href).origin !== window.location.origin &&
        !artworkUrl.startsWith('blob:')) image.crossOrigin = 'use-credentials';
    image.onload = () => {
      const texture = artworkTexture(image);
      current.setArt(texture);
      setArtError(!texture);
    };
    image.onerror = () => setArtError(true);
    image.src = artworkUrl;
    return () => { image.onload = image.onerror = null; };
  }, [artworkUrl]);

  return <section className="mockup-viewer" aria-label="Xem sản phẩm 3D">
    <div className="mockup-stage">
      <div className="mockup-canvas" ref={host} />
      <div className="mockup-product-label"><strong>{productName || (kind === 'mug' ? 'Mẫu cốc' : 'Mẫu áo thun')}</strong></div>
      {unavailable && <div className="mockup-fallback" role="status">
        {artworkUrl && <img src={artworkUrl} alt="Ảnh thiết kế" />}
        <p>Trình duyệt hoặc thiết bị này chưa hỗ trợ xem 3D.</p>
      </div>}
      {!unavailable && <div className="mockup-rotation">
        <button type="button" aria-label="Xoay sang trái" title="Xoay sang trái" onClick={() => viewer.current?.turn(-45)}><RotateCcw size={17} /></button>
        <button type="button" aria-label="Xoay sang phải" title="Xoay sang phải" onClick={() => viewer.current?.turn(45)}><RotateCw size={17} /></button>
        <button type="button" aria-label="Về góc nhìn ban đầu" title="Về góc nhìn ban đầu" onClick={() => {setSpinning(false); viewer.current?.controls.reset();}}><Scan size={17} /></button>
        <button type="button" aria-label={spinning ? 'Dừng tự xoay' : 'Tự xoay'} aria-pressed={spinning}
          title={spinning ? 'Dừng tự xoay' : 'Tự xoay'} onClick={() => setSpinning(value => !value)}>
          {spinning ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>}
      {!unavailable && <p className="mockup-drag-hint"><MousePointer2 size={14} /> Kéo để xoay</p>}
    </div>
    <div className="mockup-caption">
      {artError && <p role="alert">Ảnh thiết kế chưa tải được. Bạn có thể chọn lại ảnh hoặc tải lên bản mới.</p>}
      <p>Mô phỏng hình dáng và vị trí ảnh. Vùng in thực tế theo mẫu của xưởng.</p>
    </div>
  </section>;
}
