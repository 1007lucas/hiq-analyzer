// 표지 디자이너 상수 — 판형, 용지, 팔레트, 폰트, 템플릿, 기본값

export const MM = 3.7795275591; // CSS px per mm (96dpi)

export const TRIMS = {
  '4x6':    { name: '4×6배판 188×257 (학원교재 표준)', w: 188, h: 257 },
  'B5':     { name: 'B5 182×257', w: 182, h: 257 },
  'A4':     { name: 'A4 210×297', w: 210, h: 297 },
  'crown':  { name: '크라운판 176×248', w: 176, h: 248 },
  'sinkuk': { name: '신국판 152×225', w: 152, h: 225 },
  'A5':     { name: '국판 / A5 148×210', w: 148, h: 210 },
  'custom': { name: '직접 입력', w: 0, h: 0 },
};

// 용지별 1장(2쪽) 두께(mm)
export const PAPERS = {
  '70g 모조지': 0.09,
  '80g 모조지': 0.10,
  '100g 모조지': 0.12,
  '120g 모조지': 0.14,
  '80g 중질지': 0.11,
};

export const PALETTES = [
  { key: 'navy',     name: '네이비 · 골드',     primary: '#1F3864', secondary: '#15264A', accent: '#B08A2E', bg: '#F8F7F3', ink: '#1A1A1A' },
  { key: 'green',    name: '딥 그린 · 크림',    primary: '#1E4D3A', secondary: '#123326', accent: '#C9A24A', bg: '#F6F3EA', ink: '#141414' },
  { key: 'burgundy', name: '버건디 · 아이보리', primary: '#6E1F2B', secondary: '#4A1119', accent: '#D4A95A', bg: '#F7F2EC', ink: '#1A1A1A' },
  { key: 'cobalt',   name: '코발트 · 화이트',   primary: '#1D4ED8', secondary: '#1E3A8A', accent: '#F59E0B', bg: '#FFFFFF', ink: '#0F172A' },
  { key: 'teal',     name: '틸 · 샌드',         primary: '#0F766E', secondary: '#134E4A', accent: '#F4A261', bg: '#FAF7F0', ink: '#111827' },
  { key: 'orange',   name: '오렌지 · 차콜',     primary: '#EA580C', secondary: '#9A3412', accent: '#1F2937', bg: '#FFFBF5', ink: '#111827' },
  { key: 'purple',   name: '퍼플 · 라벤더',     primary: '#5B21B6', secondary: '#3B0F7A', accent: '#E9A8FF', bg: '#FAF7FF', ink: '#1A1A1A' },
  { key: 'charcoal', name: '차콜 · 레드',       primary: '#2B2B2B', secondary: '#111111', accent: '#D7263D', bg: '#F4F4F2', ink: '#111111' },
];

export const FONTS = {
  notoSans:      { name: 'Noto Sans KR (고딕)',          css: "'Noto Sans KR', 'Malgun Gothic', sans-serif" },
  notoSerif:     { name: 'Noto Serif KR (명조)',         css: "'Noto Serif KR', 'Batang', serif" },
  blackHan:      { name: 'Black Han Sans (굵은 제목용)', css: "'Black Han Sans', 'Noto Sans KR', sans-serif" },
  nanumMyeongjo: { name: 'Nanum Myeongjo (나눔명조)',    css: "'Nanum Myeongjo', 'Batang', serif" },
  gothicA1:      { name: 'Gothic A1',                    css: "'Gothic A1', 'Noto Sans KR', sans-serif" },
  doHyeon:       { name: 'Do Hyeon (도현)',              css: "'Do Hyeon', 'Noto Sans KR', sans-serif" },
};

export const GOOGLE_FONTS_HREF =
  'https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@400;600;700;900&family=Black+Han+Sans&family=Nanum+Myeongjo:wght@400;700;800&family=Gothic+A1:wght@400;600;800;900&family=Do+Hyeon&display=swap';

export const TEMPLATES = [
  { key: 'academic', name: '아카데믹 클래식', desc: '상단 컬러 밴드 + 명조 제목. 교재의 정석' },
  { key: 'grid',     name: '모던 그리드',     desc: '큰 학년 숫자와 기하 블록. 깔끔한 고딕' },
  { key: 'bold',     name: '볼드 타이포',     desc: '전면 컬러 + 초대형 제목. 강한 인상' },
  { key: 'minimal',  name: '미니멀 라인',     desc: '여백과 가는 테두리. 단정한 고급감' },
  { key: 'gradient', name: '그라디언트',      desc: '그라디언트 + 곡선 도형. 현대적 느낌' },
  { key: 'dark',     name: '다크 프리미엄',   desc: '딥 다크 배경 + 골드 라인. 프리미엄' },
];

export const DEFAULT_DESIGN = {
  // 내용
  title: '내신 1등급\n구문 완성',
  subtitle: '교과서 지문 구문 분석 + 내신 기출 유형 완전 정복',
  series: 'HIQ 내신 완성 시리즈',
  level: '고2',
  subject: '영어 I',
  volume: 'Vol. 1',
  author: 'HIQ입시학원 영어교육연구소',
  publisher: 'HIQ 출판',
  edition: '2026 개정 교육과정 반영',
  tagline: '문장 구조가 보이면, 문제가 풀린다',
  badge: '내신 1등급',
  blurb: '교과서 본문을 문장 단위로 해부해 가정법·관계사·수동태·분사구문 등 내신 빈출 구문을 한눈에 정리했습니다. 학교별 기출 유형을 분석해 어법 선택형, 빈칸 추론, 서술형, 어순 배열 문제를 수록했으며, 모든 문제에 정답 근거와 오답 분석을 담았습니다.',
  features: '교과서 전 단원 문장별 구문 분석\n학교 내신 기출 유형 500제 수록\n정답 근거 + 오답 분석 상세 해설\n서술형·어순 배열 집중 훈련',
  isbn: '979-11-0000-000-0',
  addon: '53740',
  price: '정가 18,000원',
  contact: 'www.hiq-academy.co.kr  |  02-000-0000',

  // 판형
  trim: '4x6',
  customW: 188,
  customH: 257,
  bleed: 3,
  pages: 240,
  paper: '80g 모조지',
  spineOverride: '',
  marks: true,

  // 스타일
  template: 'academic',
  palette: 'navy',
  customPrimary: '',
  customAccent: '',
  titleFont: 'notoSerif',
  bodyFont: 'notoSans',
  titleScale: 1,
};

export function getPalette(d) {
  const base = PALETTES.find(p => p.key === d.palette) || PALETTES[0];
  const p = { ...base };
  if (/^#[0-9a-f]{6}$/i.test(d.customPrimary || '')) p.primary = d.customPrimary;
  if (/^#[0-9a-f]{6}$/i.test(d.customAccent || '')) p.accent = d.customAccent;
  return p;
}

export function getTrim(d) {
  if (d.trim === 'custom') {
    return { w: Math.max(80, Number(d.customW) || 188), h: Math.max(80, Number(d.customH) || 257) };
  }
  const t = TRIMS[d.trim] || TRIMS['4x6'];
  return { w: t.w, h: t.h };
}

export function getSpine(d) {
  const o = Number(d.spineOverride);
  if (d.spineOverride !== '' && !Number.isNaN(o) && o > 0) return Math.round(o * 2) / 2;
  const per = PAPERS[d.paper] ?? 0.10;
  const pages = Math.max(0, Number(d.pages) || 0);
  const s = (pages / 2) * per + 0.6; // + 표지 두께
  return Math.max(3, Math.round(s * 2) / 2);
}

/** 색상 밝기 (0~1) — 글자색 자동 결정용 */
export function luminance(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return 1;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

export function hexToRgba(hex, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return `rgba(0,0,0,${a})`;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
