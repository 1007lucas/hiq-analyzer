// 학원 관리 데이터 저장소
// - 브라우저 localStorage 에 저장 (서버/DB 없이 Vercel 배포만으로 동작)
// - JSON 백업/복원 지원
import { useSyncExternalStore } from 'react';

export const STORAGE_KEY = 'hiq-academy-v1';

export const GRADES = ['초1','초2','초3','초4','초5','초6','중1','중2','중3','고1','고2','고3','기타'];
export const DAYS = ['월','화','수','목','금','토','일'];
export const STUDENT_STATUS = ['재원','휴원','퇴원'];
export const TEACHER_STATUS = ['재직','휴직','퇴직'];
export const ATT_STATUS = ['출석','지각','결석','조퇴'];
export const PAY_METHODS = ['계좌이체','카드','현금','기타'];
export const COUNSEL_TYPES = ['학부모 상담','학생 상담','입학 상담','정기 상담','기타'];

const EMPTY = Object.freeze({
  students: [],
  classes: [],
  teachers: [],
  attendance: [],
  payments: [],
  counseling: [],
  settings: { academyName: 'HIQ입시학원' },
});

let state = null;
const listeners = new Set();

function load() {
  if (state) return state;
  if (typeof window === 'undefined') return EMPTY;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    state = raw ? { ...EMPTY, ...JSON.parse(raw) } : { ...EMPTY };
  } catch {
    state = { ...EMPTY };
  }
  return state;
}

function persist() {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch {}
  listeners.forEach((l) => l());
}

export function getState() { return load(); }

export function setState(updater) {
  const next = typeof updater === 'function' ? updater(load()) : updater;
  state = { ...EMPTY, ...next };
  persist();
}

export function subscribe(l) { listeners.add(l); return () => listeners.delete(l); }

export function useAcademy() {
  return useSyncExternalStore(subscribe, getState, () => EMPTY);
}

// ── 공용 유틸 ──
export function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function thisMonth() { return today().slice(0, 7); }
export function weekdayOf(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return DAYS[(d.getDay() + 6) % 7];
}
export function fmtMoney(n) { return (Number(n) || 0).toLocaleString('ko-KR') + '원'; }
export function fmtPhone(p) {
  const d = String(p || '').replace(/\D/g, '');
  if (d.length === 11) return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
  return p || '';
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

// 학생 삭제 시 관련 출결·수납·상담도 함께 정리
export function removeStudentCascade(id) {
  setState((s) => ({
    ...s,
    students: s.students.filter((r) => r.id !== id),
    attendance: s.attendance.filter((r) => r.studentId !== id),
    payments: s.payments.filter((r) => r.studentId !== id),
    counseling: s.counseling.filter((r) => r.studentId !== id),
  }));
}
// 반 삭제 시 학생의 수강반 목록에서도 제거
export function removeClassCascade(id) {
  setState((s) => ({
    ...s,
    classes: s.classes.filter((r) => r.id !== id),
    students: s.students.map((st) => ({ ...st, classIds: (st.classIds || []).filter((c) => c !== id) })),
    attendance: s.attendance.filter((r) => r.classId !== id),
  }));
}

// 출결 기록: 같은 날짜·반·학생은 하나만
export function setAttendance(date, classId, studentId, status, note) {
  setState((s) => {
    const rest = s.attendance.filter((r) => !(r.date === date && r.classId === classId && r.studentId === studentId));
    if (!status) return { ...s, attendance: rest };
    return { ...s, attendance: [...rest, { id: uid(), date, classId, studentId, status, note: note || '' }] };
  });
}

// ── 파생 데이터 ──
export function studentFee(student, classes) {
  return (student.classIds || []).reduce((sum, cid) => {
    const c = classes.find((k) => k.id === cid);
    return sum + (c ? Number(c.fee) || 0 : 0);
  }, 0);
}
export function paymentStatus(p) {
  const paid = Number(p.paidAmount) || 0;
  const due = Number(p.amount) || 0;
  if (due > 0 && paid >= due) return '완납';
  if (paid > 0) return '부분납';
  return '미납';
}

// ── 백업 / 복원 ──
export function exportJSON() {
  const data = JSON.stringify(getState(), null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `academy-backup-${today()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
export function importJSON(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.students)) throw new Error('형식이 올바르지 않습니다.');
        setState({ ...EMPTY, ...parsed });
        resolve();
      } catch (e) { reject(e); }
    };
    reader.onerror = () => reject(new Error('파일을 읽을 수 없습니다.'));
    reader.readAsText(file);
  });
}
export function resetAll() { setState({ ...EMPTY }); }

// ── 샘플 데이터 ──
export function loadSample() {
  const t1 = uid(), t2 = uid();
  const c1 = uid(), c2 = uid(), c3 = uid();
  const s = Array.from({ length: 8 }, () => uid());
  const m = thisMonth();
  const d = today();
  setState({
    ...EMPTY,
    settings: { academyName: 'HIQ입시학원' },
    teachers: [
      { id: t1, name: '김영어', phone: '01011112222', subjects: '영어', hireDate: '2023-03-01', status: '재직', memo: '' },
      { id: t2, name: '박수학', phone: '01033334444', subjects: '수학', hireDate: '2024-01-15', status: '재직', memo: '' },
    ],
    classes: [
      { id: c1, name: '고1 영어 내신A', subject: '영어', teacherId: t1, days: ['월', '수'], time: '16:00~17:30', fee: 250000, room: '1강의실', capacity: 10 },
      { id: c2, name: '고2 영어 내신B', subject: '영어', teacherId: t1, days: ['화', '목'], time: '18:00~19:30', fee: 280000, room: '1강의실', capacity: 10 },
      { id: c3, name: '중3 수학 심화', subject: '수학', teacherId: t2, days: ['월', '수', '금'], time: '19:40~21:00', fee: 300000, room: '2강의실', capacity: 8 },
    ],
    students: [
      { id: s[0], name: '이서연', school: '하이고', grade: '고1', phone: '01055550001', parentPhone: '01066660001', classIds: [c1], status: '재원', joinDate: '2025-03-02', memo: '' },
      { id: s[1], name: '김민준', school: '하이고', grade: '고1', phone: '01055550002', parentPhone: '01066660002', classIds: [c1], status: '재원', joinDate: '2025-03-02', memo: '' },
      { id: s[2], name: '박지우', school: '중앙고', grade: '고2', phone: '01055550003', parentPhone: '01066660003', classIds: [c2], status: '재원', joinDate: '2025-06-10', memo: '모의고사 2등급' },
      { id: s[3], name: '최하은', school: '중앙고', grade: '고2', phone: '01055550004', parentPhone: '01066660004', classIds: [c2], status: '재원', joinDate: '2025-06-10', memo: '' },
      { id: s[4], name: '정도윤', school: '하이중', grade: '중3', phone: '01055550005', parentPhone: '01066660005', classIds: [c3], status: '재원', joinDate: '2025-09-01', memo: '' },
      { id: s[5], name: '강수아', school: '하이중', grade: '중3', phone: '01055550006', parentPhone: '01066660006', classIds: [c3, c1], status: '재원', joinDate: '2025-09-01', memo: '영어·수학 병행' },
      { id: s[6], name: '윤시우', school: '중앙중', grade: '중3', phone: '01055550007', parentPhone: '01066660007', classIds: [c3], status: '휴원', joinDate: '2025-01-05', memo: '11월까지 휴원' },
      { id: s[7], name: '임지호', school: '하이고', grade: '고1', phone: '01055550008', parentPhone: '01066660008', classIds: [], status: '퇴원', joinDate: '2024-03-01', memo: '' },
    ],
    attendance: [
      { id: uid(), date: d, classId: c1, studentId: s[0], status: '출석', note: '' },
      { id: uid(), date: d, classId: c1, studentId: s[1], status: '지각', note: '10분 지각' },
    ],
    payments: [
      { id: uid(), studentId: s[0], month: m, amount: 250000, paidAmount: 250000, paidDate: `${m}-03`, method: '계좌이체', memo: '' },
      { id: uid(), studentId: s[1], month: m, amount: 250000, paidAmount: 0, paidDate: '', method: '', memo: '' },
      { id: uid(), studentId: s[2], month: m, amount: 280000, paidAmount: 280000, paidDate: `${m}-05`, method: '카드', memo: '' },
      { id: uid(), studentId: s[3], month: m, amount: 280000, paidAmount: 100000, paidDate: `${m}-07`, method: '현금', memo: '잔액 추후 납부' },
      { id: uid(), studentId: s[4], month: m, amount: 300000, paidAmount: 0, paidDate: '', method: '', memo: '' },
      { id: uid(), studentId: s[5], month: m, amount: 550000, paidAmount: 550000, paidDate: `${m}-02`, method: '계좌이체', memo: '' },
    ],
    counseling: [
      { id: uid(), studentId: s[2], date: d, type: '학부모 상담', content: '내신 대비 계획 안내. 어법 파트 보강 요청.', followUp: '' },
      { id: uid(), studentId: s[4], date: d, type: '학생 상담', content: '수학 심화 진도 부담 호소. 숙제량 조정.', followUp: d },
    ],
  });
}
