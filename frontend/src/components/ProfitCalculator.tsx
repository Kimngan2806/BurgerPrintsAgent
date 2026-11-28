'use client';

import {useEffect, useRef, useState} from 'react';
import {api} from '@/lib/api';

export type ProfitSource = {sku: string; product: string; price?: string | null; quantity: number};
type CostKey = 'production_per_item' | 'shipping_total' | 'platform_total' | 'other_total';
type Profit = {
  revenue: string;
  costs: Partial<Record<CostKey, string>>;
  estimated_profit: string;
  total_known_costs: string;
  profit_per_item: string;
  margin_percent: string | null;
  unknown_costs: CostKey[];
};

const saleFields = [
  {name: 'sale_price', label: 'Giá bán mỗi sản phẩm (USD)', example: '24.99', required: true},
  {name: 'quantity', label: 'Số lượng bán', example: '2', min: 1, max: 10000, step: 1, required: true},
  {name: 'discount_percent', label: 'Giảm giá (%) · tùy chọn', example: '0', max: 100},
];
const costFields = [
  {name: 'production_per_item', label: 'Giá sản xuất mỗi sản phẩm (USD)', example: '8.50'},
  {name: 'shipping_total', label: 'Phí vận chuyển cả đơn (USD)', example: '5.00'},
  {name: 'platform_total', label: 'Phí nền tảng cả đơn (USD)', example: '2.50'},
  {name: 'other_total', label: 'Chi phí khác cả đơn (USD)', example: '1.00'},
] as const;
const costLabels: Record<CostKey, string> = {
  production_per_item: 'Tổng chi phí sản xuất',
  shipping_total: 'Phí vận chuyển',
  platform_total: 'Phí nền tảng',
  other_total: 'Chi phí khác',
};

function money(value: string) {
  const [whole, fraction = '00'] = value.split('.');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ',' + fraction.padEnd(2, '0') + ' USD';
}

type Props = {
  source: ProfitSource | null;
  busy: boolean;
  run: (action: () => Promise<void>) => Promise<void>;
  onReturn: () => void;
  returnLabel: string;
};

export default function ProfitCalculator({source, busy, run, onReturn, returnLabel}: Props) {
  const initialValues: Record<string, string> = source ? {
    quantity: String(source.quantity), production_per_item: source.price ?? '',
  } : {};
  const [values, setValues] = useState(initialValues);
  const [result, setResult] = useState<Profit | null>(null);
  const [example, setExample] = useState(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (result && window.matchMedia('(max-width: 1120px)').matches) resultHeading.current?.scrollIntoView({block: 'start'});
  }, [result]);

  function fields(items: ReadonlyArray<{name: string; label: string; example: string; min?: number;
     max?: number; step?: number; required?: boolean}>) {
    return <div className="profit-fields">{items.map(({name, label, example: placeholder, min = 0, step = 0.01, ...attributes}) =>
      <label key={name}>{label}
        <input {...attributes} name={name} type="number" min={min} step={step} placeholder={placeholder}
          value={values[name] ?? ''} onChange={event => {
            const value = event.currentTarget.value;
            setValues(previous => ({...previous, [name]: value}));
            setResult(null);
          }} />
      </label>)}</div>;
  }

  const incomplete = Boolean(result?.unknown_costs.length);
  const loss = result?.estimated_profit.startsWith('-');
  return <>
    <h1>Tính lợi nhuận</h1>
    <div className="profit-toolbar">
      <p className="muted">Nhập số tiền bằng USD. Số màu xám là ví dụ.</p>
      <button type="button" onClick={onReturn}>{returnLabel}</button>
    </div>
    {source && <p className="profit-source">
      <strong>{source.product} · {source.sku}</strong>
      {source.price == null || source.price === '' ? ' · Chưa có giá sản xuất trong catalog.'
        : ` · Giá gốc catalog ${money(source.price)} mỗi sản phẩm. Có thể sửa giá trong ô bên dưới.`}
    </p>}
    <div className="profit-layout">
      <form className="profit-form" onSubmit={event => {
        event.preventDefault();
        const payload = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== ''));
        void run(async () => {
          setResult(await api<Profit>('/profit', 'POST', {...payload, quantity: Number(payload.quantity)}));
        });
      }}>
        <fieldset disabled={busy}>
          <legend>Doanh thu</legend>
          {fields(saleFields)}
        </fieldset>
        <fieldset disabled={busy}>
          <legend>Chi phí</legend>
          <p className="muted">Để trống khoản chưa biết. Nhập 0 nếu khoản đó không phát sinh.</p>
          {fields(costFields)}
        </fieldset>
        <div className="profit-actions">
          <button className="primary" disabled={busy}>{busy ? 'Đang tính…' : 'Tính lợi nhuận'}</button>
          <button type="button" disabled={busy} onClick={() => {
            setValues(Object.fromEntries([...saleFields, ...costFields].map(field => [field.name, field.example])));
            setResult(null);
            setExample(true);
          }}>Điền số mẫu</button>
          {example && <button type="button" disabled={busy} onClick={() => {
            setValues(initialValues);
            setResult(null);
            setExample(false);
          }}>{source ? 'Về số liệu SKU' : 'Xóa số mẫu'}</button>}
        </div>
      </form>
      <section className="profit-result" aria-label="Kết quả tính lợi nhuận" aria-live="polite">
        <h2 ref={resultHeading}>Kết quả</h2>
        {result ? <>
          <p className="profit-result-label">{incomplete ? 'Số tiền còn lại sau các chi phí đã nhập'
            : loss ? 'Lỗ dự kiến' : 'Lợi nhuận dự kiến'}</p>
          <strong className={loss ? 'profit-value is-loss' : 'profit-value'}>{money(result.estimated_profit)}</strong>
          {example && <p className="muted">Kịch bản đang dùng số mẫu hoặc số đã chỉnh từ mẫu.</p>}
          {incomplete && <p className="profit-incomplete">Còn khoản chưa nhập. Kết quả có thể thay đổi khi bổ sung chi phí.</p>}
          <dl className="profit-breakdown">
            <div><dt>Doanh thu sau giảm giá</dt><dd>{money(result.revenue)}</dd></div>
            <div><dt>Tổng chi phí đã nhập</dt><dd>{money(result.total_known_costs)}</dd></div>
            <div><dt>Còn lại mỗi sản phẩm</dt><dd>{money(result.profit_per_item)}</dd></div>
            <div><dt>Biên lợi nhuận theo chi phí đã nhập</dt><dd>{result.margin_percent === null
              ? 'Không tính được khi doanh thu bằng 0' : `${result.margin_percent.replace('.', ',')}%`}</dd></div>
          </dl>
          <h3>Chi tiết chi phí</h3>
          <dl className="profit-breakdown profit-costs">
            {costFields.map(({name}) => <div key={name}><dt>{costLabels[name]}</dt>
              <dd>{result.costs[name] === undefined ? 'Chưa nhập' : money(result.costs[name]!)}</dd>
            </div>)}
          </dl>
        </> : <p className="muted">Điền giá bán và số lượng, rồi bấm Tính lợi nhuận để xem kết quả.</p>}
      </section>
    </div>
  </>;
}
