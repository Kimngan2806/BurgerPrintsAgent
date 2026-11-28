'use client';

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Menu, Plus, Send, Square, X, Sun, Moon, Package, FileImage, MessageSquare, ShoppingBag, LifeBuoy, Calculator, LogOut} from 'lucide-react';
import DesignStudio from '@/components/DesignStudio';
import DraftArtwork from '@/components/DraftArtwork';
import ProfitCalculator, {type ProfitSource} from '@/components/ProfitCalculator';
import {uploadDesign, type DesignAsset} from '@/lib/designs';
import MessageBubble from '@/components/MessageBubble';
import StreamingIndicator from '@/components/StreamingIndicator';
import {ApiError, api, apiUrl, readChatStream, requestApi} from '@/lib/api';

type Message = {id: string; role: 'user' | 'agent'; content: string; products?: Product[]};
type Conversation = {id: string; title: string; messages: Message[]; draft_id?: string};
type Line = {sku: string; quantity: number; asset_id: string; position: string};
type Address = {name: string; street: string; city: string; state: string; zip: string; country: string; email?: string; phone?: string};
type Draft = {id: string; version: number; lines: Line[]; address: Address; acknowledge_unverified_print: boolean};
type Variant = {sku_code: string; color?: string; size?: string; provider_name?: string; price?: string | null};
type Product = {id: string; name: string; image_url?: string; variants?: Variant[]; recommended_sku?: string; catalog_updated_at?: number; attribute_note?: string};
type Order = {reference: string; draft_id?: string; state: string; result: Record<string, unknown>; updated_at?: number};
type Review = {id: string; draft_version: number; summary: {store: string; sandbox: boolean; lines: (Line & {product_name: string; color: string; size: string; catalog_price: string | null; file: {name: string; sha256: string}; availability: {status: string}})[]; address: Address; cost_note: string; unknown_costs: string[]; transaction_notice: string}};
type View = 'chat' | 'search' | 'draft' | 'designs' | 'orders' | 'support' | 'profit';

type DraftTarget = {draftId: string; index: number; sku: string};
type StudioLink = DraftTarget & {productId: string; color?: string};
type ProfitContext = {source: ProfitSource; from: View};

const lockedOrderStates = new Set(['sending', 'verifying', 'created']);
const addressFields = [
  {name: 'country', label: 'Quốc gia (mã ISO)', example: 'US'},
  {name: 'name', label: 'Họ tên', example: 'John Smith'},
  {name: 'email', label: 'Email · tùy chọn', example: 'ten@example.com'},
  {name: 'phone', label: 'Số điện thoại · tùy chọn', example: '+1 212 555 0100'},
  {name: 'street', label: 'Số nhà và tên đường', example: '123 Main St'},
  {name: 'city', label: 'Thành phố', example: 'New York'},
  {name: 'state', label: 'Bang / tỉnh', example: 'NY'},
  {name: 'zip', label: 'Mã bưu chính', example: '10001'},
] as const;

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

function ProductCard({product, onAdd, onProfit, disabled}: {
  product: Product; onAdd: (sku: string) => void; onProfit: (source: ProfitSource) => void; disabled: boolean;
}) {
  const [selected, setSelected] = useState(() =>
    product.variants?.some(v => v.sku_code === product.recommended_sku) ? product.recommended_sku!
      : product.variants?.length === 1 ? product.variants[0].sku_code : '');
  const variant = product.variants?.find(v => v.sku_code === selected);
  return <article className="product-card">
    {product.image_url ? <img src={product.image_url} alt={product.name} onError={e => {e.currentTarget.style.display = 'none';}} /> : <div className="image-placeholder"><Package />Chưa có ảnh sản phẩm</div>}
    <h3>{product.name}</h3><p className="muted">{product.id}</p>
    <label>Chọn biến thể thực tế<select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Màu · size · xưởng</option>{product.variants?.map(v => <option key={v.sku_code} value={v.sku_code}>{v.color || '?'} · {v.size || '?'} · {v.provider_name || 'Chưa rõ xưởng'} — {v.sku_code}</option>)}</select></label>
    {variant && <p><strong>{variant.price == null || variant.price === '' ? 'Chưa có giá' : `${variant.price} USD`}</strong> <span className="muted">giá catalog / SKU</span></p>}
    <p className="muted">{timeText(product.catalog_updated_at)} · Khả dụng chưa kiểm tra</p>
    <button className="primary" disabled={!variant || disabled} onClick={() => onAdd(selected)}>Kiểm tra SKU và thêm vào đơn</button>
    <button type="button" disabled={!variant || disabled} onClick={() => {
      if (variant) onProfit({sku: variant.sku_code, product: product.name, price: variant.price, quantity: 1});
    }}>Tính lợi nhuận cho SKU</button>
  </article>;
}

export default function WorkspacePage() {
  const [user, setUser] = useState<{name: string; store: string; submission_enabled?: boolean} | null>(null);
  const [ready, setReady] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [googleLogin, setGoogleLogin] = useState(false);
  const [view, setView] = useState<View>('chat');
  const [sidebar, setSidebar] = useState(false);
  const [dark, setDark] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const listScope = useRef(0);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [interruptedChat, setInterruptedChat] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const nearBottom = useRef(true);
  const bottom = useRef<HTMLDivElement>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const draftRef = useRef<Draft | null>(null);
  const saveInFlight = useRef<Promise<Draft> | null>(null);
  const [panel, setPanel] = useState(false);
  const [review, setReview] = useState<Review | null>(null);
  const reviewTitle = useRef<HTMLHeadingElement>(null);
  const [assets, setAssets] = useState<DesignAsset[]>([]);
  const [studioLink, setStudioLink] = useState<StudioLink | null>(null);
  const [searchProducts, setSearchProducts] = useState<Product[]>([]);
  const [searchMessage, setSearchMessage] = useState('');
  const [orders, setOrders] = useState<Order[]>([]);
  const [supports, setSupports] = useState<{id: string; message: string; note: string; reference?: string}[]>([]);
  const [supportReference, setSupportReference] = useState('');
  const [profitContext, setProfitContext] = useState<ProfitContext | null>(null);

  async function refreshLists() {
    const scope = listScope.current;
    const [c, d, a, o, s] = await Promise.all([
      api<Conversation[]>('/work/conversation'), api<Draft[]>('/work/draft'), api<DesignAsset[]>('/work/asset'),
      api<Order[]>('/orders'), api<typeof supports>('/work/support')]);
    if (scope === listScope.current) {
      setConversations(c); setDrafts(d); setAssets(a); setOrders(o); setSupports(s);
    }
  }

  async function logOut() {
    await api('/logout', 'POST');
    listScope.current += 1;
    setUser(null); setAuthMode('login'); setConversation(null); setConversations([]); setMessages([]); setInput('');
    setInterruptedChat(null);
    setDraft(null); draftRef.current = null; setDrafts([]); setAssets([]); setReview(null); setPanel(false);
    setSearchProducts([]); setSearchMessage(''); setOrders([]); setSupports([]); setSupportReference('');
    setProfitContext(null); setStudioLink(null);
    setView('chat');
  }
  const restoreSession = useCallback(async () => {
    setError('');
    try {
      setUser(await api<typeof user>('/me'));
      setReady(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setReady(true);
      else setError(e instanceof Error ? e.message : 'Chưa tải được phiên làm việc.');
    }
  }, []);
  useEffect(() => {
    void restoreSession();
    const url = new URL(window.location.href);
    if (url.searchParams.get('auth_error') === 'google') {
      setError('Đăng nhập Google chưa hoàn tất. Bạn có thể thử lại hoặc dùng tài khoản BurgerPrintsAgent.');
      url.searchParams.delete('auth_error');
      window.history.replaceState(window.history.state, '', url);
    }
    const theme = localStorage.getItem('theme') === 'dark'; setDark(theme);
    document.documentElement.setAttribute('data-theme', theme ? 'dark' : 'light');
    return () => abort.current?.abort();
  }, [restoreSession]);
  useEffect(() => {
    if (!ready || user) return;
    const controller = new AbortController();
    void api<{google: boolean}>('/auth/options', 'GET', undefined, controller.signal)
      .then(options => setGoogleLogin(options.google))
      .catch(() => {});
    return () => controller.abort();
  }, [ready, user]);
  useEffect(() => {if (user) refreshLists().catch(e => setError(e.message));}, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {if (nearBottom.current) bottom.current?.scrollIntoView({behavior: loading ? 'auto' : 'smooth'});}, [messages, loading]);
  useEffect(() => {draftRef.current = draft;}, [draft]);
  useEffect(() => {if (review && panel) reviewTitle.current?.scrollIntoView({block: 'nearest'});}, [review, panel]);

  // Draft edits are saved automatically; compare-and-swap protects simultaneous tabs.
  useEffect(() => {
    if (!dirty || !draft || saving || saveError) return;
    const timer = setTimeout(() => {saveDraft().catch(e => {setSaveError(true); setError(e.message);});}, 700);
    return () => clearTimeout(timer);
  }, [draft, dirty, saving, saveError]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(action: () => Promise<void>) {
    if (actionPending.current) return;
    actionPending.current = true;
    setBusy(true); setError(''); setNotice('');
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : 'Không hoàn tất được. Dữ liệu đã lưu vẫn được giữ.');}
    finally {actionPending.current = false; setBusy(false);}
  }
  function editDraft(next: Draft) {draftRef.current = next; setDraft(next); setDirty(true); setReview(null); setSaveError(false);}
  async function saveDraft(): Promise<Draft | null> {
    if (saveInFlight.current) {
      const saved = await saveInFlight.current;
      const current = draftRef.current;
      if (current?.id === saved.id && current !== saved) return saveDraft();
      return saved;
    }
    const snapshot = draftRef.current;
    if (!snapshot) return null;
    setSaving(true);
    const pending = api<Draft>(`/drafts/${snapshot.id}`, 'PUT', {
      version: snapshot.version, lines: snapshot.lines, address: snapshot.address,
      acknowledge_unverified_print: snapshot.acknowledge_unverified_print,
    }).then(saved => {
      if (draftRef.current === snapshot) {draftRef.current = saved; setDraft(saved); setDirty(false);}
      else if (draftRef.current?.id === snapshot.id) {
        const next = {...draftRef.current, version: saved.version};
        draftRef.current = next; setDraft(next);
      }
      setDrafts(prev => [saved, ...prev.filter(d => d.id !== saved.id)]);
      setSaveError(false); return saved;
    }).finally(() => {saveInFlight.current = null; setSaving(false);});
    saveInFlight.current = pending;
    return pending;
  }
  async function openDraft(ident: string, bind = true, discardUnsaved = false) {
    if (loading) throw new Error('Đợi lượt trả lời hoàn tất trước khi chuyển đơn nháp.');
    if (dirty && !discardUnsaved) await saveDraft();
    const next = await api<Draft>(`/drafts/${ident}`);
    if (bind && conversation && conversation.draft_id !== ident) {
      setConversation(await api<Conversation>(`/conversations/${conversation.id}/draft`, 'PUT', {draft_id: ident}));
    }
    draftRef.current = next; setDraft(next); setDirty(false); setSaveError(false); setReview(null); setPanel(true);
  }
  async function newDraft() {
    if (loading) throw new Error('Đợi lượt trả lời hoàn tất trước khi tạo đơn nháp khác.');
    if (dirty) await saveDraft();
    const next = await api<Draft>('/drafts', 'POST');
    setDrafts(previous => [next, ...previous]);
    if (conversation) setConversation(await api<Conversation>(`/conversations/${conversation.id}/draft`, 'PUT', {draft_id: next.id}));
    draftRef.current = next; setDraft(next); setDirty(false); setSaveError(false); setReview(null); setPanel(true);
    return next;
  }
  async function openConversation(ident: string) {
    if (dirty) await saveDraft();
    const next = await api<Conversation>(`/conversations/${ident}`);
    setConversation(next); setMessages(next.messages); setView('chat'); setSidebar(false);
    setInterruptedChat(null);
    if (next.draft_id) await openDraft(next.draft_id, false, true);
    else {setDraft(null); draftRef.current = null; setPanel(false); setReview(null);}
    nearBottom.current = true;
  }
  async function send(text = input) {
    if (!text.trim() || loading || busy) return;
    if (dirty) {try {await saveDraft();} catch (e) {setError((e as Error).message); return;}}
    setError(''); setNotice(''); setInterruptedChat(null); setLoading(true); setInput(''); nearBottom.current = true;
    let active = conversation;
    let sent = false;
    let accepted = false;
    let completed = false;
    const userId = crypto.randomUUID();
    const agentId = crypto.randomUUID();
    const controller = new AbortController(); abort.current = controller;
    try {
      if (!active) {active = await api<Conversation>('/conversations', 'POST'); setConversation(active);}
      const draftId = draftRef.current?.id;
      if (draftId && active.draft_id !== draftId && !controller.signal.aborted) {
        active = await api<Conversation>(`/conversations/${active.id}/draft`, 'PUT', {draft_id: draftId});
        setConversation(active);
      }
      if (controller.signal.aborted) {setInput(text); return;}
      setMessages(prev => [...prev, {id: userId, role: 'user', content: text}, {id: agentId, role: 'agent', content: ''}]);
      sent = true;
      const response = await requestApi('/chat/stream', 'POST', {session_id: active.id, message: text}, controller.signal);
      accepted = true;
      await readChatStream(response, answer => {
        setMessages(prev => prev.map(m => m.id === agentId ? {...m, content: answer} : m));
      });
      completed = true;
      const updated = await api<Conversation>(`/conversations/${active.id}`);
      setConversation(updated); setMessages(updated.messages);
      if (updated.draft_id) {
        const next = await api<Draft>(`/drafts/${updated.draft_id}`); draftRef.current = next; setDraft(next); setDirty(false); setReview(null); setPanel(true);
      }
      await refreshLists();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Chưa hoàn tất được yêu cầu.';
      const status = e instanceof ApiError ? e.status : undefined;
      if (!sent || (!accepted && status !== undefined && status >= 400 && status < 500)) {
        setInput(text);
        setMessages(prev => prev.filter(m => m.id !== userId && m.id !== agentId));
        setError(message);
      } else {
        setInterruptedChat(active?.id ?? null);
        setMessages(prev => prev.filter(m => m.id !== agentId || Boolean(m.content)));
        if (controller.signal.aborted) setNotice('Đã dừng nhận phản hồi. Tải lại hội thoại để kiểm tra nội dung đã lưu.');
        else if (completed) setError('Đã nhận phản hồi. Tải lại hội thoại để xem nội dung đã lưu.');
        else setError(`${message} Kiểm tra nội dung đã lưu trước khi gửi lại.`);
      }
    } finally {setLoading(false); abort.current = null;}
  }
  async function addSku(code: string) {
    const info = await api<{ok: boolean; sku: Variant; availability: Record<string, {status: string}>}>(`/sku?code=${encodeURIComponent(code.trim())}`);
    if (!info.ok) throw new Error('SKU không khớp chính xác. Hãy chọn mã đầy đủ trong danh sách biến thể.');
    const availability = info.availability[info.sku.sku_code];
    if (availability?.status === 'out_of_stock') throw new Error('SKU đang có trong danh sách hết hàng. Chọn lại biến thể.');
    const current = draftRef.current;
    const active = current && !isLocked(current.id) ? current : await newDraft();
    editDraft({...active, lines: [...active.lines, {sku: info.sku.sku_code, quantity: 1, asset_id: '', position: 'front'}]});
    setPanel(true);
    await saveDraft();
    setNotice(`Đã thêm ${info.sku.sku_code} vào đơn nháp. Bạn có thể gắn ảnh ở dòng SKU vừa thêm.`);
  }

  function isLocked(id: string) {
    return orders.some(order => order.draft_id === id && lockedOrderStates.has(order.state));
  }

  function navigate(next: View) {
    setView(next); setSidebar(false); setPanel(next === 'draft' && !!draftRef.current);
    setError(''); setNotice('');
    if (next === 'designs') setStudioLink(null);
    if (next === 'support') setSupportReference('');
    if (next === 'profit') setProfitContext(null);
  }

  function openProfit(source: ProfitSource, from: View = view) {
    navigate('profit');
    setProfitContext({source, from});
  }

  async function findVariant(sku: string) {
    const {results} = await api<{results: Product[]}>(`/products?q=${encodeURIComponent(sku)}`);
    for (const product of results) {
      const variant = product.variants?.find(item => item.sku_code === sku);
      if (variant) return {product, variant};
    }
    throw new Error('Chưa tìm được SKU này trong catalog. Hãy kiểm tra biến thể trong đơn nháp.');
  }

  function updateLine(target: DraftTarget, change: Partial<Line>) {
    const active = draftRef.current;
    if (active?.id !== target.draftId || active.lines[target.index]?.sku !== target.sku || isLocked(active.id)) {
      throw new Error('Dòng SKU đã thay đổi. Mở lại đơn nháp và chọn dòng cần sửa.');
    }
    editDraft({...active, lines: active.lines.map((line, index) => index === target.index ? {...line, ...change} : line)});
  }

  async function attachAsset(target: DraftTarget, asset: DesignAsset) {
    setAssets(previous => [asset, ...previous.filter(item => item.id !== asset.id)]);
    try {
      await saveInFlight.current;
      updateLine(target, {asset_id: asset.id});
      await saveDraft();
    } catch (error) {
      const detail = error instanceof Error ? ' ' + error.message : '';
      throw new Error(`Ảnh “${asset.name}” có trong thư viện. Chưa lưu được ảnh vào đơn nháp.${detail}`);
    }
    setNotice(`Đã gắn “${asset.name}” vào ${target.sku} và lưu đơn nháp.`);
  }

  const draftLocked = !!draft && isLocked(draft.id);
  const draftReadOnly = busy || loading || draftLocked;
  const draftLink = studioLink && draft?.id === studioLink.draftId
    && draft.lines[studioLink.index]?.sku === studioLink.sku ? studioLink : undefined;
  const draftSteps: string[] = [];
  if (draft && !draftLocked) {
    if (!draft.lines.length) draftSteps.push('Thêm ít nhất một SKU.');
    const missingImages = draft.lines.map((line, index) => line.asset_id ? 0 : index + 1).filter(Boolean);
    if (missingImages.length) draftSteps.push(`Gắn ảnh vào dòng ${missingImages.join(', ')}.`);
    const requiredAddress = addressFields.filter(({name}) => name !== 'email' && name !== 'phone'
      && (name !== 'state' || draft.address.country.toUpperCase() === 'US'));
    const missingAddress = requiredAddress.filter(({name}) => !draft.address[name]?.trim());
    if (missingAddress.length) draftSteps.push(`Nhập thông tin người nhận: ${missingAddress.map(({label}) => label.toLowerCase()).join(', ')}.`);
    if (!draft.acknowledge_unverified_print) draftSteps.push('Xác nhận đã đối chiếu ảnh với mẫu in của SKU.');
  }

  if (!ready) return <main className="auth-screen">{error
    ? <section className="auth-card"><p role="alert">{error}</p><button className="primary" onClick={restoreSession}>Tải lại phiên làm việc</button></section>
    : <p role="status">Đang khôi phục phiên làm việc…</p>}</main>;
  if (!user) return <main className="auth-screen"><form className="auth-card" onSubmit={e => {e.preventDefault(); const data = new FormData(e.currentTarget); run(async () => {await api(`/auth/${authMode}`, 'POST', Object.fromEntries(data)); setUser(await api('/me'));});}}>
    <img src="/burgerprint-logo.svg" alt="BurgerPrints" width="180" /><h1>Không gian làm việc POD</h1>
    <p>Tìm SKU, chuẩn bị thiết kế và tiếp tục đơn nháp bằng tài khoản BurgerPrintsAgent của bạn.</p>
    <label>Tên tài khoản<input name="name" autoComplete="username" minLength={3} maxLength={80} required /></label>
    <label>Mật khẩu<input name="password" type="password" autoComplete={authMode === 'register' ? 'new-password' : 'current-password'} minLength={10} maxLength={256} required /></label>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <button className="primary" disabled={busy}>{busy ? 'Đang xử lý…' : authMode === 'register' ? 'Tạo tài khoản' : 'Đăng nhập'}</button>
    {googleLogin && <button className="google-auth-button" type="button" disabled={busy} onClick={() => window.location.assign(apiUrl('/auth/google'))}>
      <img src="/google-sign-in.png" width={18} height={18} alt="" />Tiếp tục với Google
    </button>}
    <button type="button" onClick={() => {setAuthMode(authMode === 'login' ? 'register' : 'login'); setError('');}}>{authMode === 'login' ? 'Chưa có tài khoản? Đăng ký' : 'Đã có tài khoản? Đăng nhập'}</button>
  </form></main>;

  const navigation: [View, string, React.ReactNode][] = [['chat', 'Hội thoại', <MessageSquare key="chat" size={18} />], ['draft', 'Đơn nháp', <ShoppingBag key="draft" size={18} />], ['orders', 'Đơn hàng', <Package key="orders" size={18} />], ['designs', 'Thiết kế', <FileImage key="designs" size={18} />], ['support', 'Hỗ trợ', <LifeBuoy key="support" size={18} />], ['profit', 'Tính lợi nhuận', <Calculator key="profit" size={18} />]];
  const reloadChat = view === 'chat' && conversation && interruptedChat === conversation.id
    ? <button disabled={busy || loading || dirty || saving} onClick={() => run(async () => {
      await openConversation(conversation.id);
      await refreshLists();
    })}>Tải lại hội thoại</button>
    : null;
  const feedback = <>
    {error && <div className="error-banner" role="alert">{error}{reloadChat}
      <button aria-label="Đóng thông báo lỗi" onClick={() => setError('')}><X size={16} /></button></div>}
    {notice && <div className="notice-banner" role="status">{notice}{!error && reloadChat}</div>}
    {busy && <p className="task-progress" role="status">Đang xử lý…</p>}
  </>;
  return <div className="workspace-shell">
    {sidebar && <button className="sidebar-scrim" aria-label="Đóng điều hướng" onClick={() => setSidebar(false)} />}
    <aside className={`workspace-nav ${sidebar ? 'is-open' : ''}`}>
      <img className="brand-logo" src="/burgerprint-logo.svg" alt="BurgerPrints" />
      <button className="primary" disabled={loading || busy || dirty} onClick={() => {setConversation(null); setMessages([]); setDraft(null); draftRef.current = null; setReview(null); setView('chat'); setPanel(false); setSidebar(false);}}><Plus size={18} />Chat mới</button>
      <nav aria-label="Chức năng">{navigation.map(([key, label, icon]) => <button key={key} aria-current={view === key ? 'page' : undefined} onClick={() => navigate(key)}>{icon}{label}</button>)}</nav>
      <section className="nav-history" aria-labelledby="history-heading">
        <h2 id="history-heading" className="nav-caption">Lịch sử của bạn</h2>
        <div className="history-list">
          {conversations.map(c => <button key={c.id} title={c.title} disabled={loading || busy} onClick={() => run(() => openConversation(c.id))}>{c.title}</button>)}
          {!conversations.length && <p className="muted">Chưa có hội thoại</p>}
        </div>
      </section>
      <div className="nav-footer"><p>{user.name}</p><small>{user.store}</small>
        <button onClick={() => {const next = !dark; setDark(next); localStorage.setItem('theme', next ? 'dark' : 'light'); document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light');}}>{dark ? <Sun size={16} /> : <Moon size={16} />}{dark ? 'Giao diện sáng' : 'Giao diện tối'}</button>
        <button disabled={loading || saving || dirty} onClick={() => run(logOut)}><LogOut size={16} />Đăng xuất</button>
      </div>
    </aside>
    <main className="workspace-main">
      <header className="workspace-header"><button className="mobile-menu" aria-label="Mở điều hướng" onClick={() => setSidebar(true)}><Menu size={22} /></button><div><strong>{view === 'search' ? 'Tìm sản phẩm' : navigation.find(n => n[0] === view)?.[1]}</strong><p className="muted">BurgerPrintsAgent · Trợ lý fulfillment</p></div><button onClick={() => {setPanel(!panel); if (!draft) navigate('draft');}}>Đơn nháp {draft ? `(${draft.lines.length})` : ''}</button></header>
      {!panel && feedback}
      {view === 'chat' ? <>
        <div className="workspace-chat" onScroll={e => {const el = e.currentTarget; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;}}>
          {!messages.length && <section className="welcome"><span className="eyebrow">TỪ Ý TƯỞNG ĐẾN ĐƠN HÀNG</span><h1>Hôm nay bạn muốn<br />hoàn thành việc gì?</h1><p>Tìm đúng biến thể, chuẩn bị file và duyệt đơn trong một nơi.</p>
            <div className="entry-grid">{[['search', 'Tìm sản phẩm', 'Lọc và chọn biến thể từ catalog'], ['draft', 'Tạo đơn từ SKU', 'Dùng mã chính xác bạn đã có'], ['designs', 'Mở thiết kế', 'Tải file, URL hoặc dùng thư viện'], ['orders', 'Tra cứu đơn', 'Trạng thái nguồn và tracking']].map(([key, title, subtitle]) => <button key={key} onClick={() => navigate(key as View)}><strong>{title}</strong><span>{subtitle}</span></button>)}</div>
            {!!drafts.length && <button className="resume-draft" onClick={() => run(async () => {await openDraft(drafts[0].id); setView('draft');})}>Tiếp tục đơn nháp gần nhất · {drafts[0].lines.length} dòng sản phẩm →</button>}
          </section>}
          {messages.map(m => <React.Fragment key={m.id}>
            <MessageBubble role={m.role} content={m.content} />
            {m.role === 'agent' && !!m.products?.length && <div className="product-grid">
              {m.products.map(p => <ProductCard key={p.id} product={p} onAdd={sku => run(() => addSku(sku))}
                onProfit={openProfit} disabled={busy || loading} />)}
            </div>}
          </React.Fragment>)}
          {loading && <StreamingIndicator />}
          <div ref={bottom} />
        </div>
        <form className="workspace-composer" onSubmit={e => {e.preventDefault(); send();}}><div><input aria-label="Tin nhắn" value={input} onChange={e => setInput(e.target.value)} placeholder="Tìm áo thun, so sánh SKU hoặc sửa đơn nháp…" maxLength={10000} disabled={loading} />{loading ? <button type="button" onClick={() => abort.current?.abort()} aria-label="Dừng trả lời, không hủy đơn"><Square size={16} />Dừng trả lời</button> : <button className="primary" disabled={!input.trim() || busy || saving}><Send size={16} />Gửi</button>}</div><small>Kiểm tra dữ liệu và bản duyệt trước khi xác nhận đơn.</small></form>
      </> : <div className="workspace-content" key={view}>
        {view === 'search' && <>
          <h1>Tìm sản phẩm phù hợp</h1>
          <p className="muted">Chọn màu và cỡ để xem giá của đúng SKU, rồi thêm vào đơn nháp hoặc tính lợi nhuận.</p>
          <form className="filter-form" onSubmit={event => {
            event.preventDefault();
            const query = new URLSearchParams();
            new FormData(event.currentTarget).forEach((value, key) => {if (value) query.set(key, String(value));});
            void run(async () => {
              const result = await api<{results: Product[]; code?: string}>(`/products?${query}`);
              setSearchProducts(result.results);
              setSearchMessage(result.code === 'CATALOG_UNAVAILABLE' ? 'Danh mục đang đồng bộ. Thử tìm lại sau khi dữ liệu sẵn sàng.'
                : result.results.length ? '' : 'Chưa tìm thấy sản phẩm phù hợp. Thử đổi tên, màu, cỡ hoặc mức giá.');
            });
          }}>
            <label>Sản phẩm hoặc SKU<input name="q" placeholder="T-shirt hoặc mã SKU đầy đủ" /></label>
            <label>Màu<input name="color" placeholder="Black" /></label>
            <label>Cỡ<input name="size" placeholder="M" /></label>
            <label>Giá catalog tối đa (USD)<input name="max_price" type="number" min="0" step=".01" /></label>
            <button className="primary" disabled={busy}>Tìm sản phẩm</button>
          </form>
          <div className="product-grid">{searchProducts.map(p => <ProductCard key={p.id} product={p}
            onAdd={sku => run(() => addSku(sku))} onProfit={openProfit} disabled={busy || loading} />)}</div>
          {searchMessage && <p className="empty-state" role="status">{searchMessage}</p>}
        </>}
        {view === 'draft' && <><h1>Đơn nháp của bạn</h1><p>Đơn nhiều SKU được lưu theo tài khoản. Chọn một đơn để tiếp tục.</p><button className="primary" disabled={busy || saving} onClick={() => run(async () => {await newDraft();})}><Plus size={18} />Tạo đơn nháp</button><div className="record-list">{drafts.map(d => <button key={d.id} disabled={saving} onClick={() => run(() => openDraft(d.id))}><strong>{d.lines.map(l => l.sku).join(', ') || 'Đơn nháp trống'}</strong><span>{d.lines.length} dòng · phiên bản {d.version} · {d.address.name || 'Chưa có người nhận'}</span></button>)}</div></>}
        {view === 'designs' && <DesignStudio assets={assets} busy={busy || loading}
          refreshLists={refreshLists} run={run} onNotice={setNotice} draftLink={draftLink}
          initialAsset={assets.find(asset => asset.id === (draftLink ? draft?.lines[draftLink.index]?.asset_id : undefined))}
          draftLines={draftLocked ? [] : draft?.lines.map(line => line.sku) ?? []}
          onReturn={() => navigate('draft')}
          onAttach={(asset, index) => {
            if (!draft || !draft.lines[index]) return;
            const target = {draftId: draft.id, index, sku: draft.lines[index].sku};
            void run(async () => {await attachAsset(target, asset); setView('draft'); setPanel(true);});
          }} />}
        {view === 'orders' && <>
          <h1>Đơn hàng trong tài khoản</h1>
          <p>Theo dõi các đơn bạn đã gửi từ BurgerPrintsAgent.</p>
          <button disabled={busy} onClick={() => run(async () => {
            setOrders(await api<Order[]>('/orders')); setNotice('Đã cập nhật danh sách đơn hàng.');
          })}>Tải lại danh sách</button>
          <div className="record-list">{orders.map(order => <article key={order.reference} className="order-card">
            <h3>{String(order.result.order_id || order.reference)}</h3>
            <p><strong>{stateText[order.state] || order.state}</strong></p>
            <p className="muted">Mã tham chiếu: {order.reference}<br />{timeText(order.updated_at)}</p>
            <p>Trạng thái từ BurgerPrints: {String((order.result.detail as Record<string, unknown> | undefined)?.state
              || (order.result.detail as Record<string, unknown> | undefined)?.status || 'Chưa cập nhật')}</p>
            {Boolean(order.result.message) && <p>{String(order.result.message)}</p>}
            <OrderDetails result={order.result} />
            <div className="workspace-actions">
              <button disabled={busy} onClick={() => run(async () => {
                const refreshed = await api<Order>(`/orders/${order.reference}/refresh`, 'POST');
                setOrders(previous => previous.map(item => item.reference === order.reference ? {...item, ...refreshed} : item));
                setNotice(`Đã đối chiếu đơn ${order.reference} với BurgerPrints.`);
              })}>Cập nhật trạng thái và vận chuyển</button>
              <button onClick={() => {navigate('support'); setSupportReference(order.reference);}}>Yêu cầu hỗ trợ cho đơn này</button>
            </div>
          </article>)}</div>
          {!orders.length && <div className="empty-state"><p>Chưa có đơn đã gửi.</p>
            <button onClick={() => navigate('draft')}>Mở đơn nháp</button>
          </div>}
        </>}
        {view === 'support' && <>
          <h1>Yêu cầu hỗ trợ</h1>
          <p>Ghi lại vấn đề và chọn đơn liên quan để tiện theo dõi trong ứng dụng.</p>
          <form className="stack-form" onSubmit={event => {
            event.preventDefault();
            const form = event.currentTarget;
            const data = Object.fromEntries(new FormData(form));
            void run(async () => {
              const saved = await api<(typeof supports)[number]>('/support', 'POST', data);
              setSupports(previous => [saved, ...previous]);
              form.reset();
              setNotice('Đã lưu yêu cầu hỗ trợ trong ứng dụng.');
            });
          }}>
            <label>Đơn liên quan · tùy chọn
              <select name="reference" value={supportReference} onChange={event => setSupportReference(event.currentTarget.value)}>
                <option value="">Không chọn đơn</option>
                {orders.map(order => <option key={order.reference} value={order.reference}>
                  {String(order.result.order_id || order.reference)}
                </option>)}
              </select>
            </label>
            <label>Mô tả vấn đề<textarea name="message" required minLength={5} maxLength={6000}
              placeholder="Ví dụ: Tôi cần kiểm tra mã vận chuyển của đơn này." /></label>
            <button className="primary" disabled={busy}>Lưu yêu cầu hỗ trợ</button>
          </form>
          <div className="record-list">{supports.map(item => <article key={item.id}>
            {item.reference && <strong>Đơn {item.reference}</strong>}<p>{item.message}</p><small>{item.note}</small>
          </article>)}</div>
        </>}
        {view === 'profit' && <ProfitCalculator source={profitContext?.source ?? null} busy={busy} run={run}
          onReturn={() => navigate(profitContext?.from ?? 'search')}
          returnLabel={profitContext?.from === 'draft' ? 'Về đơn nháp'
            : profitContext?.from === 'chat' ? 'Về hội thoại' : 'Về tìm sản phẩm'} />}
      </div>}
    </main>
    {panel && <aside className="context-panel" key={draft?.id ?? 'empty'} aria-label="Đơn nháp đang làm"><div className="panel-heading"><h2>Đơn nháp</h2><button aria-label="Đóng bảng đơn nháp" onClick={() => setPanel(false)}><X size={20} /></button></div>
      {feedback}
      {!draft ? <div className="empty-state"><p>Chưa mở đơn nháp.</p><button className="primary" disabled={busy} onClick={() => run(async () => {await newDraft();})}>Tạo đơn nháp</button></div> : <>
        <p className="muted">{user.store}<br />Phiên bản {draft.version} · {saving ? 'Đang lưu…' : dirty ? 'Chưa lưu' : 'Đã lưu'}</p>
        {draftLocked ? <div className="empty-state"><p>Đơn này đã chuyển sang trang Đơn hàng để theo dõi.</p>
          <button onClick={() => navigate('orders')}>Mở Đơn hàng</button>
        </div> : <>
          <form className="sku-add" onSubmit={event => {
            event.preventDefault();
            const form = event.currentTarget;
            const code = String(new FormData(form).get('sku') ?? '').trim();
            if (code) void run(async () => {await addSku(code); form.reset();});
          }}>
            <label>Mã SKU đầy đủ<input name="sku" placeholder="Ví dụ: USALCMW11UL-White-11oz" required disabled={draftReadOnly} /></label>
            <button disabled={draftReadOnly}>Thêm SKU</button>
            <button type="button" onClick={() => navigate('search')}>Tìm sản phẩm trong catalog</button>
          </form>
          {draft.lines.map((line, index) => {
            const target = {draftId: draft.id, index, sku: line.sku};
            return <section className="draft-line" key={`${index}-${line.sku}`} aria-label={`Dòng ${index + 1} · ${line.sku}`}>
              <strong>Dòng {index + 1} · {line.sku}</strong>
              <label>Số lượng<input type="number" min="1" max="10000" value={line.quantity} disabled={draftReadOnly}
                onChange={event => {
                  const quantity = event.currentTarget.valueAsNumber;
                  if (Number.isInteger(quantity) && quantity >= 1 && quantity <= 10000) updateLine(target, {quantity});
                }} /></label>
              <DraftArtwork key={line.asset_id} id={line.asset_id} assets={assets} disabled={draftReadOnly}
                onSelect={id => run(async () => {
                  if (id) {
                    const asset = assets.find(item => item.id === id);
                    if (asset) await attachAsset(target, asset);
                  } else {
                    updateLine(target, {asset_id: ''});
                    await saveDraft();
                    setNotice(`Đã bỏ ảnh khỏi ${line.sku}.`);
                  }
                })}
                onUpload={file => run(async () => attachAsset(target, await uploadDesign(file)))}
                onImport={url => run(async () => {
                  const asset = await api<DesignAsset>('/assets/import', 'POST', {url, name: `Mặt trước · ${line.sku}`.slice(0, 160)});
                  await attachAsset(target, asset);
                })}
                onPreview={() => run(async () => {
                  const {product, variant} = await findVariant(line.sku);
                  navigate('designs');
                  setStudioLink({...target, productId: product.id, color: variant.color});
                })} />
              <div className="workspace-actions">
                <button disabled={draftReadOnly} onClick={() => run(async () => {
                  const {product, variant} = await findVariant(line.sku);
                  openProfit({sku: line.sku, product: product.name, price: variant.price, quantity: line.quantity}, 'draft');
                })}>Tính lợi nhuận</button>
                <button disabled={draftReadOnly} onClick={() => {
                  const active = draftRef.current;
                  if (active?.id !== draft.id) return;
                  editDraft({...active, lines: active.lines.filter((_, lineIndex) => lineIndex !== index)});
                }}>Xóa dòng</button>
              </div>
            </section>;
          })}
          <fieldset disabled={draftReadOnly}>
            <legend>Người nhận</legend>
            {addressFields.map(({name, label, example}) => <label key={name}>
              {name === 'state' && draft.address.country.toUpperCase() !== 'US' ? label + ' · tùy chọn' : label}
              <input type={name === 'email' ? 'email' : name === 'phone' ? 'tel' : 'text'} value={draft.address[name] ?? ''}
                placeholder={example} maxLength={name === 'country' ? 2 : name === 'phone' ? 40 : name === 'email' ? 254 : 200}
                onChange={event => {
                  const active = draftRef.current;
                  if (active?.id !== draft.id) return;
                  const value = event.currentTarget.value;
                  editDraft({...active, address: {...active.address, [name]: name === 'country' ? value.toUpperCase() : value}});
                }} />
            </label>)}
          </fieldset>
          <label className="checkbox-label"><input type="checkbox" disabled={draftReadOnly}
            checked={draft.acknowledge_unverified_print} onChange={event => {
              const active = draftRef.current;
              if (active?.id === draft.id) editDraft({...active, acknowledge_unverified_print: event.currentTarget.checked});
            }} />Tôi đã đối chiếu ảnh với mẫu in mặt trước của từng SKU.</label>
          {saveError && <button disabled={busy || saving} onClick={() => run(() => openDraft(draft.id, true, true))}>Tải bản máy chủ và bỏ thay đổi chưa lưu</button>}
          <button disabled={!dirty || saving || draftReadOnly} onClick={() => run(async () => {
            await saveDraft(); setNotice('Đã lưu đơn nháp.');
          })}>Lưu ngay</button>
          {draftSteps.length > 0 && <div className="draft-next">
            <strong>Trước khi duyệt đơn</strong><ul>{draftSteps.map(step => <li key={step}>{step}</li>)}</ul>
          </div>}
          <button className="primary" disabled={draftReadOnly || draftSteps.length > 0} onClick={() => run(async () => {
            const latest = dirty || saveInFlight.current ? await saveDraft() : draftRef.current;
            if (latest?.id === draft.id) {
              setReview(await api<Review>(`/drafts/${latest.id}/review`, 'POST', {version: latest.version}));
            }
          })}>Kiểm tra và xem bản duyệt</button>
        </>}
        {review && !draftLocked && <section className="review-card">
          <h3 ref={reviewTitle}>Bản duyệt v{review.draft_version}</h3>
          <p>{review.summary.store} · {review.summary.sandbox ? 'Đơn thử' : 'Đơn thật'}</p>
          {review.summary.lines.map((line, index) => <div key={index}>
            <strong>{line.product_name || line.sku}</strong>
            <p>{line.sku} · {line.color} · {line.size} × {line.quantity}</p>
            <p>{line.catalog_price == null ? 'Chưa có giá' : `${line.catalog_price} USD / sản phẩm · giá catalog`}</p>
            <p>Ảnh mặt trước: {line.file.name}</p>
            <p>{stateText[line.availability?.status] || 'Khả dụng chưa xác minh'}</p>
          </div>)}
          <p>Người nhận: {Object.values(review.summary.address).filter(Boolean).join(', ')}</p>
          <p>{review.summary.cost_note}</p><p>Phí vận chuyển, thuế và phụ phí cần được xác nhận riêng.</p>
          <p>{review.summary.transaction_notice}</p>
          {user.submission_enabled === false ? <p role="status">Cửa hàng chưa bật gửi đơn. Đơn nháp và bản duyệt đã được lưu.</p>
            : <button className="primary" disabled={busy || dirty || saving} onClick={() => run(async () => {
              const result = await api<Order>(`/drafts/${draft.id}/submit`, 'POST', {review_id: review.id, confirmed: true});
              setOrders(previous => [{...result, draft_id: draft.id}, ...previous.filter(order => order.reference !== result.reference)]);
              setReview(null);
              navigate('orders');
              setNotice(stateText[result.state] || result.state);
            })}>Xác nhận gửi {review.summary.sandbox ? 'đơn thử' : 'đơn thật'}</button>}
        </section>}
      </>}
    </aside>}
  </div>;
}
