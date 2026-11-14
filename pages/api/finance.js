import Anthropic from '@anthropic-ai/sdk';

export const config = { api: { bodyParser: { sizeLimit: '2mb' } } };

const MODEL = 'claude-opus-5-5';
const BETAS = ['server-side-fallback-2026-07-01'];

const SYSTEM = {
  academy: `당신은 한국의 소규모 학원(영어·입시학원)을 전담하는 재무 비서입니다.
학원은 교육용역으로 부가가치세 면세사업자이며, 강사는 보통 3.3% 사업소득자 또는 4대보험 근로자입니다.
숫자는 원 단위로 정확히 인용하고, 추측은 '추정'이라고 표시하세요. 세무 판단은 '세무사 확인 필요'를 덧붙이세요.
답은 한국어, 간결한 문단과 번호 목록으로. 마크다운 헤더(#)는 쓰지 마세요.`,
  personal: `당신은 한 사람의 개인 재무를 전담하는 비서입니다.
지출 데이터를 근거로 구체적이고 실행 가능한 조언을 합니다. 훈계하지 말고, 숫자를 근거로 우선순위를 정해 제안하세요.
답은 한국어, 간결한 문단과 번호 목록으로. 마크다운 헤더(#)는 쓰지 마세요.`,
};

function getClient(res) {
  if (!process.env.ANTHROPIC_API_KEY) {
    res.status(500).json({ error: 'API 키가 설정되지 않았습니다. Vercel 환경변수 ANTHROPIC_API_KEY를 확인하세요.' });
    return null;
  }
  return new Anthropic();
}

function textOf(response) {
  if (response.stop_reason === 'refusal') {
    const why = response.stop_details?.explanation || '안전 정책상 응답이 거부되었습니다.';
    throw new Error(why);
  }
  return response.content.filter((b) => b.type === 'text').map((b) => b.text).join('\n').trim();
}

async function categorize(client, payload) {
  const { items = [], categories = [], domain = 'personal' } = payload;
  if (!items.length || !categories.length) return { items: [] };
  const lines = items.map((it) => `${it.id}\t${it.desc}\t${it.amount > 0 ? '입금' : '출금'} ${Math.abs(it.amount).toLocaleString('ko-KR')}원`).join('\n');
  const response = await client.beta.messages.create({
    model: MODEL,
    betas: BETAS,
    fallbacks: 'default',
    max_tokens: 16000,
    output_config: {
      effort: 'low',
      format: {
        type: 'json_schema',
        schema: {
          type: 'object',
          properties: {
            items: {
              type: 'array',
              items: {
                type: 'object',
                properties: { id: { type: 'string' }, category: { type: 'string', enum: categories } },
                required: ['id', 'category'],
                additionalProperties: false,
              },
            },
          },
          required: ['items'],
          additionalProperties: false,
        },
      },
    },
    system: `${SYSTEM[domain] || SYSTEM.personal}

거래내역 한 줄(id, 내용, 입출금·금액)마다 아래 카테고리 중 정확히 하나를 고르세요.
카테고리: ${categories.join(', ')}
${domain === 'academy'
  ? '입금에 사람 이름만 있으면(타행이체 등) 보통 학생 보호자의 수강료 입금입니다 → "수강료 수입". 대표자 본인 계좌 간 이동·카드대금 결제는 "이체·내부거래".'
  : '사람 이름만 있는 입금·출금은 보통 "이체·송금". 급여·상여는 "수입". 카드사로 나가는 결제대금은 "카드대금". 적금·예금·증권·펀드 계좌로의 이체는 "저축·투자".'}
모든 id를 빠짐없이 반환하세요.`,
    messages: [{ role: 'user', content: lines }],
  });
  const text = textOf(response);
  try {
    const parsed = JSON.parse(text);
    return { items: parsed.items || [] };
  } catch {
    throw new Error('AI 응답을 해석할 수 없습니다. 다시 시도해주세요.');
  }
}

async function analyze(client, payload) {
  const { domain = 'personal', summary = '', question = '' } = payload;
  if (!summary) throw new Error('분석할 데이터가 없습니다.');
  const response = await client.beta.messages.create({
    model: MODEL,
    betas: BETAS,
    fallbacks: 'default',
    max_tokens: 4000,
    output_config: { effort: 'medium' },
    system: SYSTEM[domain] || SYSTEM.personal,
    messages: [{
      role: 'user',
      content: `[재무 데이터 요약]\n${summary}\n\n[요청]\n${question || '이 데이터를 바탕으로 핵심 코멘트 3~5개와 이번 달 실행할 행동 2~3개를 제안해주세요.'}`,
    }],
  });
  return { text: textOf(response) };
}

async function message(client, payload) {
  const { academy = '학원', student = '학생', className = '', amount = 0, month = '', dueDay = '', tone = 'polite', draft = '' } = payload;
  const response = await client.beta.messages.create({
    model: MODEL,
    betas: BETAS,
    fallbacks: 'default',
    max_tokens: 1000,
    output_config: { effort: 'low' },
    system: `당신은 학원 원장을 대신해 보호자에게 보내는 문자 메시지를 작성합니다. 정중하고 부담스럽지 않게, 150자 이내, 이모지 없이, 문자 본문만 출력하세요.`,
    messages: [{
      role: 'user',
      content: `학원명: ${academy}\n학생: ${student}${className ? ` (${className})` : ''}\n대상: ${month} 수강료 ${Number(amount).toLocaleString('ko-KR')}원\n납부 기한: 매월 ${dueDay || '-'}일\n톤: ${tone === 'firm' ? '2차 안내(조금 더 분명하게)' : '1차 안내(부드럽게)'}\n${draft ? `참고 초안:\n${draft}` : ''}`,
    }],
  });
  return { text: textOf(response) };
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const client = getClient(res);
  if (!client) return;
  const { task, payload = {} } = req.body || {};
  try {
    let out;
    if (task === 'categorize') out = await categorize(client, payload);
    else if (task === 'analyze') out = await analyze(client, payload);
    else if (task === 'message') out = await message(client, payload);
    else return res.status(400).json({ error: `알 수 없는 작업: ${task}` });
    return res.status(200).json(out);
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) return res.status(401).json({ error: 'API 키가 올바르지 않습니다.' });
    if (e instanceof Anthropic.RateLimitError) return res.status(429).json({ error: '요청이 많습니다. 잠시 후 다시 시도해주세요.' });
    if (e instanceof Anthropic.APIError) return res.status(e.status || 500).json({ error: e.message });
    return res.status(500).json({ error: e.message });
  }
}
