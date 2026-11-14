// 숫자·날짜 표시 유틸
export const won = (n, opts = {}) => {
  if (n === null || n === undefined || Number.isNaN(n)) return '-';
  const v = Math.round(n);
  const s = Math.abs(v).toLocaleString('ko-KR');
  const sign = v < 0 ? '-' : (opts.plus && v > 0 ? '+' : '');
  return `${sign}${s}원`;
};

export const wonShort = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return '-';
  const v = Math.round(n);
  const a = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (a >= 100000000) return `${sign}${(a / 100000000).toFixed(a % 100000000 === 0 ? 0 : 1)}억`;
  if (a >= 10000) return `${sign}${Math.round(a / 10000).toLocaleString('ko-KR')}만`;
  return `${sign}${a.toLocaleString('ko-KR')}`;
};

export const pct = (part, whole) => (!whole ? 0 : Math.round((part / whole) * 100));

export const pad2 = (n) => String(n).padStart(2, '0');

export const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
};

export const thisMonth = () => todayISO().slice(0, 7);

export const monthLabel = (ym) => {
  if (!ym) return '';
  const [y, m] = ym.split('-');
  return `${y}년 ${Number(m)}월`;
};

export const shiftMonth = (ym, delta) => {
  const [y, m] = ym.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
};

export const lastNMonths = (n, endYm = thisMonth()) => {
  const out = [];
  for (let i = n - 1; i >= 0; i--) out.push(shiftMonth(endYm, -i));
  return out;
};

export const daysBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);

export const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
