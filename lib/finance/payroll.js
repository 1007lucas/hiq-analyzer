// 강사 급여 계산 (3.3% 사업소득 / 4대보험 근로자 간이 추정)
export const DEFAULT_RATES = {
  pension: 4.5,        // 국민연금 근로자 부담 (%)
  pensionCap: 6370000, // 국민연금 기준소득월액 상한 (원) — 매년 7월 변경, 수정 가능
  health: 3.545,       // 건강보험 근로자 부담 (%)
  care: 12.95,         // 장기요양 (건강보험료 대비 %)
  employment: 0.9,     // 고용보험 근로자 부담 (%)
};

const floor10 = (n) => Math.floor(n / 10) * 10;

export function calcPay(inst, month, rates = DEFAULT_RATES) {
  const hours = Number(inst.hours?.[month] ?? 0);
  const gross = inst.payMode === 'hourly' ? Math.round(Number(inst.rate || 0) * hours) : Math.round(Number(inst.rate || 0));
  const extra = Math.round(Number(inst.extra?.[month] ?? 0)); // 추가 수당·인센티브
  const base = gross + extra;
  if (inst.type === 'freelancer') {
    const incomeTax = floor10(base * 0.03);
    const localTax = floor10(incomeTax * 0.1);
    return { gross, extra, base, deductions: [['소득세 3%', incomeTax], ['지방소득세 0.3%', localTax]], totalDeduction: incomeTax + localTax, net: base - incomeTax - localTax, withheld: incomeTax + localTax, hours };
  }
  const pensionBase = Math.min(base, rates.pensionCap);
  const pension = floor10(pensionBase * rates.pension / 100);
  const health = floor10(base * rates.health / 100);
  const care = floor10(health * rates.care / 100);
  const employment = floor10(base * rates.employment / 100);
  const incomeTax = Math.round(Number(inst.incomeTax?.[month] ?? 0));
  const localTax = floor10(incomeTax * 0.1);
  const list = [['국민연금', pension], ['건강보험', health], ['장기요양', care], ['고용보험', employment], ['소득세(간이세액)', incomeTax], ['지방소득세', localTax]];
  const total = list.reduce((a, [, v]) => a + v, 0);
  return { gross, extra, base, deductions: list, totalDeduction: total, net: base - total, withheld: incomeTax + localTax, hours };
}
