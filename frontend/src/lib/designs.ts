import {api, apiUrl} from '@/lib/api';

export type DesignAsset = {
  id: string;
  version: number;
  name: string;
  tags: string;
  file_version: number;
  sha256: string;
  validation: {width: number; height: number; message: string};
};

export const designFormats = 'image/png,image/jpeg,image/webp';
export const designPreviewUrl = (id: string) => apiUrl('/assets/' + encodeURIComponent(id) + '/preview');

export function uploadDesign(file: File, previousId = '') {
  if (file.size > 25 * 1024 * 1024) throw new Error('Ảnh vượt quá giới hạn 25 MB.');
  const data = new FormData();
  data.set('file', file);
  const params = new URLSearchParams({previous_id: previousId});
  return api<DesignAsset>('/assets/upload?' + params, 'POST', data);
}
