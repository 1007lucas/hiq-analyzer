// 은행·카드 거래내역 파일(xlsx/xls/csv) → 표준 거래 배열
import { pad2 } from './format';

const HEADER_PATTERNS = {
  date: /거래\s*일|일시|일자|날짜|승인\s*일|이용\s*일|결제\s*일|사용\s*일|date/i,
  desc: /적요|내용|내역|가맹점|거래처|거래\s*구분|비고|메모|상호|사용처|보낸\s*분|받는\s*분|의뢰인|송금인|수취인|상대|거래\s*기관|description|merchant|memo/i,
  out: /출금|지출|사용\s*금액|승인\s*금액|이용\s*금액|결제\s*금액|청구\s*금액|withdraw|debit|출금액/i,
  in: /입금|수입|deposit|credit|입금액/i,
  amount: /^금액$|거래\s*금액|amount/i,
  balance: /잔액|balance/i,
};

export const ROLE_LABELS = { date: '날짜', desc: '내용(적요)', in: '입금액', out: '출금액', amount: '금액(부호)', skip: '사용 안 함' };

export async function readFileToRows(file) {
  const XLSX = await import('xlsx');
  const name = (file.name || '').toLowerCase();
  const buf = await file.arrayBuffer();
  let wb;
  if (/\.(csv|txt|tsv)$/.test(name)) {
    wb = XLSX.read(decodeText(buf), { type: 'string', raw: true });
  } else {
    wb = XLSX.read(buf, { type: 'array', cellDates: true });
  }
  const ws = wb.Sheets[wb.SheetNames[0]];
  if (!ws) throw new Error('시트를 찾을 수 없습니다.');
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: '' });
  return rows.filter((r) => r.some((c) => c !== '' && c !== null && c !== undefined));
}

function decodeText(buf) {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buf); }
  catch { return new TextDecoder('euc-kr').decode(buf); }
}

// 헤더 행 자동 탐지: 키워드가 가장 많이 맞는 행
export function detectHeader(rows) {
  let best = { idx: 0, score: 0 };
  const limit = Math.min(rows.length, 30);
  for (let i = 0; i < limit; i++) {
    const cells = rows[i].map((c) => String(c ?? '').trim());
    let score = 0;
    let hasDate = false;
    cells.forEach((c) => {
      if (!c || c.length > 20) return;
      if (HEADER_PATTERNS.date.test(c)) { score += 2; hasDate = true; }
      else if (HEADER_PATTERNS.out.test(c) || HEADER_PATTERNS.in.test(c) || HEADER_PATTERNS.amount.test(c)) score += 2;
      else if (HEADER_PATTERNS.desc.test(c) || HEADER_PATTERNS.balance.test(c)) score += 1;
    });
    if (hasDate && score > best.score) best = { idx: i, score };
  }
  return best.score >= 3 ? best.idx : -1;
}

// 열 역할 자동 배정 → { colIndex: role }
export function autoMapColumns(headerCells) {
  const map = {};
  const cells = headerCells.map((c) => String(c ?? '').trim());
  const taken = new Set();
  const pick = (role, re, multi = false) => {
    cells.forEach((c, i) => {
      if (!c || taken.has(i)) return;
      if (re.test(c)) {
        if (!multi && Object.values(map).includes(role)) return;
        map[i] = role; taken.add(i);
      }
    });
  };
  pick('date', HEADER_PATTERNS.date);
  // 잔액은 먼저 제외
  cells.forEach((c, i) => { if (HEADER_PATTERNS.balance.test(c)) { map[i] = 'skip'; taken.add(i); } });
  pick('out', HEADER_PATTERNS.out);
  pick('in', HEADER_PATTERNS.in);
  if (!Object.values(map).includes('out') && !Object.values(map).includes('in')) pick('amount', HEADER_PATTERNS.amount);
  pick('desc', HEADER_PATTERNS.desc, true);
  return map;
}

export function parseDate(v) {
  if (v instanceof Date && !isNaN(v)) return `${v.getFullYear()}-${pad2(v.getMonth() + 1)}-${pad2(v.getDate())}`;
  if (typeof v === 'number') {
    // 엑셀 일련번호
    if (v > 20000 && v < 80000) {
      const d = new Date(Math.round((v - 25569) * 86400000));
      return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
    }
    v = String(v);
  }
  const s = String(v ?? '').trim();
  if (!s) return null;
  let m = s.match(/(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})/);
  if (m) return `${m[1]}-${pad2(m[2])}-${pad2(m[3])}`;
  m = s.match(/^(\d{4})(\d{2})(\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = s.match(/^(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})/);
  if (m) return `20${m[1]}-${pad2(m[2])}-${pad2(m[3])}`;
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); // MM/DD/YYYY
  if (m) return `${m[3]}-${pad2(m[1])}-${pad2(m[2])}`;
  return null;
}

export function parseAmount(v) {
  if (v === null || v === undefined || v === '') return 0;
  if (typeof v === 'number') return v;
  let s = String(v).replace(/[₩,원\s]/g, '');
  let neg = false;
  if (/^\(.*\)$/.test(s)) { neg = true; s = s.slice(1, -1); }
  if (s.startsWith('-')) { neg = true; s = s.slice(1); }
  if (s.startsWith('+')) s = s.slice(1);
  const n = parseFloat(s);
  if (Number.isNaN(n)) return 0;
  return neg ? -n : n;
}

export function cleanDesc(s) {
  return String(s ?? '').replace(/\s+/g, ' ').trim();
}

// rows + mapping → 거래 배열. options.flipSign: 금액 단일열이 모두 양수(카드 명세)일 때 지출로 취급
export function buildTransactions(rows, headerIdx, mapping, options = {}) {
  const roles = {};
  Object.entries(mapping).forEach(([i, role]) => {
    if (role === 'skip') return;
    (roles[role] ||= []).push(Number(i));
  });
  if (!roles.date) throw new Error('날짜 열을 지정해주세요.');
  if (!roles.in && !roles.out && !roles.amount) throw new Error('금액 열을 지정해주세요.');

  const out = [];
  for (let r = headerIdx + 1; r < rows.length; r++) {
    const row = rows[r];
    const date = parseDate(row[roles.date[0]]);
    if (!date) continue;
    let amount = 0;
    if (roles.in || roles.out) {
      const inc = (roles.in || []).reduce((a, i) => a + parseAmount(row[i]), 0);
      const exp = (roles.out || []).reduce((a, i) => a + parseAmount(row[i]), 0);
      amount = inc - Math.abs(exp);
    } else {
      amount = parseAmount(row[roles.amount[0]]);
      if (options.flipSign) amount = -amount;
    }
    if (!amount) continue;
    const descParts = (roles.desc || []).map((i) => cleanDesc(row[i])).filter(Boolean);
    const desc = [...new Set(descParts)].join(' / ') || '(내용 없음)';
    out.push({
      id: `${date}|${desc}|${amount}|${r}`,
      key: `${date}|${desc}|${amount}`,
      date,
      month: date.slice(0, 7),
      desc,
      amount: Math.round(amount),
      source: options.source || '',
      category: null,
    });
  }
  return out;
}

// 단일 금액열이 거의 모두 양수면 카드 명세(지출)로 추정
export function guessFlipSign(rows, headerIdx, mapping) {
  const amtCol = Object.entries(mapping).find(([, role]) => role === 'amount');
  if (!amtCol) return false;
  const idx = Number(amtCol[0]);
  let pos = 0, total = 0;
  for (let r = headerIdx + 1; r < rows.length; r++) {
    const n = parseAmount(rows[r][idx]);
    if (!n) continue;
    total++; if (n > 0) pos++;
  }
  return total > 0 && pos / total >= 0.95;
}
