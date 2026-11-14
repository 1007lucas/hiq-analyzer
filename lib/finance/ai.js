// 서버 API(/api/finance) 호출 헬퍼 (클라이언트)
export async function aiCall(task, payload) {
  const res = await fetch('/api/finance', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, payload }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `오류 (${res.status})`);
  return data;
}

// 미분류 거래를 60건씩 AI 분류. 같은 설명은 한 번만 질문.
export async function categorizeWithAI(items, categories, domain, onProgress) {
  const byDesc = new Map();
  for (const it of items) {
    const k = `${it.desc}|${it.amount > 0 ? '+' : '-'}`;
    if (!byDesc.has(k)) byDesc.set(k, { id: k, desc: it.desc, amount: it.amount });
  }
  const unique = [...byDesc.values()];
  const result = new Map();
  const BATCH = 60;
  for (let i = 0; i < unique.length; i += BATCH) {
    const batch = unique.slice(i, i + BATCH);
    onProgress?.(Math.min(i + BATCH, unique.length), unique.length);
    const data = await aiCall('categorize', { items: batch, categories, domain });
    for (const row of data.items || []) {
      if (categories.includes(row.category)) result.set(row.id, row.category);
    }
  }
  return (it) => result.get(`${it.desc}|${it.amount > 0 ? '+' : '-'}`) || null;
}
