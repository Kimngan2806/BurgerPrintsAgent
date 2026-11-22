export const mockupLabels = {
  't-shirt': 'Áo thun', mug: 'Cốc', hoodie: 'Áo hoodie', sweatshirt: 'Áo nỉ',
  'long-sleeve': 'Áo dài tay', polo: 'Áo polo', 'tank-top': 'Áo ba lỗ', onesie: 'Áo liền thân em bé',
  dress: 'Váy', bottoms: 'Quần và chân váy', cap: 'Mũ', bag: 'Túi và ba lô',
  tumbler: 'Ly, bình và lọ', 'wall-art': 'Tranh, poster và biển', textile: 'Chăn, khăn, thảm và cờ',
  pillow: 'Gối', ornament: 'Móc khóa và đồ trang trí', sticker: 'Nhãn dán',
  'phone-case': 'Ốp điện thoại', card: 'Thiệp, sổ và tranh ghép',
  shoes: 'Giày', accessory: 'Phụ kiện', other: 'Sản phẩm khác',
} as const;

export type MockupKind = keyof typeof mockupLabels;
export type Placement = {x: number; y: number};
export const centeredArtwork: Placement = {x: 0, y: 0};
