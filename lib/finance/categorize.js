// 분류 파이프라인: 기억된 규칙 → 키워드 규칙 → AI → 기본값
import { ruleCategory, defaultCategory, normalizeDesc } from './rules';
import { categorizeWithAI } from './ai';

export function applyMemory(domain, txs, memory) {
  return txs.map((t) => {
    if (t.category && t.locked) return t;
    const k = normalizeDesc(t.desc);
    if (memory[k]) return { ...t, category: memory[k], how: 'memory' };
    const rc = ruleCategory(domain, t);
    if (rc) return { ...t, category: rc, how: 'rule' };
    return { ...t, category: t.category || null, how: t.category ? t.how : null };
  });
}

// 미분류 거래를 AI로 분류하고, 결과를 기억(memory)에 저장
export async function runAI(domain, txs, categories, onProgress) {
  const pending = txs.filter((t) => !t.category);
  if (!pending.length) return { txs, memory: {}, count: 0 };
  const lookup = await categorizeWithAI(pending, categories, domain, onProgress);
  const memory = {};
  let count = 0;
  const out = txs.map((t) => {
    if (t.category) return t;
    const c = lookup(t);
    if (c) {
      count++;
      memory[normalizeDesc(t.desc)] = c;
      return { ...t, category: c, how: 'ai' };
    }
    return { ...t, category: defaultCategory(domain, t), how: 'default' };
  });
  return { txs: out, memory, count };
}

export function fillDefaults(domain, txs) {
  return txs.map((t) => (t.category ? t : { ...t, category: defaultCategory(domain, t), how: 'default' }));
}

// 월별 카테고리 합계
export function summarize(txs, month, isIncome) {
  const income = {}, expense = {};
  let incomeTotal = 0, expenseTotal = 0;
  for (const t of txs) {
    if (month && t.month !== month) continue;
    const cat = t.category || '기타';
    if (t.amount > 0 || isIncome(cat)) {
      if (t.amount > 0) { income[cat] = (income[cat] || 0) + t.amount; incomeTotal += t.amount; }
      else { expense[cat] = (expense[cat] || 0) + Math.abs(t.amount); expenseTotal += Math.abs(t.amount); }
    } else {
      expense[cat] = (expense[cat] || 0) + Math.abs(t.amount); expenseTotal += Math.abs(t.amount);
    }
  }
  const toRows = (o) => Object.entries(o).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
  return { income: toRows(income), expense: toRows(expense), incomeTotal, expenseTotal, net: incomeTotal - expenseTotal };
}

export function monthlyTotals(txs, months) {
  return months.map((m) => {
    let income = 0, expense = 0;
    for (const t of txs) if (t.month === m) { if (t.amount > 0) income += t.amount; else expense += -t.amount; }
    return { month: m, income, expense };
  });
}
