'use client';

import dynamic from 'next/dynamic';
import {useEffect, useRef, useState} from 'react';
import {Box, ChevronLeft, ChevronRight, ImagePlus, Link2, Search, X} from 'lucide-react';
import {api} from '@/lib/api';
import {designFormats, designPreviewUrl, uploadDesign, type DesignAsset} from '@/lib/designs';
import {centeredArtwork, mockupLabels, type MockupKind, type Placement} from '@/lib/mockup-types';

const MockupViewer = dynamic(() => import('./MockupViewer'), {
  ssr: false,
  loading: () => <div className="mockup-stage mockup-fallback" role="status">Đang mở chế độ xem 3D…</div>,
});

type StudioProps = {
  assets: DesignAsset[];
  busy: boolean;
  refreshLists: () => Promise<void>;
  run: (action: () => Promise<void>) => Promise<void>;
  onNotice: (message: string) => void;
  initialAsset?: DesignAsset;
  draftLink?: {index: number; productId: string; color?: string};
  draftLines: string[];
  onAttach: (asset: DesignAsset, index: number) => void;
  onReturn: () => void;
};
type CatalogProduct = {id: string; name: string; kind: MockupKind};
type CatalogPage = {results: CatalogProduct[]; has_more: boolean; catalog_ready: boolean};
type CatalogKind = {kind: MockupKind; count: number};
type CatalogColor = {name: string; hex: string | null};
type ColorOption = {key: string; name: string; hex: string; exact: boolean};

const PAGE_SIZE = 30;
const NEUTRAL = '#f9f8f5';
const namedColors: Record<string, string> = {
  white: '#ffffff', black: '#161616', navy: '#182339', red: '#c72434',
  'royal blue': '#214894', 'light blue': '#a0c6de', pink: '#efb1c6', 'light pink': '#f4c4d2',
  grey: '#898c91', gray: '#898c91', 'sport grey': '#a3a4a7', 'heather grey': '#a3a4a7',
  'forest green': '#254334', maroon: '#6d252f', yellow: '#f3ce42', natural: '#e8dfca',
};

function colorOptions(colors: CatalogColor[]) {
  const options = new Map<string, ColorOption>();
  const exactNames = new Set<string>();
  for (const color of colors) {
    const name = color.name.trim().toLowerCase();
    const rawHex = color.hex?.trim().replace(/^#/, '').toLowerCase() ?? '';
    const exact = /^(?:[a-f0-9]{3}|[a-f0-9]{6})$/.test(rawHex);
    const hex = exact ? '#' + (rawHex.length === 3 ? rawHex.replace(/./g, digit => digit.repeat(2)) : rawHex)
      : Object.prototype.hasOwnProperty.call(namedColors, name) ? namedColors[name] : NEUTRAL;
    const key = name + ':' + hex;
    if (exact) exactNames.add(name);
    if (!options.has(key) || exact) options.set(key, {key, name: color.name, hex, exact});
  }
  return Array.from(options.values()).filter(color => color.exact || !exactNames.has(color.name.trim().toLowerCase()));
}

export default function DesignStudio({
  assets, busy, refreshLists, run, onNotice, initialAsset, draftLink, draftLines, onAttach, onReturn,
}: StudioProps) {
  const [kind, setKind] = useState<MockupKind | 'all'>(draftLink ? 'all' : 't-shirt');
  const [kinds, setKinds] = useState<CatalogKind[]>([]);
  const [query, setQuery] = useState(draftLink?.productId ?? '');
  const [page, setPage] = useState(0);
  const [retry, setRetry] = useState(0);
  const [catalog, setCatalog] = useState<{key: string; data?: CatalogPage; error?: string}>();
  const [productId, setProductId] = useState(draftLink?.productId ?? '');
  const [colors, setColors] = useState<{id: string; options?: ColorOption[]; error?: boolean}>();
  const [colorKey, setColorKey] = useState('');
  const [artwork, setArtwork] = useState(initialAsset);
  const [scale, setScale] = useState(100);
  const [position, setPosition] = useState<Placement>(centeredArtwork);
  const [removeBackground, setRemoveBackground] = useState(true);
  const [previousAsset, setPreviousAsset] = useState('');
  const [assetQuery, setAssetQuery] = useState('');
  const [editor, setEditor] = useState<'products' | 'artwork'>(draftLink ? 'artwork' : 'products');
  const [targetLine, setTargetLine] = useState(draftLink?.index ?? 0);
  const top = useRef<HTMLDivElement>(null);
  const artworkUrl = artwork ? designPreviewUrl(artwork.id) : undefined;
  const catalogKey = JSON.stringify([kind, query.trim(), page, retry]);
  const currentCatalog = catalog?.key === catalogKey ? catalog : undefined;
  const products = currentCatalog?.data?.results ?? [];
  const product = products.find(item => item.id === productId);
  const currentColors = colors?.id === product?.id ? colors : undefined;
  const color = currentColors?.options?.find(item => item.key === colorKey);
  const modelKind = product?.kind ?? (kind === 'all' ? 't-shirt' : kind);

  useEffect(() => {
    const abort = new AbortController();
    void api<{results: CatalogKind[]}>('/mockups/kinds', 'GET', undefined, abort.signal).then(data => {
      if (!abort.signal.aborted) setKinds(data.results);
    }).catch(() => {});
    return () => abort.abort();
  }, [retry, catalog?.data?.catalog_ready]);

  useEffect(() => {
    const abort = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({kind, q: query.trim(), offset: String(page * PAGE_SIZE)});
        const data = await api<CatalogPage>('/mockups/products?' + params, 'GET', undefined, abort.signal);
        if (abort.signal.aborted) return;
        setCatalog({key: catalogKey, data});
        setProductId(id => data.results.some(item => item.id === id) ? id : data.results[0]?.id ?? '');
      } catch (error) {
        if (!abort.signal.aborted) setCatalog({key: catalogKey, error: error instanceof Error ? error.message : 'Chưa tải được catalog.'});
      }
    }, 200);
    return () => {window.clearTimeout(timer); abort.abort();};
  }, [catalogKey, kind, page, query]);

  useEffect(() => {
    const id = product?.id;
    if (!id) return;
    const abort = new AbortController();
    const params = new URLSearchParams({product_id: id});
    void api<{colors: CatalogColor[]}>('/mockups/colors?' + params, 'GET', undefined, abort.signal).then(data => {
      if (abort.signal.aborted) return;
      const options = colorOptions(data.colors);
      setColors({id, options});
      const initialColor = id === draftLink?.productId ? draftLink.color?.trim().toLowerCase() : undefined;
      setColorKey((options.find(option => option.name.trim().toLowerCase() === initialColor) ?? options[0])?.key ?? '');
    }).catch(() => {if (!abort.signal.aborted) setColors({id, error: true});});
    return () => abort.abort();
  }, [product?.id, retry, draftLink?.productId, draftLink?.color]);

  function useAsset(asset: DesignAsset) {
    if (artwork?.id !== asset.id) setPosition(centeredArtwork);
    setArtwork(asset);
    setEditor('artwork');
  }

  function upload(file: File) {
    void run(async () => {
      const asset = await uploadDesign(file, previousAsset);
      useAsset(asset);
      await refreshLists();
      onNotice(draftLines.length ? 'Đã lưu ảnh. Bấm Gắn ảnh vào đơn nháp để dùng ảnh cho SKU.' : 'Đã lưu ảnh vào thư viện.');
    });
  }

  function changeKind(next: MockupKind | 'all') {
    if (next === kind) return;
    setKind(next);
    setQuery('');
    setPage(0);
    setProductId('');
  }

  const catalogMessage = currentCatalog?.error || (!currentCatalog ? 'Đang tải catalog…'
    : !currentCatalog.data?.catalog_ready ? 'Catalog đang đồng bộ. Bạn có thể tải lại để kiểm tra.'
    : products.length ? '' : 'Chưa tìm thấy sản phẩm phù hợp.');
  const filteredAssets = assets.filter(item => (item.name + ' ' + item.tags).toLowerCase().includes(assetQuery.trim().toLowerCase()));

  return <div className="design-studio" ref={top}>
    <div className="studio-heading">
      <span className="studio-icon"><Box size={23} /></span>
      <h1>Thiết kế trên mẫu 3D</h1>
    </div>
    {draftLines.length > 0 && <div className="studio-draft-link">
      <div>
        <label>Gắn ảnh vào dòng SKU
          <select value={draftLines[targetLine] ? targetLine : ''} onChange={event => setTargetLine(Number(event.currentTarget.value))}
            disabled={busy}>
            <option value="" disabled>Chọn dòng SKU</option>
            {draftLines.map((sku, index) => <option key={index} value={index}>Dòng {index + 1} · {sku}</option>)}
          </select>
        </label>
        <p className="muted">{artwork ? 'Đơn nháp dùng ảnh gốc. Vị trí trên mẫu 3D để xem thử.'
          : 'Tải ảnh lên hoặc chọn một ảnh đã lưu bên dưới.'}</p>
      </div>
      <div className="studio-draft-actions">
        <button type="button" className="primary" disabled={busy || !artwork || !draftLines[targetLine]}
          onClick={() => {if (artwork) onAttach(artwork, targetLine);}}>Gắn ảnh vào đơn nháp</button>
        <button type="button" disabled={busy} onClick={onReturn}>Về đơn nháp</button>
      </div>
    </div>}
    <div className="studio-grid">
      <div className="studio-controls">
        <div className="studio-editor-switch" role="group" aria-label="Bảng chỉnh thiết kế">
          <button type="button" aria-pressed={editor === 'products'} onClick={() => setEditor('products')}>
            <Box size={16} /> Sản phẩm
          </button>
          <button type="button" aria-pressed={editor === 'artwork'} onClick={() => setEditor('artwork')}>
            <ImagePlus size={16} /> Ảnh và vị trí
          </button>
        </div>
        <div className="studio-section" hidden={editor !== 'products'}>
          <label className="studio-field">Loại sản phẩm
            <select value={kind} onChange={event => changeKind(event.target.value as MockupKind | 'all')}>
              <option value="all">Tất cả sản phẩm</option>
              {(Object.keys(mockupLabels) as MockupKind[]).map(key => {
                const count = kinds.find(item => item.kind === key)?.count;
                if (kinds.length && !count && key !== kind) return null;
                return <option key={key} value={key}>{mockupLabels[key]}{count ? ' (' + count + ')' : ''}</option>;
              })}
            </select>
          </label>
          <label className="studio-field">Tìm trong catalog
            <span className="studio-search"><Search size={16} /><input value={query} maxLength={100}
              onChange={event => {setQuery(event.target.value); setPage(0);}} placeholder="Tên hoặc mã sản phẩm" /></span>
          </label>
          {products.length > 0 && <label className="studio-field">Mẫu sản phẩm
            <select value={product?.id ?? ''} onChange={event => setProductId(event.target.value)}>
              {products.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>}
          {(page > 0 || currentCatalog?.data?.has_more) && <div className="studio-pages">
            <button type="button" disabled={page === 0 || !currentCatalog} onClick={() => setPage(value => value - 1)}><ChevronLeft size={15} /> Trước</button>
            <span>Trang {page + 1}</span>
            <button type="button" disabled={!currentCatalog?.data?.has_more} onClick={() => setPage(value => value + 1)}>Sau <ChevronRight size={15} /></button>
          </div>}
          {catalogMessage && <p className="studio-status" role="status">{catalogMessage}
            {currentCatalog && (!currentCatalog.data?.catalog_ready || currentCatalog.error) &&
              <button type="button" onClick={() => setRetry(value => value + 1)}>Tải lại</button>}
          </p>}
          {product && <div className="studio-colors">
            <h3>Màu <span>{color?.name}</span></h3>
            {currentColors?.options?.length ? <>
              <div className="studio-swatches" role="group" aria-label="Chọn màu sản phẩm">
                {currentColors.options.map(option => <button type="button" key={option.key}
                  aria-label={option.name + ' ' + option.hex} title={option.name + ' · ' + option.hex}
                  aria-pressed={colorKey === option.key} onClick={() => setColorKey(option.key)}>
                  <span style={{backgroundColor: option.hex}} />
                </button>)}
              </div>
              {color && !color.exact && <p className="studio-status">Catalog chưa có mã màu. Màu hiển thị là màu minh họa.</p>}
            </> : <p className="studio-status" role="status">{currentColors?.error ? 'Chưa tải được màu. Thử chọn lại mẫu.'
              : currentColors ? 'Mẫu này chưa có màu trong catalog.' : 'Đang tải màu…'}</p>}
          </div>}
        </div>
        <div className="studio-section" hidden={editor !== 'artwork'}>
          {artwork && <div className="studio-artwork">
            <img src={artworkUrl} alt="" />
            <span title={artwork.name}>{artwork.name}</span>
            <button type="button" disabled={busy} onClick={() => setArtwork(undefined)} aria-label="Gỡ ảnh khỏi mẫu"><X size={16} /></button>
          </div>}
          <label className="studio-upload">
            <ImagePlus size={22} />
            <span><strong>{artwork ? 'Đổi ảnh thiết kế' : 'Tải ảnh lên'}</strong><small>PNG, JPEG hoặc WebP · tối đa 25 MB</small></span>
            <input type="file" aria-label="Tải ảnh thiết kế" accept={designFormats} disabled={busy}
              onChange={event => {const file = event.target.files?.[0]; event.target.value = ''; if (file) upload(file);}} />
          </label>
          {artwork && <>
            <label className="studio-background">
              <input type="checkbox" checked={removeBackground} onChange={event => setRemoveBackground(event.target.checked)} />
              <span>Bỏ nền trắng hoặc caro khi xem thử</span>
            </label>
            <label className="studio-field studio-scale">Kích thước ảnh <span>{scale}%</span>
              <input type="range" aria-label="Kích thước ảnh" min={25} max={155} value={scale} onChange={event => setScale(Number(event.target.value))} />
            </label>
            <details className="studio-placement">
              <summary>Căn chỉnh bằng thanh trượt</summary>
              <label className="studio-field studio-scale">Ngang <span>{Math.round(position.x * 100)}%</span>
                <input type="range" aria-label="Vị trí ngang" min={-100} max={100} value={Math.round(position.x * 100)}
                  onChange={event => setPosition(value => ({...value, x: Number(event.target.value) / 100}))} />
              </label>
              <label className="studio-field studio-scale">Dọc <span>{Math.round(position.y * 100)}%</span>
                <input type="range" aria-label="Vị trí dọc" min={-100} max={100} value={Math.round(position.y * 100)}
                  onChange={event => setPosition(value => ({...value, y: Number(event.target.value) / 100}))} />
              </label>
              <button type="button" onClick={() => setPosition(centeredArtwork)}>Đưa ảnh về giữa</button>
            </details>
          </>}
          <details className="studio-import">
            <summary><Link2 size={16} /> Nhập URL hoặc thay phiên bản</summary>
            <label className="studio-field">Phiên bản mới của
              <select value={previousAsset} onChange={event => setPreviousAsset(event.target.value)}>
                <option value="">Thiết kế mới</option>
                {assets.map(asset => <option key={asset.id} value={asset.id}>{asset.name} · v{asset.file_version}</option>)}
              </select>
            </label>
            <form onSubmit={event => {
              event.preventDefault();
              const values = Object.fromEntries(new FormData(event.currentTarget));
              void run(async () => {
                const asset = await api<DesignAsset>('/assets/import', 'POST', {...values, previous_id: previousAsset});
                useAsset(asset);
                await refreshLists();
                onNotice('Đã lưu file gốc vào thư viện.');
              });
            }}>
              <label className="studio-field">Tên thiết kế<input name="name" required /></label>
              <label className="studio-field">URL ảnh công khai<input name="url" type="url" required placeholder="https://…/design.png" /></label>
              <button type="submit" disabled={busy}>Nhập từ URL</button>
            </form>
          </details>
        </div>
      </div>
      <div className="studio-preview">
        <MockupViewer kind={modelKind} color={color?.hex ?? NEUTRAL} productName={product?.name}
          artworkUrl={artworkUrl} scale={scale / 100} position={position} onPositionChange={setPosition}
          removeBackground={removeBackground} />
      </div>
    </div>
    <section className="studio-library">
      <div className="studio-library-heading">
        <h2>Thư viện thiết kế</h2>
        <label className="studio-field">Tìm theo tên / phân loại
          <input value={assetQuery} onChange={event => setAssetQuery(event.target.value)} />
        </label>
      </div>
      <div className="asset-grid">
        {filteredAssets.map(asset => <article className="asset-card" key={asset.id}>
          <img src={designPreviewUrl(asset.id)} alt={asset.name + ' · v' + asset.file_version} loading="lazy" />
          <h3>{asset.name} · v{asset.file_version}</h3>
          <p>{asset.validation.width} × {asset.validation.height} px</p>
          <p className="muted">{asset.validation.message}</p>
          <button type="button" disabled={busy} aria-pressed={artwork?.id === asset.id} onClick={() => {
            useAsset(asset);
            top.current?.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
          }}>Xem trên sản phẩm</button>
          <details className="studio-asset-edit">
            <summary>Đổi tên và phân loại</summary>
            <form onSubmit={event => {
              event.preventDefault();
              const data = Object.fromEntries(new FormData(event.currentTarget));
              void run(async () => {
                const saved = await api<DesignAsset>('/assets/' + encodeURIComponent(asset.id), 'PATCH', {version: asset.version, ...data});
                if (artwork?.id === asset.id) useAsset(saved);
                await refreshLists();
              });
            }}>
              <label>Tên<input name="name" defaultValue={asset.name} required /></label>
              <label>Phân loại<input name="tags" defaultValue={asset.tags} /></label>
              <button type="submit" disabled={busy}>Lưu tên và phân loại</button>
            </form>
          </details>
        </article>)}
      </div>
      {!filteredAssets.length && <p className="empty-state">
        {assets.length ? 'Chưa tìm thấy thiết kế phù hợp.' : 'Thư viện chưa có file. Tải ảnh hoặc nhập từ URL để bắt đầu.'}
      </p>}
    </section>
  </div>;
}
