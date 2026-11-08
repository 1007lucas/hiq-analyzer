// 학원 인사 관리 데이터 저장소
// - 브라우저 localStorage 에 저장 (서버/DB 없이 Vercel 배포만으로 동작)
// - JSON 백업/복원 지원
import { useSyncExternalStore } from 'react';

export const STORAGE_KEY = 'hiq-hr-v1';

export const POSITIONS = ['원장', '부원장', '강사', '상담실장', '행정', '기타'];
export const EMP_TYPES = ['정규직', '계약직', '시간강사', '프리랜서'];
export const EMP_STATUS = ['재직', '휴직', '퇴직'];
export const PAY_TYPES = ['월급제', '시급제'];
export const WORK_STATUS = ['정상', '지각', '조퇴', '결근', '휴가', '외근'];
export const LEAVE_TYPES = ['연차', '반차', '병가', '경조사', '무급휴가', '기타'];
export const LEAVE_STATUS = ['대기', '승인', '반려'];
export const CONTRACT_TYPES = ['근로계약', '위촉계약(프리랜서)', '용역계약', '비밀유지계약', '기타'];
export const DAYS = ['월', '화', '수', '목', '금', '토', '일'];

export const DEFAULT_SETTINGS = Object.freeze({
  academyName: 'HIQ입시학원',
  workStart: '13:00',
  workEnd: '22:00',
  defaultAnnualLeave: 15,
  rates: { pension: 4.5, health: 3.545, care: 12.95, employment: 0.9, freelancerTax: 3.3 },
});

const EMPTY = Object.freeze({
  employees: [],
  attendance: [],
  leaves: [],
  payrolls: [],
  contracts: [],
  settings: DEFAULT_SETTINGS,
});

let state = null;
const listeners = new Set();

function normalize(s) {
  return { ...EMPTY, ...s, settings: { ...DEFAULT_SETTINGS, ...(s?.settings || {}), rates: { ...DEFAULT_SETTINGS.rates, ...(s?.settings?.rates || {}) } } };
}
function load() {
  if (state) return state;
  if (typeof window === 'undefined') return EMPTY;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    state = raw ? normalize(JSON.parse(raw)) : normalize({});
  } catch { state = normalize({}); }
  return state;
}
function persist() {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch {}
  listeners.forEach((l) => l());
}
export function getState() { return load(); }
export function setState(updater) {
  const next = typeof updater === 'function' ? updater(load()) : updater;
  state = normalize(next);
  persist();
}
export function subscribe(l) { listeners.add(l); return () => listeners.delete(l); }
export function useAcademy() { return useSyncExternalStore(subscribe, getState, () => EMPTY); }

// ── 공용 유틸 ──
export function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function thisMonth() { return today().slice(0, 7); }
export function thisYear() { return today().slice(0, 4); }
export function weekdayOf(dateStr) { const d = new Date(dateStr + 'T00:00:00'); return DAYS[(d.getDay() + 6) % 7]; }
export function addDays(dateStr, n) { const d = new Date(dateStr + 'T00:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }
export function daysBetween(a, b) { return Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000); }
export function monthDates(month) {
  const [y, m] = month.split('-').map(Number);
  const n = new Date(y, m, 0).getDate();
  return Array.from({ length: n }, (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`);
}
export function fmtMoney(n) { return Math.round(Number(n) || 0).toLocaleString('ko-KR') + '원'; }
export function fmtNum(n) { return Math.round(Number(n) || 0).toLocaleString('ko-KR'); }
export function fmtPhone(p) {
  const d = String(p || '').replace(/\D/g, '');
  if (d.length === 11) return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
  return p || '';
}
export function toMin(t) { if (!t) return null; const [h, m] = t.split(':').map(Number); return h * 60 + m; }
export function workHours(checkIn, checkOut, breakMin = 0) {
  const a = toMin(checkIn), b = toMin(checkOut);
  if (a == null || b == null || b <= a) return 0;
  return Math.max(0, (b - a - breakMin) / 60);
}
export function yearsOfService(hireDate, until = today()) {
  if (!hireDate) return '';
  const d = daysBetween(hireDate, until);
  if (d < 0) return '';
  const y = Math.floor(d / 365), m = Math.floor((d % 365) / 30);
  return y ? `${y}년 ${m}개월` : `${m}개월`;
}

// ── CRUD ──
export function addItem(col, item) {
  const row = { id: uid(), createdAt: new Date().toISOString(), ...item };
  setState((s) => ({ ...s, [col]: [...s[col], row] }));
  return row;
}
export function updateItem(col, id, patch) {
  setState((s) => ({ ...s, [col]: s[col].map((r) => (r.id === id ? { ...r, ...patch } : r)) }));
}
export function removeItem(col, id) {
  setState((s) => ({ ...s, [col]: s[col].filter((r) => r.id !== id) }));
}
export function updateSettings(patch) {
  setState((s) => ({ ...s, settings: { ...s.settings, ...patch } }));
}
export function removeEmployeeCascade(id) {
  setState((s) => ({
    ...s,
    employees: s.employees.filter((r) => r.id !== id),
    attendance: s.attendance.filter((r) => r.employeeId !== id),
    leaves: s.leaves.filter((r) => r.employeeId !== id),
    payrolls: s.payrolls.filter((r) => r.employeeId !== id),
    contracts: s.contracts.filter((r) => r.employeeId !== id),
  }));
}

// 근태: 같은 날짜·직원은 하나만 (upsert)
export function upsertWork(date, employeeId, patch) {
  setState((s) => {
    const idx = s.attendance.findIndex((r) => r.date === date && r.employeeId === employeeId);
    if (idx === -1) return { ...s, attendance: [...s.attendance, { id: uid(), date, employeeId, checkIn: '', checkOut: '', status: '정상', note: '', ...patch }] };
    const next = [...s.attendance];
    next[idx] = { ...next[idx], ...patch };
    return { ...s, attendance: next };
  });
}
export function removeWork(date, employeeId) {
  setState((s) => ({ ...s, attendance: s.attendance.filter((r) => !(r.date === date && r.employeeId === employeeId)) }));
}

// ── 파생 계산 ──
// 휴가 일수: 일요일 제외, 반차는 0.5
export function calcLeaveDays(type, start, end) {
  if (!start) return 0;
  if (type === '반차') return 0.5;
  const e = end || start;
  const n = daysBetween(start, e);
  if (n < 0) return 0;
  let cnt = 0;
  for (let i = 0; i <= n; i++) if (weekdayOf(addDays(start, i)) !== '일') cnt++;
  return cnt;
}
// 연차 잔여 (해당 연도)
export function leaveBalance(emp, leaves, year, settings) {
  const total = Number(emp.annualLeave ?? settings.defaultAnnualLeave) || 0;
  const used = leaves.filter((l) => l.employeeId === emp.id && l.status === '승인' && ['연차', '반차'].includes(l.type) && (l.start || '').startsWith(year))
    .reduce((s, l) => s + (Number(l.days) || 0), 0);
  return { total, used, left: total - used };
}
// 월 근무시간 합계
export function monthHours(attendance, employeeId, month) {
  return attendance.filter((a) => a.employeeId === employeeId && a.date.startsWith(month)).reduce((s, a) => s + (Number(a.hours) || 0), 0);
}
// 급여 공제 계산
export function calcDeductions(emp, gross, rates, incomeTax = 0, otherDeduction = 0) {
  const r = rates;
  const g = Number(gross) || 0;
  const floor10 = (v) => Math.floor(v / 10) * 10;
  let d = { pension: 0, health: 0, care: 0, employment: 0, incomeTax: 0, localTax: 0, other: Number(otherDeduction) || 0 };
  if (emp.empType === '프리랜서') {
    d.incomeTax = floor10(g * (r.freelancerTax / 1.1) / 100); // 3%
    d.localTax = floor10(d.incomeTax * 0.1);                   // 0.3%
  } else {
    if (emp.insured) {
      d.pension = floor10(g * r.pension / 100);
      d.health = floor10(g * r.health / 100);
      d.care = floor10(d.health * r.care / 100);
      d.employment = floor10(g * r.employment / 100);
    }
    d.incomeTax = Math.round(Number(incomeTax) || 0);
    d.localTax = floor10(d.incomeTax * 0.1);
  }
  d.total = d.pension + d.health + d.care + d.employment + d.incomeTax + d.localTax + d.other;
  return d;
}
export function contractState(c, t = today()) {
  if (c.status === '해지') return '해지';
  if (c.end && c.end < t) return '만료';
  if (c.end && daysBetween(t, c.end) <= 30) return '만료임박';
  return '진행중';
}

// ── 백업 / 복원 ──
export function exportJSON() {
  const data = JSON.stringify(getState(), null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `hr-backup-${today()}.json`; a.click();
  URL.revokeObjectURL(url);
}
export function importJSON(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.employees)) throw new Error('형식이 올바르지 않습니다.');
        setState(parsed); resolve();
      } catch (e) { reject(e); }
    };
    reader.onerror = () => reject(new Error('파일을 읽을 수 없습니다.'));
    reader.readAsText(file);
  });
}
export function resetAll() { setState({}); }

// ── 샘플 데이터 ──
export function loadSample() {
  const e = Array.from({ length: 6 }, () => uid());
  const m = thisMonth(), d = today(), y = thisYear();
  const emp = (id, o) => ({ id, phone: '', email: '', subject: '', leaveDate: '', bank: '', account: '', memo: '', birth: '', annualLeave: 15, insured: true, ...o });
  setState({
    settings: { ...DEFAULT_SETTINGS },
    employees: [
      emp(e[0], { name: '김원장', position: '원장', empType: '정규직', subject: '영어', phone: '01011110001', email: 'kim@hiq.kr', hireDate: '2019-03-01', status: '재직', payType: '월급제', baseSalary: 5000000, hourlyRate: 0, bank: '국민', account: '123-45-67890' }),
      emp(e[1], { name: '이영어', position: '강사', empType: '정규직', subject: '영어', phone: '01011110002', email: 'lee@hiq.kr', hireDate: '2022-03-02', status: '재직', payType: '월급제', baseSalary: 3200000, hourlyRate: 0, bank: '신한', account: '110-222-333333' }),
      emp(e[2], { name: '박수학', position: '강사', empType: '계약직', subject: '수학', phone: '01011110003', email: 'park@hiq.kr', hireDate: '2024-09-01', status: '재직', payType: '월급제', baseSalary: 2900000, hourlyRate: 0, bank: '우리', account: '1002-333-444444' }),
      emp(e[3], { name: '최국어', position: '강사', empType: '시간강사', subject: '국어', phone: '01011110004', hireDate: '2025-03-03', status: '재직', payType: '시급제', baseSalary: 0, hourlyRate: 40000, insured: false, annualLeave: 0, bank: '카카오', account: '3333-01-555555' }),
      emp(e[4], { name: '정과학', position: '강사', empType: '프리랜서', subject: '과학', phone: '01011110005', hireDate: '2025-06-01', status: '재직', payType: '월급제', baseSalary: 2400000, hourlyRate: 0, insured: false, annualLeave: 0, bank: '하나', account: '555-666-777777' }),
      emp(e[5], { name: '한행정', position: '행정', empType: '정규직', phone: '01011110006', email: 'han@hiq.kr', hireDate: '2023-01-16', status: '재직', payType: '월급제', baseSalary: 2600000, hourlyRate: 0, bank: '농협', account: '301-0000-1111-11' }),
    ],
    attendance: [
      { id: uid(), employeeId: e[0], date: d, checkIn: '12:50', checkOut: '', status: '정상', hours: 0, note: '' },
      { id: uid(), employeeId: e[1], date: d, checkIn: '13:12', checkOut: '', status: '지각', hours: 0, note: '병원 진료' },
      { id: uid(), employeeId: e[3], date: addDays(d, -2), checkIn: '16:00', checkOut: '21:00', status: '정상', hours: 5, note: '' },
      { id: uid(), employeeId: e[3], date: addDays(d, -4), checkIn: '16:00', checkOut: '21:00', status: '정상', hours: 5, note: '' },
      { id: uid(), employeeId: e[3], date: addDays(d, -7), checkIn: '16:00', checkOut: '20:00', status: '조퇴', hours: 4, note: '' },
    ],
    leaves: [
      { id: uid(), employeeId: e[1], type: '연차', start: addDays(d, 5), end: addDays(d, 6), days: 2, reason: '가족 여행', status: '대기', createdAt: new Date().toISOString() },
      { id: uid(), employeeId: e[2], type: '반차', start: addDays(d, -10), end: addDays(d, -10), days: 0.5, reason: '개인 사정', status: '승인', createdAt: new Date().toISOString() },
      { id: uid(), employeeId: e[5], type: '연차', start: `${y}-05-02`, end: `${y}-05-03`, days: 2, reason: '', status: '승인', createdAt: new Date().toISOString() },
    ],
    payrolls: [
      { id: uid(), employeeId: e[1], month: m, payType: '월급제', baseAmount: 3200000, hours: 0, hourlyRate: 0, allowance: 200000, bonus: 0, incomeTax: 95000, otherDeduction: 0, status: '지급완료', paidDate: `${m}-10`, memo: '내신 특강 수당 포함' },
      { id: uid(), employeeId: e[4], month: m, payType: '월급제', baseAmount: 2400000, hours: 0, hourlyRate: 0, allowance: 0, bonus: 0, incomeTax: 0, otherDeduction: 0, status: '미지급', paidDate: '', memo: '' },
    ],
    contracts: [
      { id: uid(), employeeId: e[1], type: '근로계약', start: '2025-03-01', end: '', payTerms: '월 3,200,000원 / 주 5일 13:00~22:00', insured: true, memo: '기간의 정함이 없는 근로계약', status: '진행중' },
      { id: uid(), employeeId: e[2], type: '근로계약', start: `${Number(y) - 1}-09-01`, end: addDays(d, 20), payTerms: '월 2,900,000원 / 1년 계약', insured: true, memo: '재계약 협의 필요', status: '진행중' },
      { id: uid(), employeeId: e[3], type: '근로계약', start: '2025-03-03', end: `${y}-12-31`, payTerms: '시급 40,000원 / 주 3일', insured: false, memo: '', status: '진행중' },
      { id: uid(), employeeId: e[4], type: '위촉계약(프리랜서)', start: '2025-06-01', end: `${Number(y) + 1}-05-31`, payTerms: '월 2,400,000원 (3.3% 원천징수)', insured: false, memo: '', status: '진행중' },
      { id: uid(), employeeId: e[0], type: '비밀유지계약', start: '2019-03-01', end: '', payTerms: '', insured: false, memo: '', status: '진행중' },
    ],
  });
}
