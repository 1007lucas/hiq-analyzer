// 학원(교육서비스업·면세사업자) 기준 세무·신고 일정
// 일반적인 기준이며 실제 신고 의무는 세무사 확인이 필요합니다.
import { pad2 } from './format';

const MONTH_NAMES = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];

function nextBusinessDay(y, m, d) {
  const dt = new Date(y, m - 1, d);
  // 말일 보정 (d=0 → 전월 말일 처리 방지)
  while (dt.getDay() === 0 || dt.getDay() === 6) dt.setDate(dt.getDate() + 1);
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
}
function lastDay(y, m) { return new Date(y, m, 0).getDate(); }

export function buildTaxCalendar(year, opts = {}) {
  const { halfYearWithholding = false, hasEmployees = true, hasTaxableSales = false, sincere = false } = opts;
  const ev = [];
  const add = (date, title, desc, docs, kind) => ev.push({ date, title, desc, docs, kind });

  for (let m = 1; m <= 12; m++) {
    const prev = m === 1 ? '12월' : MONTH_NAMES[m - 2];
    const isHalf = m === 1 || m === 7;
    if (!halfYearWithholding || isHalf) {
      add(nextBusinessDay(year, m, 10), '원천세 신고·납부',
        halfYearWithholding
          ? `반기(${m === 1 ? '7~12월' : '1~6월'}) 지급분 강사료(3.3%)·급여 원천징수세액 신고·납부`
          : `${prev} 지급분 강사료(3.3%)·급여 원천징수세액 신고·납부 (홈택스)`,
        ['강사별 지급액·원천징수액 내역', '급여대장', '홈택스 원천징수이행상황신고서'], 'withholding');
    }
    add(nextBusinessDay(year, m, lastDay(year, m)), '사업소득 간이지급명세서 제출',
      `${prev} 지급분 3.3% 사업소득(프리랜서 강사) 간이지급명세서 제출`,
      ['강사 주민번호·지급액·원천징수액', '홈택스 간이지급명세서(거주자의 사업소득)'], 'statement');
    if (hasEmployees) {
      add(nextBusinessDay(year, m, 10), '4대보험료 납부',
        `${prev}분 국민연금·건강보험·고용·산재보험료 고지 납부`,
        ['4대보험 고지서(사회보험통합징수포털)'], 'insurance');
    }
  }

  add(nextBusinessDay(year, 2, 10), '면세사업자 사업장현황신고',
    `${year - 1}년 수입금액·사업장 현황 신고 (학원 등 교육용역은 부가세 면세 → 부가세 신고 대신 이 신고)`,
    ['연간 수강료 수입 집계', '계산서·현금영수증·카드매출 집계', '사업장 기본현황(강사 수·강의실 등)'], 'annual');
  add(nextBusinessDay(year, 3, 10), '근로소득 지급명세서 제출 · 연말정산 마감',
    `${year - 1}년 4대보험 근로자 급여 지급명세서 제출, 연말정산 결과 반영`,
    ['근로소득 원천징수영수증', '연말정산 간소화 자료(직원 제출분)'], 'annual');
  add(nextBusinessDay(year, 5, 31), sincere ? '종합소득세 신고·납부 (성실신고확인 대상은 6/30)' : '종합소득세 신고·납부',
    `${year - 1}년 학원 사업소득 + 기타소득 합산 신고. 장부(간편장부/복식부기) 기준`,
    ['연간 수입·지출 장부', '적격증빙(세금계산서·카드·현금영수증)', '인건비 지급 내역', '임대차계약서·임대료 증빙', '사업소득 원천징수영수증(있을 경우)'], 'annual');
  if (sincere) add(nextBusinessDay(year, 6, 30), '성실신고확인서 제출 + 종합소득세 신고·납부',
    '성실신고확인 대상 사업자는 세무사 확인서를 첨부하여 6/30까지 신고', ['성실신고확인서(세무사 작성)'], 'annual');
  add(nextBusinessDay(year, 11, 30), '종합소득세 중간예납 납부',
    `${year}년 상반기분 중간예납 고지서 납부 (전년 납부세액의 1/2 기준, 소액은 고지 제외)`,
    ['중간예납 고지서(홈택스/우편)'], 'annual');
  add(nextBusinessDay(year, 7, 31), '재산세(건축물) 납부 — 학원 건물 소유 시',
    '건물을 소유한 경우에만 해당. 임차 시 해당 없음', ['재산세 고지서'], 'optional');
  if (hasTaxableSales) {
    add(nextBusinessDay(year, 1, 25), '부가가치세 확정신고 (과세 겸영 시)',
      `${year - 1}년 하반기 교재 판매 등 과세 매출분`, ['과세·면세 매출 구분 집계', '매입세금계산서'], 'vat');
    add(nextBusinessDay(year, 7, 25), '부가가치세 확정신고 (과세 겸영 시)',
      `${year}년 상반기 교재 판매 등 과세 매출분`, ['과세·면세 매출 구분 집계', '매입세금계산서'], 'vat');
  }

  return ev.sort((a, b) => a.date.localeCompare(b.date));
}

export const KIND_LABEL = {
  withholding: '원천세', statement: '지급명세서', insurance: '4대보험', annual: '연간 신고', optional: '해당 시', vat: '부가세',
};
