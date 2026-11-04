'use client';

import React, {useEffect, useRef, useState} from 'react';
import {Menu, Plus, Send, Square, X, Sun, Moon, Package, FileImage, MessageSquare, ShoppingBag, LifeBuoy, Calculator, LogOut} from 'lucide-react';
import MessageBubble from '@/components/MessageBubble';
import StreamingIndicator from '@/components/StreamingIndicator';
import {getApiBaseUrl} from '@/lib/api';

type Message = {id: string; role: 'user' | 'agent'; content: string};
type Conversation = {id: string; title: string; messages: Message[]; products?: Product[]; draft_id?: string};
type Line = {sku: string; quantity: number; asset_id: string; position: string};
type Address = {name: string; street: string; city: string; state: string; zip: string; country: string};
type Draft = {id: string; version: number; lines: Line[]; address: Address; acknowledge_unverified_print: boolean};
type Asset = {id: string; version: number; name: string; tags: string; file_version: number; sha256: string; validation: {width: number; height: number; message: string}};
type Variant = {sku_code: string; color?: string; size?: string; provider_name?: string; price?: string};
type Product = {id: string; name: string; image_url?: string; variants?: Variant[]; catalog_updated_at?: number; attribute_note?: string};
type Order = {reference: string; state: string; result: Record<string, unknown>; updated_at?: number};
type Review = {id: string; draft_version: number; summary: {store: string; sandbox: boolean; lines: (Line & {product_name: string; color: string; size: string; catalog_price: string | null; file: {name: string; sha256: string}; availability: {status: string}})[]; address: Address; cost_note: string; unknown_costs: string[]; transaction_notice: string}};
type View = 'chat' | 'search' | 'draft' | 'designs' | 'orders' | 'support' | 'profit';

const apiUrl = (path: string) => `${getApiBaseUrl()}/api${path}`;
async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {method, credentials: 'include',
    headers: body instanceof FormData ? undefined : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Yêu cầu không hợp lệ (${response.status}). Kiểm tra các trường vừa nhập.`);
  return data;
}
const timeText = (timestamp?: number) => timestamp ? new Date(timestamp * 1000).toLocaleString('vi-VN') : 'Chưa có thời điểm cập nhật';
const stateText: Record<string, string> = {sending: 'Đang gửi / cần đối chiếu nếu bị gián đoạn', verifying: 'Đang xác minh — không gửi lại', created: 'Đã xác nhận tạo đơn', rejected: 'Nguồn từ chối — sửa đơn rồi duyệt lại', unknown: 'Chưa xác minh', out_of_stock: 'Có trong danh sách hết hàng', not_listed_out_of_stock: 'Không nằm trong danh sách hết hàng; chưa bảo đảm nhận đơn'};

function OrderDetails({result}: {result: Record<string, unknown>}) {
  const detail = result.detail as Record<string, unknown> | undefined;
  const seller = detail?.seller as Record<string, unknown> | undefined;
  const tracking = Array.isArray(result.tracking) ? result.tracking as Record<string, unknown>[] : [];
  const items = Array.isArray(detail?.items) ? detail.items as Record<string, unknown>[] : [];
  return <section className="source-details">
    {detail && <><p>Thanh toán: {String(detail.payment_date || detail.payment_status || 'Nguồn chưa xác nhận')}</p><p>Sản xuất / fulfillment: {String(detail.fulfillment || 'Nguồn chưa xác nhận')}</p>{['amount', 'shipping_fee', 'tax_amount'].map(key => seller?.[key] != null || detail[key] != null ? <p key={key}>{({amount:'Chi phí đơn',shipping_fee:'Phí vận chuyển',tax_amount:'Thuế'})[key]}: {String(seller?.[key] ?? detail[key])} {String(detail.currency || 'USD')} · nguồn BurgerPrints</p> : null)}</>}
    {items.map((item, i) => <p key={i}>{String(item.name || item.sku || item.catalog_sku || 'Sản phẩm')} × {String(item.quantity || '?')}</p>)}
    <p className="muted">{timeText(result.checked_at as number | undefined)}</p>
    {tracking.length ? tracking.map((t,i) => <p key={i}>Tracking: {String(t.tracking_carrier || t.carrier || '')} · {String(t.tracking_code || t.code || '')}{typeof t.url === 'string' && /^https?:\/\//i.test(t.url) && <> · <a href={t.url} target="_blank" rel="noreferrer">Mở tra cứu</a></>}</p>) : <p className="muted">Chưa có tracking được nguồn xác nhận.</p>}
  </section>;
}

function ProductCard({product, onAdd}: {product: Product; onAdd: (sku: string) => void}) {
  const [selected, setSelected] = useState('');
  const variant = product.variants?.find(v => v.sku_code === selected);
  return <article className="product-card">
    {product.image_url ? <img src={product.image_url} alt={product.name} onError={e => {e.currentTarget.style.display = 'none';}} /> : <div className="image-placeholder"><Package />Chưa có ảnh sản phẩm</div>}
    <h3>{product.name}</h3><p className="muted">{product.id}</p>
    <label>Chọn biến thể thực tế<select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Màu · size · xưởng</option>{product.variants?.map(v => <option key={v.sku_code} value={v.sku_code}>{v.color || '?'} · {v.size || '?'} · {v.provider_name || 'Chưa rõ xưởng'} — {v.sku_code}</option>)}</select></label>
    {variant && <p><strong>{variant.price == null || variant.price === '' ? 'Chưa có giá' : `${variant.price} USD`}</strong> <span className="muted">giá catalog / SKU</span></p>}
    <p className="muted">{timeText(product.catalog_updated_at)} · Khả dụng chưa kiểm tra</p>
    <button className="primary" disabled={!selected} onClick={() => onAdd(selected)}>Kiểm tra SKU và thêm vào đơn</button>
  </article>;
}

export default function WorkspacePage() {
  const [user, setUser] = useState<{name: string; store: string; sandbox: boolean} | null>(null);
  const [ready, setReady] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [view, setView] = useState<View>('chat');
  const [sidebar, setSidebar] = useState(false);
  const [dark, setDark] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const nearBottom = useRef(true);
  const bottom = useRef<HTMLDivElement>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const draftRef = useRef<Draft | null>(null);
  const [panel, setPanel] = useState(false);
  const [review, setReview] = useState<Review | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetQuery, setAssetQuery] = useState('');
  const [previousAsset, setPreviousAsset] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [searched, setSearched] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [supports, setSupports] = useState<{id: string; message: string; note: string}[]>([]);
  const [calculation, setCalculation] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<{name: string; count: number}[]>([]);

  async function refreshLists() {
    const [c, d, a, o, s, m] = await Promise.all([
      api<Conversation[]>('/work/conversation'), api<Draft[]>('/work/draft'), api<Asset[]>('/work/asset'),
      api<Order[]>('/orders'), api<typeof supports>('/work/support'), api<{events: typeof metrics}>('/metrics')]);
    setConversations(c); setDrafts(d); setAssets(a); setOrders(o); setSupports(s); setMetrics(m.events);
  }
  useEffect(() => {
    api<typeof user>('/me').then(setUser).catch(() => {}).finally(() => setReady(true));
    const theme = localStorage.getItem('theme') === 'dark'; setDark(theme);
    document.documentElement.setAttribute('data-theme', theme ? 'dark' : 'light');
    return () => abort.current?.abort();
  }, []);
  useEffect(() => {if (user) refreshLists().catch(e => setError(e.message));}, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {if (nearBottom.current) bottom.current?.scrollIntoView({behavior: loading ? 'auto' : 'smooth'});}, [messages, loading]);
  useEffect(() => {draftRef.current = draft;}, [draft]);

  // Draft edits are saved automatically; compare-and-swap protects simultaneous tabs.
  useEffect(() => {
    if (!dirty || !draft || saving || saveError) return;
    const timer = setTimeout(() => {saveDraft().catch(e => {setSaveError(true); setError(e.message);});}, 700);
    return () => clearTimeout(timer);
  }, [draft, dirty, saving, saveError]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : 'Không hoàn tất được. Dữ liệu đã lưu vẫn được giữ.');}
    finally {setBusy(false);}
  }
  function editDraft(next: Draft) {draftRef.current = next; setDraft(next); setDirty(true); setReview(null); setSaveError(false);}
  async function saveDraft() {
    const snapshot = draftRef.current;
    if (!snapshot) return null;
    if (saving) throw new Error('Đang lưu đơn nháp. Đợi lưu xong rồi tiếp tục.');
    setSaving(true);
    try {
      const saved = await api<Draft>(`/drafts/${snapshot.id}`, 'PUT', {version: snapshot.version, lines: snapshot.lines, address: snapshot.address, acknowledge_unverified_print: snapshot.acknowledge_unverified_print});
      if (draftRef.current === snapshot) {draftRef.current = saved; setDraft(saved); setDirty(false);}
      else {const next = {...draftRef.current!, version: saved.version}; draftRef.current = next; setDraft(next);}
      setDrafts(prev => [saved, ...prev.filter(d => d.id !== saved.id)]);
      setSaveError(false); return saved;
    } finally {setSaving(false);}
  }
  async function openDraft(ident: string, bind = true, discardUnsaved = false) {
    if (loading) throw new Error('Đợi lượt trả lời hoàn tất trước khi chuyển đơn nháp.');
    if (dirty && !discardUnsaved) await saveDraft();
    const next = await api<Draft>(`/drafts/${ident}`);
    draftRef.current = next; setDraft(next); setDirty(false); setSaveError(false); setReview(null); setPanel(true);
    if (bind && conversation) await api(`/conversations/${conversation.id}/draft`, 'PUT', {draft_id: ident});
  }
  async function newDraft() {
    if (loading) throw new Error('Đợi lượt trả lời hoàn tất trước khi tạo đơn nháp khác.');
    if (dirty) await saveDraft();
    const next = await api<Draft>('/drafts', 'POST');
    draftRef.current = next; setDraft(next); setDirty(false); setReview(null); setPanel(true);
    if (conversation) await api(`/conversations/${conversation.id}/draft`, 'PUT', {draft_id: next.id});
    await refreshLists(); return next;
  }
  async function openConversation(ident: string) {
    if (dirty) await saveDraft();
    const next = await api<Conversation>(`/conversations/${ident}`);
    setConversation(next); setMessages(next.messages); setProducts(next.products || []); setView('chat'); setSidebar(false);
    if (next.draft_id) await openDraft(next.draft_id, false);
    else {setDraft(null); draftRef.current = null; setPanel(false); setReview(null);}
    nearBottom.current = true;
  }
  async function send(text = input) {
    if (!text.trim() || loading || busy) return;
    if (dirty) {try {await saveDraft();} catch (e) {setError((e as Error).message); return;}}
    setError(''); setLoading(true); setInput(''); nearBottom.current = true;
    let active = conversation;
    const agentId = crypto.randomUUID();
    const controller = new AbortController(); abort.current = controller;
    try {
      if (!active) {active = await api<Conversation>('/conversations', 'POST'); setConversation(active);}
      setMessages(prev => [...prev, {id: crypto.randomUUID(), role: 'user', content: text}, {id: agentId, role: 'agent', content: ''}]);
      const response = await fetch(apiUrl('/chat/stream'), {method: 'POST', credentials: 'include', signal: controller.signal,
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: active.id, message: text})});
      if (!response.ok || !response.body) {const failure = await response.json(); throw new Error(failure.detail || 'Không kết nối được chatbot.');}
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let answer = ''; let ended = false;
      while (!ended) {
        const chunk = await reader.read(); if (chunk.done) break;
        buffer += decoder.decode(chunk.value, {stream: true});
        const events = buffer.split(/\r?\n\r?\n/); buffer = events.pop() || '';
        for (const event of events) {
          const value = event.split(/\r?\n/).filter(s => s.startsWith('data:')).map(s => s.slice(5).trimStart()).join('\n');
          if (!value) continue;
          if (value === '[DONE]') {ended = true; break;}
          const data = JSON.parse(value);
          if (data.type === 'tool_result') {
            if (data.tool === 'search_products') setProducts(data.result.results || []);
            if (data.tool === 'get_sku_info' && data.result.ok) setProducts([{...data.result.product, image_url: data.result.product_image_url, variants: [data.result.sku]}]);
            continue;
          }
          answer += data.text || (data.error ? `\n\n${data.error}` : '');
          setMessages(prev => prev.map(m => m.id === agentId ? {...m, content: answer} : m));
        }
      }
      if (!ended) throw new Error('Kết nối phản hồi bị ngắt. Mở lại lịch sử để kiểm tra phần đã lưu.');
      const updated = await api<Conversation>(`/conversations/${active.id}`);
      setConversation(updated);
      if (updated.draft_id) {
        const next = await api<Draft>(`/drafts/${updated.draft_id}`); draftRef.current = next; setDraft(next); setDirty(false); setReview(null); setPanel(true);
      }
      await refreshLists();
    } catch (e) {
      const stopped = e instanceof DOMException && e.name === 'AbortError';
      const message = stopped ? 'Đã dừng trả lời. Thao tác này không hủy đơn hàng.' : (e as Error).message;
      setNotice(stopped ? message : ''); if (!stopped) setError(message);
      setMessages(prev => prev.map(m => m.id === agentId && !m.content ? {...m, content: message} : m));
    } finally {setLoading(false); abort.current = null;}
  }
  async function addSku(code: string) {
    const info = await api<{ok: boolean; sku: Variant; availability: Record<string, {status: string}>}>(`/sku?code=${encodeURIComponent(code)}`);
    if (!info.ok) throw new Error('SKU không khớp chính xác. Hãy chọn mã đầy đủ trong danh sách biến thể.');
    const availability = info.availability[info.sku.sku_code];
    if (availability?.status === 'out_of_stock') throw new Error('SKU đang có trong danh sách hết hàng. Chọn lại biến thể.');
    const active = draftRef.current || await newDraft();
    editDraft({...active, lines: [...active.lines, {sku: info.sku.sku_code, quantity: 1, asset_id: '', position: 'front'}]});
    setNotice(stateText[availability?.status] || 'Khả dụng chưa xác minh.'); setPanel(true);
  }
  const navigate = (next: View) => {setView(next); setSidebar(false); if (next === 'draft') setPanel(true);};

  if (!ready) return <main className="auth-screen"><p role="status">Đang khôi phục phiên làm việc…</p></main>;
  if (!user) return <main className="auth-screen"><form className="auth-card" onSubmit={e => {e.preventDefault(); const data = new FormData(e.currentTarget); run(async () => {await api(`/auth/${authMode}`, 'POST', Object.fromEntries(data)); setUser(await api('/me'));});}}>
    <img src="/burgerprint-logo.svg" alt="BurgerPrints" width="180" /><h1>Không gian làm việc POD</h1>
    <p>Tìm SKU, chuẩn bị thiết kế và tiếp tục đơn nháp của bạn.</p><p className="demo-label">Demo một store · tài khoản ứng dụng riêng, không phải đăng nhập BurgerPrints</p>
    <label>Tên tài khoản<input name="name" autoComplete="username" minLength={3} maxLength={80} required /></label>
    <label>Mật khẩu<input name="password" type="password" autoComplete={authMode === 'register' ? 'new-password' : 'current-password'} minLength={10} maxLength={256} required /></label>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <button className="primary" disabled={busy}>{busy ? 'Đang xử lý…' : authMode === 'register' ? 'Tạo tài khoản' : 'Đăng nhập'}</button>
    <button type="button" onClick={() => {setAuthMode(authMode === 'login' ? 'register' : 'login'); setError('');}}>{authMode === 'login' ? 'Chưa có tài khoản? Đăng ký' : 'Đã có tài khoản? Đăng nhập'}</button>
  </form></main>;

  const navigation: [View, string, React.ReactNode][] = [['chat', 'Hội thoại', <MessageSquare key="chat" size={18} />], ['draft', 'Đơn nháp', <ShoppingBag key="draft" size={18} />], ['orders', 'Đơn hàng', <Package key="orders" size={18} />], ['designs', 'Thiết kế', <FileImage key="designs" size={18} />], ['support', 'Hỗ trợ', <LifeBuoy key="support" size={18} />], ['profit', 'Tính lợi nhuận', <Calculator key="profit" size={18} />]];
  return <div className="workspace-shell">
    {sidebar && <button className="sidebar-scrim" aria-label="Đóng điều hướng" onClick={() => setSidebar(false)} />}
    <aside className={`workspace-nav ${sidebar ? 'is-open' : ''}`}>
      <img className="brand-logo" src="/burgerprint-logo.svg" alt="BurgerPrints" />
      <button className="primary" disabled={loading || busy || dirty} onClick={() => {setConversation(null); setMessages([]); setProducts([]); setDraft(null); draftRef.current = null; setReview(null); setView('chat'); setPanel(false); setSidebar(false);}}><Plus size={18} />Chat mới</button>
      <nav aria-label="Chức năng">{navigation.map(([key, label, icon]) => <button key={key} aria-current={view === key ? 'page' : undefined} onClick={() => navigate(key)}>{icon}{label}</button>)}</nav>
      <p className="nav-caption">Lịch sử của bạn</p><div className="history-list">{conversations.map(c => <button key={c.id} disabled={loading || busy} onClick={() => run(() => openConversation(c.id))}>{c.title}</button>)}{!conversations.length && <p className="muted">Chưa có hội thoại</p>}</div>
      <div className="nav-footer"><p>{user.name}</p><small>{user.store}</small><span className="demo-label">{user.sandbox ? 'Sandbox' : 'Đơn thật'} · Demo một store</span>
        <button onClick={() => {const next = !dark; setDark(next); localStorage.setItem('theme', next ? 'dark' : 'light'); document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light');}}>{dark ? <Sun size={16} /> : <Moon size={16} />}{dark ? 'Giao diện sáng' : 'Giao diện tối'}</button>
        <button disabled={loading || saving || dirty} onClick={() => run(async () => {await api('/logout', 'POST'); setUser(null); setConversation(null); setMessages([]); setDraft(null); draftRef.current = null; setProducts([]);})}><LogOut size={16} />Đăng xuất</button>
      </div>
    </aside>
    <main className="workspace-main">
      <header className="workspace-header"><button className="mobile-menu" aria-label="Mở điều hướng" onClick={() => setSidebar(true)}><Menu size={22} /></button><div><strong>{view === 'search' ? 'Tìm sản phẩm' : navigation.find(n => n[0] === view)?.[1]}</strong><p className="muted">BurgerPrintsAgent · Trợ lý fulfillment</p></div><button onClick={() => {setPanel(!panel); if (!draft) navigate('draft');}}>Đơn nháp {draft ? `(${draft.lines.length})` : ''}</button></header>
      {error && <div className="error-banner" role="alert">{error}<button aria-label="Đóng thông báo lỗi" onClick={() => setError('')}><X size={16} /></button></div>}
      {notice && <div className="notice-banner" role="status">{notice}</div>}
      {busy && <p className="task-progress" role="status">Đang xử lý…</p>}
      {view === 'chat' ? <>
        <div className="workspace-chat" onScroll={e => {const el = e.currentTarget; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;}}>
          {!messages.length && <section className="welcome"><span className="eyebrow">TỪ Ý TƯỞNG ĐẾN ĐƠN HÀNG</span><h1>Hôm nay bạn muốn<br />hoàn thành việc gì?</h1><p>Tìm đúng biến thể, chuẩn bị file và duyệt đơn trong một nơi.</p>
            <div className="entry-grid">{[['search', 'Tìm sản phẩm', 'Lọc và chọn biến thể từ catalog'], ['draft', 'Tạo đơn từ SKU', 'Dùng mã chính xác bạn đã có'], ['designs', 'Mở thiết kế', 'Tải file, URL hoặc dùng thư viện'], ['orders', 'Tra cứu đơn', 'Trạng thái nguồn và tracking']].map(([key, title, subtitle]) => <button key={key} onClick={() => navigate(key as View)}><strong>{title}</strong><span>{subtitle}</span></button>)}</div>
            {!!drafts.length && <button className="resume-draft" onClick={() => run(async () => {await openDraft(drafts[0].id); setView('draft');})}>Tiếp tục đơn nháp gần nhất · {drafts[0].lines.length} dòng sản phẩm →</button>}
          </section>}
          {messages.map(m => <MessageBubble key={m.id} role={m.role} content={m.content} />)}
          {loading && <StreamingIndicator />}
          {!!products.length && <div className="product-grid">{products.map(p => <ProductCard key={p.id} product={p} onAdd={sku => run(() => addSku(sku))} />)}</div>}
          <div ref={bottom} />
        </div>
        <form className="workspace-composer" onSubmit={e => {e.preventDefault(); send();}}><div><input aria-label="Tin nhắn" value={input} onChange={e => setInput(e.target.value)} placeholder="Tìm áo thun, so sánh SKU hoặc sửa đơn nháp…" maxLength={10000} disabled={loading} />{loading ? <button type="button" onClick={() => abort.current?.abort()} aria-label="Dừng trả lời, không hủy đơn"><Square size={16} />Dừng trả lời</button> : <button className="primary" disabled={!input.trim() || busy || saving}><Send size={16} />Gửi</button>}</div><small>Kiểm tra dữ liệu và bản duyệt trước khi xác nhận đơn.</small></form>
      </> : <div className="workspace-content">
        {view === 'search' && <><h1>Tìm sản phẩm phù hợp</h1><p className="muted">Chọn đúng tổ hợp màu và size trước khi xem giá SKU. Tối đa ba lựa chọn mỗi lần.</p><form className="filter-form" onSubmit={e => {e.preventDefault(); const data = new FormData(e.currentTarget); const query = new URLSearchParams(); data.forEach((v, k) => {if (v) query.set(k, String(v));}); run(async () => {const result = await api<{results: Product[]}>(`/products?${query}`); setProducts(result.results); setSearched(true);});}}><label>Sản phẩm hoặc SKU<input name="q" placeholder="T-shirt hoặc mã SKU đầy đủ" /></label><label>Màu<input name="color" placeholder="Black" /></label><label>Size<input name="size" placeholder="M" /></label><label>Giá catalog tối đa (USD)<input name="max_price" type="number" min="0" step=".01" /></label><button className="primary" disabled={busy}>Tìm sản phẩm</button></form><div className="product-grid">{products.map(p => <ProductCard key={p.id} product={p} onAdd={sku => run(() => addSku(sku))} />)}</div>{searched && !products.length && <div className="empty-state">Chưa có kết quả trong catalog hiện tại. Thử nới một điều kiện màu, size hoặc giá; nếu catalog trống, cần cấu hình API và đồng bộ.</div>}</>}
        {view === 'draft' && <><h1>Đơn nháp của bạn</h1><p>Đơn nhiều SKU được lưu theo tài khoản. Chọn một đơn để tiếp tục.</p><button className="primary" disabled={busy || saving} onClick={() => run(async () => {await newDraft();})}><Plus size={18} />Tạo đơn nháp</button><div className="record-list">{drafts.map(d => <button key={d.id} disabled={saving} onClick={() => run(() => openDraft(d.id))}><strong>{d.lines.map(l => l.sku).join(', ') || 'Đơn nháp trống'}</strong><span>{d.lines.length} dòng · phiên bản {d.version} · {d.address.name || 'Chưa có người nhận'}</span></button>)}</div></>}
        {view === 'designs' && <><h1>Thư viện thiết kế</h1><p>Preview file gốc đã lưu. Chưa phải mockup hay xác nhận chuẩn in.</p><label>Phiên bản mới của<select value={previousAsset} onChange={e => setPreviousAsset(e.target.value)}><option value="">Thiết kế mới</option>{assets.map(a => <option key={a.id} value={a.id}>{a.name} · v{a.file_version}</option>)}</select></label><div className="design-import"><label className="upload-box">Tải PNG, JPEG hoặc WebP · tối đa 25 MB<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={e => {const file = e.target.files?.[0]; if (!file) return; e.target.value = ''; run(async () => {const form = new FormData(); form.set('file', file); await api(`/assets/upload?previous_id=${previousAsset}`, 'POST', form); await refreshLists(); setNotice('Đã lưu phiên bản file. Chọn lại file trong dòng sản phẩm để dùng bản mới.');});}} /></label><form onSubmit={e => {e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); run(async () => {await api('/assets/import', 'POST', {...data, previous_id: previousAsset}); await refreshLists();});}}><label>Tên thiết kế<input name="name" required /></label><label>URL ảnh công khai<input name="url" type="url" required placeholder="https://…/design.png" /></label><button disabled={busy}>Nhập từ URL</button></form></div><label>Tìm theo tên / phân loại<input value={assetQuery} onChange={e => setAssetQuery(e.target.value)} /></label><div className="asset-grid">{assets.filter(a => `${a.name} ${a.tags}`.toLowerCase().includes(assetQuery.toLowerCase())).map(a => <article className="asset-card" key={a.id}><img src={apiUrl(`/assets/${a.id}/preview`)} alt={`Preview ${a.name}, phiên bản ${a.file_version}`} /><h3>{a.name} · v{a.file_version}</h3><p>{a.validation.width} × {a.validation.height} px</p><p className="muted">{a.validation.message}</p><form onSubmit={e => {e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); run(async () => {await api(`/assets/${a.id}`, 'PATCH', {version: a.version, ...data}); await refreshLists();});}}><label>Tên<input name="name" defaultValue={a.name} required /></label><label>Phân loại<input name="tags" defaultValue={a.tags} /></label><button disabled={busy}>Lưu tên và phân loại</button></form></article>)}</div>{!assets.length && <p className="empty-state">Thư viện chưa có file. Tải file hoặc nhập URL để bắt đầu.</p>}</>}
        {view === 'orders' && <><h1>Đơn hàng trong tài khoản</h1><p>Chỉ hiển thị đơn đã gửi từ tài khoản ứng dụng này tới store demo.</p><button onClick={() => run(refreshLists)}>Tải lại danh sách</button><div className="record-list">{orders.map(order => <article key={order.reference} className="order-card"><h3>{String(order.result.order_id || order.reference)}</h3><p><strong>{stateText[order.state] || order.state}</strong></p><p className="muted">Mã tham chiếu: {order.reference}<br />{timeText(order.updated_at)}</p><p>Trạng thái nguồn: {String((order.result.detail as Record<string, unknown> | undefined)?.state || (order.result.detail as Record<string, unknown> | undefined)?.status || 'Chưa cập nhật')}</p><button disabled={busy} onClick={() => run(async () => {await api(`/orders/${order.reference}/refresh`, 'POST'); await refreshLists();})}>Đối chiếu đơn và tracking</button>{Boolean(order.result.message) && <p>{String(order.result.message)}</p>}<OrderDetails result={order.result} /><button onClick={() => {navigate('support'); setNotice(`Mã tham chiếu cần hỗ trợ: ${order.reference}`);}}>Yêu cầu hỗ trợ</button></article>)}</div>{!orders.length && <p className="empty-state">Chưa có yêu cầu gửi đơn. Bạn có thể tiếp tục từ Đơn nháp.</p>}</>}
        {view === 'support' && <><h1>Yêu cầu hỗ trợ</h1><p>Lưu vấn đề và mã tham chiếu để tiếp tục xử lý. Chưa gửi yêu cầu tới BurgerPrints; chưa hỗ trợ hủy đơn tự động.</p><form className="stack-form" onSubmit={e => {e.preventDefault(); const data = Object.fromEntries(new FormData(e.currentTarget)); run(async () => {await api('/support', 'POST', data); await refreshLists(); setNotice('Đã lưu yêu cầu hỗ trợ trong ứng dụng.');});}}><label>Mã tham chiếu (nếu có)<input name="reference" /></label><label>Mô tả vấn đề<textarea name="message" required minLength={5} maxLength={6000} /></label><button className="primary" disabled={busy}>Lưu yêu cầu hỗ trợ</button></form><div className="record-list">{supports.map(s => <article key={s.id}><p>{s.message}</p><small>{s.note}</small></article>)}</div></>}
        {view === 'profit' && <><h1>Lợi nhuận theo kịch bản</h1><p>Đơn vị USD. Giá bán và giá sản xuất theo sản phẩm; các phí khác là tổng cho số lượng đã nhập. Để trống khoản chưa biết.</p><form className="filter-form" onSubmit={e => {e.preventDefault(); const values = Object.fromEntries(new FormData(e.currentTarget)); run(async () => {setCalculation(await api('/profit', 'POST', {...values, quantity: Number(values.quantity)}));});}}>{[['sale_price', 'Giá bán / sản phẩm', '20'], ['quantity', 'Số lượng', '1'], ['discount_percent', 'Giảm giá (%)', '0'], ['production_per_item', 'Giá sản xuất / sản phẩm', ''], ['shipping_total', 'Tổng phí ship', ''], ['platform_total', 'Tổng phí nền tảng', ''], ['other_total', 'Tổng chi phí khác', '']].map(([name, label, value]) => <label key={name}>{label}<input name={name} type="number" min={name === 'quantity' ? 1 : 0} step={name === 'quantity' ? 1 : '.01'} defaultValue={value} required={['sale_price', 'quantity', 'discount_percent'].includes(name)} /></label>)}<button className="primary" disabled={busy}>Tính kịch bản</button></form>{calculation && <section className="calculation-result"><h2>{String(calculation.estimated_profit)} USD</h2><p>Lợi nhuận dự kiến · margin {calculation.margin_percent == null ? 'không xác định' : `${calculation.margin_percent}%`}</p><p>Doanh thu sau giảm giá: {String(calculation.revenue)} USD</p>{Object.entries(calculation.costs as Record<string, string>).map(([k,v]) => <p key={k}>{k}: {v} USD · người bán nhập</p>)}<p>Chưa xác định: {(calculation.unknown_costs as string[]).join(', ') || 'Không có khoản bỏ trống trong biểu mẫu'}</p><small>{String(calculation.note)}</small></section>}<details><summary>Số liệu sử dụng của tài khoản</summary>{metrics.map(m => <p key={m.name}>{m.name}: {m.count}</p>)}</details></>}
      </div>}
    </main>
    {panel && <aside className="context-panel" aria-label="Đơn nháp đang làm"><div className="panel-heading"><h2>Đơn nháp</h2><button aria-label="Đóng bảng đơn nháp" onClick={() => setPanel(false)}><X size={20} /></button></div>
      {!draft ? <div className="empty-state"><p>Chưa mở đơn nháp.</p><button className="primary" disabled={busy} onClick={() => run(async () => {await newDraft();})}>Tạo đơn nháp</button></div> : <>
        <p className="muted">{user.store}<br />Phiên bản {draft.version} · {saving ? 'Đang lưu…' : dirty ? 'Chưa lưu' : 'Đã lưu'}</p>
        <form className="sku-add" onSubmit={e => {e.preventDefault(); const code = String(new FormData(e.currentTarget).get('sku')); run(() => addSku(code));}}><label>Mã SKU chính xác<input name="sku" placeholder="Dán mã SKU đầy đủ" required /></label><button disabled={busy || loading || saving}>Thêm SKU</button></form>
        {draft.lines.map((line, index) => <section className="draft-line" key={`${index}-${line.sku}`}><strong>{line.sku}</strong><label>Số lượng<input type="number" min="1" max="10000" value={line.quantity} onChange={e => editDraft({...draft, lines: draft.lines.map((l, i) => i === index ? {...l, quantity: Number(e.target.value)} : l)})} /></label><label>File mặt trước<select value={line.asset_id} onChange={e => editDraft({...draft, lines: draft.lines.map((l, i) => i === index ? {...l, asset_id: e.target.value} : l)})}><option value="">Chọn từ thư viện</option>{assets.map(a => <option key={a.id} value={a.id}>{a.name} · v{a.file_version}</option>)}</select></label>{line.asset_id && <img className="line-preview" src={apiUrl(`/assets/${line.asset_id}/preview`)} alt="Preview file mặt trước đã chọn" />}<button onClick={() => navigate('designs')}>Mở thư viện / tải file</button><button onClick={() => editDraft({...draft, lines: draft.lines.filter((_, i) => i !== index)})}>Xóa dòng</button></section>)}
        <fieldset><legend>Người nhận</legend>{(['country', 'name', 'street', 'city', 'state', 'zip'] as const).map(key => <label key={key}>{({country: 'Quốc gia (ISO: US, VN…)', name: 'Họ tên', street: 'Địa chỉ', city: 'Thành phố', state: `Bang / tỉnh ${draft.address.country.toUpperCase() === 'US' ? '(bắt buộc)' : '(tùy chọn)'}`, zip: 'Mã bưu chính'})[key]}<input value={draft.address[key]} maxLength={key === 'country' ? 2 : 200} onChange={e => editDraft({...draft, address: {...draft.address, [key]: key === 'country' ? e.target.value.toUpperCase() : e.target.value}})} /></label>)}</fieldset>
        <p className="muted">Chưa có dịch vụ bổ sung được xác minh cho SKU. Phí ship, thuế, tổng đơn và điều kiện giá nhiều sản phẩm chưa xác định.</p>
        <label className="checkbox-label"><input type="checkbox" checked={draft.acknowledge_unverified_print} onChange={e => editDraft({...draft, acknowledge_unverified_print: e.target.checked})} />Tôi đã tự đối chiếu template cho từng SKU và mặt in. Kiểm tra file cơ bản chưa xác nhận chuẩn in.</label>
        {saveError && <button onClick={() => run(async () => {await openDraft(draft.id, true, true);})}>Tải bản máy chủ (bỏ thay đổi chưa lưu)</button>}
        <button disabled={!dirty || saving || busy} onClick={() => run(async () => {await saveDraft();})}>Lưu ngay</button>
        <button className="primary" disabled={dirty || saving || busy || loading || !draft.lines.length} onClick={() => run(async () => {setReview(await api<Review>(`/drafts/${draft.id}/review`, 'POST', {version: draft.version}));})}>Kiểm tra và xem bản duyệt</button>
        {review && <section className="review-card"><h3>Bản duyệt v{review.draft_version}</h3><p>{review.summary.store} · {review.summary.sandbox ? 'SANDBOX' : 'ĐƠN THẬT'}</p>{review.summary.lines.map((l,i) => <div key={i}><strong>{l.product_name}</strong><p>{l.sku} · {l.color} · {l.size} × {l.quantity}</p><p>{l.catalog_price == null ? 'Chưa có giá' : `${l.catalog_price} USD · giá catalog`}</p><p>File: {l.file.name} · front</p><small>SHA256: {l.file.sha256.slice(0,16)}…</small><p>{stateText[l.availability?.status] || 'Khả dụng chưa xác minh'}</p></div>)}<p>{Object.values(review.summary.address).filter(Boolean).join(', ')}</p><p>{review.summary.cost_note}</p><p>Chưa xác định: {review.summary.unknown_costs.join(', ')}</p><p>{review.summary.transaction_notice}</p><p>Không chọn dịch vụ bổ sung.</p><button className="primary" disabled={busy || dirty || saving} onClick={() => run(async () => {const result = await api<Order>(`/drafts/${draft.id}/submit`, 'POST', {review_id: review.id, confirmed: true}); setNotice(stateText[result.state] || result.state); setReview(null); await refreshLists(); navigate('orders');})}>Xác nhận gửi {review.summary.sandbox ? 'đơn sandbox' : 'đơn thật'} v{review.draft_version}</button></section>}
      </>}
    </aside>}
  </div>;
}
