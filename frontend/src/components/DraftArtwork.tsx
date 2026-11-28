'use client';

import {useState} from 'react';
import {ImagePlus} from 'lucide-react';
import {designFormats, designPreviewUrl, type DesignAsset} from '@/lib/designs';

type Props = {
  id: string;
  assets: DesignAsset[];
  disabled: boolean;
  onSelect: (id: string) => void;
  onUpload: (file: File) => void;
  onImport: (url: string) => void;
  onPreview: () => void;
};

function AttachedImage({asset}: {asset: DesignAsset}) {
  const [unavailable, setUnavailable] = useState(false);
  return unavailable ? <p className="draft-file-status">Tệp “{asset.name}” không mở được. Tải ảnh lên lại để duyệt đơn.</p> : <>
    <img className="line-preview" src={designPreviewUrl(asset.id)} alt="Ảnh mặt trước đã gắn"
      onError={() => setUnavailable(true)} />
    <p className="draft-file-status"><strong>Ảnh đã gắn</strong> · {asset.name}</p>
  </>;
}

export default function DraftArtwork({id, assets, disabled, onSelect, onUpload, onImport, onPreview}: Props) {
  const asset = assets.find(item => item.id === id);
  return <div className="draft-artwork">
    <h3>Ảnh in mặt trước</h3>
    {asset ? <AttachedImage key={asset.id} asset={asset} />
      : <p className="draft-file-status">{id ? 'Tệp đã chọn không có trong thư viện. Chọn hoặc tải ảnh lại.'
        : 'Chưa gắn ảnh cho SKU này.'}</p>}
    <label className="draft-file-upload"><ImagePlus size={17} />
      <span>{asset ? 'Tải ảnh thay thế' : 'Tải ảnh lên và gắn vào SKU'}</span>
      <input type="file" aria-label={asset ? 'Tải ảnh thay thế' : 'Tải ảnh lên và gắn vào SKU'}
        accept={designFormats} disabled={disabled} onChange={event => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = '';
          if (file) onUpload(file);
        }} />
    </label>
    <small className="muted">PNG, JPEG hoặc WebP · tối đa 25 MB</small>
    {assets.length > 0 && <label>Hoặc chọn ảnh đã lưu
      <select value={asset?.id ?? ''} disabled={disabled} onChange={event => onSelect(event.currentTarget.value)}>
        <option value="">Chọn từ thư viện</option>
        {assets.map(item => <option key={item.id} value={item.id}>{item.name} · v{item.file_version}</option>)}
      </select>
    </label>}
    <details>
      <summary>Dùng đường dẫn ảnh</summary>
      <form className="sku-add" onSubmit={event => {
        event.preventDefault();
        const url = String(new FormData(event.currentTarget).get('design_url') ?? '').trim();
        if (url) onImport(url);
      }}>
        <label>URL ảnh công khai<input name="design_url" type="url" placeholder="https://…/anh.png"
          maxLength={2048} required disabled={disabled} /></label>
        <button disabled={disabled}>Nhập và gắn ảnh</button>
      </form>
    </details>
    <button type="button" disabled={disabled} onClick={onPreview}>Xem SKU và ảnh trên mẫu 3D</button>
  </div>;
}
