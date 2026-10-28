import React, { useCallback, useEffect, useMemo, useState } from 'react';

// Read ONLY public, stored Meta-library scan results. This page does not
// launch a new search and never conflates 21 public ad IDs with Meta ad sets.
// The crawler is currently on an isolated branch until verified and merged.
const BASE = 'https://raw.githubusercontent.com/chienlolk49-sketch/Global-Product-Hunter-AI/feature/product-focused-v15/cloud_hunter/data/';
const CATEGORIES = [
  ['beauty', 'Làm đẹp'], ['wellness', 'Chăm sóc sức khỏe'], ['home', 'Gia dụng'],
  ['kitchen', 'Nhà bếp'], ['electronics', 'Điện tử'], ['fashion', 'Thời trang'],
  ['baby', 'Mẹ và bé'], ['sport', 'Thể thao'], ['vehicle', 'Ô tô / xe máy'],
  ['travel', 'Du lịch'], ['garden', 'Làm vườn'], ['toys', 'Đồ chơi'],
  ['office', 'Văn phòng'], ['food', 'Thực phẩm']
] as const;

type Ad = { ad_id?: string; ad_url?: string; landing_url?: string; image_url?: string };
type Qualified = {
  name: string; category?: string; ad_count: number; active_ads_observed?: number;
  advertiser_count?: number; countries?: string[]; ads?: Ad[];
  product_url?: string; ad_links?: string[]; verification?: string;
};
type Candidate = {
  name: string; category?: string; observed_ad_ids: number; missing_to_21?: number;
  product_url?: string; sample_ad_links?: string[]; verification?: string;
};
type ScanStatus = {
  timestamp_utc?: string; state?: string; goal_completed?: boolean;
  unique_active_ads_observed_last_48h?: number; qualifying_products?: number;
  searches_attempted?: number; searches_succeeded?: number; new_ads?: number;
  category_qualified_counts?: Record<string, number>; campaign_state?: string;
};
type ScanTop = { updated_at?: string; categories?: Record<string, Qualified[]> };
type ScanCandidates = { updated_at?: string; count?: number; candidates?: Candidate[] };

function safeUrl(value?: string): string | undefined {
  try {
    if (!value) return undefined;
    const parsed = new URL(value);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : undefined;
  } catch { return undefined; }
}
function legitAdUrl(value?: string): string | undefined {
  const parsed = safeUrl(value);
  if (!parsed) return undefined;
  const url = new URL(parsed);
  return (url.hostname === 'facebook.com' || url.hostname === 'www.facebook.com') &&
    url.pathname.startsWith('/ads/library/') ? parsed : undefined;
}
async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(BASE + path + '?r=' + Date.now(), { cache: 'no-store' });
  if (!response.ok) throw new Error(path + ': HTTP ' + response.status);
  return response.json() as Promise<T>;
}
const integer = (n: unknown): number => typeof n === 'number' && Number.isFinite(n) ? n : 0;
const friendlyTime = (value?: string): string => {
  if (!value) return 'Chưa có';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? 'Không rõ' : d.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }) + ' (giờ Việt Nam)';
};

const CloudHunter: React.FC = () => {
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [top, setTop] = useState<ScanTop | null>(null);
  const [research, setResearch] = useState<ScanCandidates | null>(null);
  const [category, setCategory] = useState<string>('all');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastLoaded, setLastLoaded] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    const results = await Promise.allSettled([
      readJson<ScanStatus>('status.json'),
      readJson<ScanTop>('top50.json'),
      readJson<ScanCandidates>('candidates.json')
    ]);
    const [st, tp, ca] = results;
    if (st.status === 'fulfilled') setStatus(st.value);
    if (tp.status === 'fulfilled') setTop(tp.value);
    if (ca.status === 'fulfilled') setResearch(ca.value);
    const problems = results
      .map((x, i) => x.status === 'rejected' ? (['Trạng thái', 'Top 50', 'Sản phẩm tiềm năng'][i] + ': ' + String(x.reason)) : null)
      .filter((x): x is string => Boolean(x));
    setError(problems.length ? 'Không tải được tất cả nguồn dữ liệu. ' + problems.join('; ') : null);
    setLastLoaded(Date.now());
    setBusy(false);
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => { void refresh(); }, 60_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const qualified = useMemo(() => {
    const rows = Object.entries(top?.categories || {})
      .filter(([name]) => name !== 'other')
      .flatMap(([name, values]) => (Array.isArray(values) ? values : []).map(item => ({ ...item, category: name })));
    return rows.filter(x => integer(x.ad_count) >= 21)
      .filter(x => category === 'all' || x.category === category)
      .sort((a, b) => integer(b.ad_count) - integer(a.ad_count));
  }, [top, category]);
  const candidates = useMemo(() => {
    return (research?.candidates || [])
      .filter(x => category === 'all' || x.category === category)
      .filter(x => integer(x.observed_ad_ids) >= 2)
      .sort((a, b) => integer(b.observed_ad_ids) - integer(a.observed_ad_ids));
  }, [research, category]);

  return <div className="p-6 md:p-8 max-w-[1500px] mx-auto text-white space-y-6">
    <section className="rounded-2xl bg-surface border border-border p-6 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-primary font-extrabold">Dữ liệu Meta Ads Library công khai</div>
          <h2 className="text-3xl font-bold mt-1">Cloud Hunter — Kết quả quét thật</h2>
          <p className="text-text-secondary text-sm mt-2">Nguồn: nhánh V15 đang kiểm thử · Cập nhật kết quả hiển thị mỗi 60 giây</p>
          <p className="text-text-secondary text-xs mt-1">Lần dữ liệu cuối: {friendlyTime(status?.timestamp_utc || top?.updated_at)}</p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={busy}
          className="bg-primary hover:bg-primary-hover disabled:opacity-50 rounded-xl px-5 py-3 font-bold">
          {busy ? 'Đang tải dữ liệu…' : 'Làm mới kết quả'}
        </button>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ['Quảng cáo Active được quan sát trong 48h', integer(status?.unique_active_ads_observed_last_48h)],
          ['Sản phẩm trong Top 50', integer(status?.qualifying_products)],
          ['Sản phẩm tiềm năng', integer(research?.count)],
          ['Truy vấn của lượt gần nhất', integer(status?.searches_attempted)]
        ].map(([label, count]) => <div key={String(label)} className="bg-background rounded-xl border border-border p-4">
          <div className="text-2xl font-extrabold">{Number(count).toLocaleString('vi-VN')}</div>
          <div className="text-text-secondary text-xs mt-1">{label}</div>
        </div>)}
      </div>
      <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
        {status?.goal_completed ? 'Dữ liệu báo cáo đã đạt chỉ tiêu danh mục.' :
          'Chiến dịch CHƯA đạt đủ 50 sản phẩm/ngành. Một lần chạy thành công trên GitHub KHÔNG có nghĩa đã tìm đủ sản phẩm.'}
        {' '}21 mã quảng cáo Meta không phải 21 nhóm quảng cáo (ad sets). Số Active là quan sát từ lượt tìm kiếm, không phải kiểm chứng hoạt động theo thời gian thực ngay lúc bạn mở trang.
      </div>
      {error && <p className="rounded-xl bg-red-500/10 border border-red-500/30 p-3 text-red-300 text-sm">{error}</p>}
      {lastLoaded && <p className="text-text-secondary text-xs">Lần tải trang: {friendlyTime(new Date(lastLoaded).toISOString())}</p>}
    </section>
    <section className="rounded-2xl bg-surface border border-border p-5 space-y-3">
      <label className="font-semibold text-sm block" htmlFor="hunter-category">Lọc theo ngành hàng</label>
      <select id="hunter-category" value={category} onChange={e => setCategory(e.target.value)}
        className="bg-background text-white border border-border rounded-lg p-3 w-full max-w-sm">
        <option value="all">Tất cả ngành hàng</option>
        {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map(([value, label]) => <button key={value} onClick={() => setCategory(value)}
          className={'px-2.5 py-1.5 rounded-full text-xs border ' + (category === value ? 'bg-primary border-primary text-white' : 'border-border text-text-secondary')}>
          {label}: {integer(status?.category_qualified_counts?.[value])}/50
        </button>)}
        {category !== 'all' && <button className="text-primary text-sm underline" onClick={() => setCategory('all')}>Xóa bộ lọc</button>}
      </div>
    </section>
    <section className="space-y-3">
      <div className="flex items-end gap-3 justify-between">
        <h3 className="font-bold text-xl">Top 50 — Từ 21 quảng cáo Active được ghi nhận</h3>
        <span className="text-sm text-text-secondary">{qualified.length} sản phẩm</span>
      </div>
      {qualified.length === 0 && <p className="border border-border rounded-xl p-6 bg-surface text-text-secondary">
        Không có sản phẩm đạt ngưỡng trong danh mục đang chọn. Không tự thêm dữ liệu thiếu bằng chứng.
      </p>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {qualified.map((p, index) => {
          const purchase = safeUrl(p.product_url || p.ads?.find(a => safeUrl(a.landing_url))?.landing_url);
          const links = (p.ad_links || p.ads?.map(a => a.ad_url) || []).map(legitAdUrl).filter((x): x is string => Boolean(x));
          return <div className="bg-surface border border-emerald-500/30 rounded-xl p-5 space-y-3" key={(p.category || '') + '|' + p.name + index}>
            <div className="flex items-center gap-3">
              <span className="text-xl font-extrabold text-emerald-400">{integer(p.ad_count)} mã</span>
              <span className="text-xs text-emerald-300 border border-emerald-500/30 px-2 py-1 rounded">Đạt ngưỡng dữ liệu</span>
            </div>
            <h4 className="text-lg font-bold capitalize">{p.name}</h4>
            <p className="text-xs text-text-secondary">{p.category} · {integer(p.advertiser_count)} nhà quảng cáo ghi nhận</p>
            <div className="flex flex-wrap gap-3 text-sm">
              {purchase && <a className="underline text-primary" href={purchase} target="_blank" rel="noopener noreferrer">Xem trang sản phẩm</a>}
              {links.slice(0, 5).map((link, i) => <a key={link + i} className="underline text-sky-400" href={link} target="_blank" rel="noopener noreferrer">Quảng cáo {i + 1}</a>)}
            </div>
            <p className="text-xs text-text-secondary">Cùng URL sản phẩm theo dữ liệu quét. Cần kiểm tra thủ công trước khi kết luận chính xác tuyệt đối.</p>
          </div>;
        })}
      </div>
    </section>
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <h3 className="font-bold text-xl">Sản phẩm đang nghiên cứu (không thuộc Top 50)</h3>
        <span className="text-sm text-text-secondary">{candidates.length} sản phẩm hiển thị</span>
      </div>
      {candidates.length === 0 && <p className="border border-border rounded-xl p-6 bg-surface text-text-secondary">Chưa có danh sách sản phẩm nghiên cứu từ nguồn dữ liệu này.</p>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {candidates.map((p, index) => {
          const purchase = safeUrl(p.product_url);
          const links = (p.sample_ad_links || []).map(legitAdUrl).filter((x): x is string => Boolean(x));
          return <article key={(purchase || p.name) + index} className="bg-surface border border-border rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h4 className="text-base font-semibold capitalize">{p.name}</h4>
              <span className="shrink-0 text-xs font-bold text-amber-300">{integer(p.observed_ad_ids)}/21</span>
            </div>
            <div className="w-full h-2 rounded-full bg-background overflow-hidden">
              <div className="h-full bg-amber-500" style={{ width: Math.min(100, integer(p.observed_ad_ids) / 21 * 100) + '%' }} />
            </div>
            <p className="text-xs text-text-secondary">{p.category || 'other'} · {integer(p.observed_ad_ids) >= 21 ?
              'Đủ số mã quan sát, cần đối chiếu nhận diện sản phẩm và Top 50' :
              'Cần thêm ' + Math.max(0, 21 - integer(p.observed_ad_ids)) + ' mã Active hợp lệ'}</p>
            <div className="flex flex-wrap gap-3 text-xs">
              {purchase && <a className="text-primary underline" href={purchase} target="_blank" rel="noopener noreferrer">Xem sản phẩm</a>}
              {links.slice(0, 3).map((link, i) => <a className="text-sky-400 underline" key={link + i} href={link} target="_blank" rel="noopener noreferrer">Quảng cáo {i + 1}</a>)}
            </div>
          </article>;
        })}
      </div>
    </section>
    <p className="text-xs text-text-secondary pb-8">
      Đây là dữ liệu lưu ở nhánh thử nghiệm GitHub, không phải kết quả từ nút “Quét” của Daily Hunt, và không có thao tác quét trực tiếp từ màn hình này. Dữ liệu không cập nhật cho đến khi bộ quét GitHub chạy và lưu thành công.
    </p>
  </div>;
};
export default CloudHunter;
