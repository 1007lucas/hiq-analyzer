// 반복 결제(구독·고정지출) 탐지
import { normalizeDesc } from './rules';
import { daysBetween } from './format';

const median = (arr) => {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export function detectRecurring(transactions, { today = new Date() } = {}) {
  const groups = new Map();
  for (const tx of transactions) {
    if (tx.amount >= 0) continue;
    const k = normalizeDesc(tx.desc);
    if (k.length < 2) continue;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(tx);
  }
  const out = [];
  for (const [key, list] of groups) {
    if (list.length < 2) continue;
    list.sort((a, b) => a.date.localeCompare(b.date));
    const months = new Set(list.map((t) => t.month));
    if (months.size < 2) continue;
    const amounts = list.map((t) => Math.abs(t.amount));
    const med = median(amounts);
    if (!med) continue;
    const stable = amounts.filter((a) => Math.abs(a - med) / med <= 0.2).length / amounts.length;
    if (stable < 0.6) continue;
    const gaps = [];
    for (let i = 1; i < list.length; i++) gaps.push(daysBetween(list[i - 1].date, list[i].date));
    const g = median(gaps.filter((x) => x > 0));
    let interval = null;
    if (g >= 25 && g <= 36) interval = 'monthly';
    else if (g >= 6 && g <= 8) interval = 'weekly';
    else if (g >= 355 && g <= 375) interval = 'yearly';
    else if (g >= 12 && g <= 16) interval = 'biweekly';
    if (!interval) continue;
    const last = list[list.length - 1];
    const sinceLast = daysBetween(last.date, today);
    const expected = { monthly: 31, weekly: 7, biweekly: 14, yearly: 365 }[interval];
    const active = sinceLast <= expected * 1.6;
    const monthly = { monthly: med, weekly: med * 4.33, biweekly: med * 2.17, yearly: med / 12 }[interval];
    out.push({
      key,
      name: last.desc,
      amount: med,
      monthlyCost: Math.round(monthly),
      interval,
      count: list.length,
      firstDate: list[0].date,
      lastDate: last.date,
      active,
      category: last.category || null,
      months: [...months].sort(),
    });
  }
  return out.sort((a, b) => b.monthlyCost - a.monthlyCost);
}

export const INTERVAL_LABEL = { monthly: '매월', weekly: '매주', biweekly: '2주마다', yearly: '매년' };
