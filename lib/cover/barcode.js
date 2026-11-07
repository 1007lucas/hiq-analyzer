// EAN-13 / EAN-5 (ISBN + 부가기호) 바코드 인코더 — SVG로 렌더링하기 위한 모듈 패턴을 생성합니다.

const L = ['0001101','0011001','0010011','0111101','0100011','0110001','0101111','0111011','0110111','0001011'];
const G = ['0100111','0110011','0011011','0100001','0011101','0111001','0000101','0010001','0001001','0010111'];
const R = ['1110010','1100110','1101100','1000010','1011100','1001110','1010000','1000100','1001000','1110100'];
const PARITY13 = ['LLLLLL','LLGLGG','LLGGLG','LLGGGL','LGLLGG','LGGLLG','LGGGLL','LGLGLG','LGLGGL','LGGLGL'];
const PARITY5 = ['GGLLL','GLGLL','GLLGL','GLLLG','LGGLL','LLGGL','LLLGG','LGLGL','LGLLG','LLGLG'];

export const onlyDigits = (s) => String(s || '').replace(/\D/g, '');

/** 12자리 → 체크디지트 계산 */
export function ean13CheckDigit(d12) {
  let sum = 0;
  for (let i = 0; i < 12; i++) sum += Number(d12[i]) * (i % 2 === 0 ? 1 : 3);
  return String((10 - (sum % 10)) % 10);
}

/** 입력(ISBN 12~13자리)을 정규화. 유효하지 않으면 null */
export function normalizeIsbn13(input) {
  const d = onlyDigits(input);
  if (d.length === 12) return d + ean13CheckDigit(d);
  if (d.length === 13) return d.slice(0, 12) + ean13CheckDigit(d.slice(0, 12));
  return null;
}

/** 978-89-xxxx-xxx-x 형태로 하이픈 표기 (단순 표기용) */
export function formatIsbn(d13) {
  if (!d13) return '';
  return `${d13.slice(0,3)}-${d13.slice(3,5)}-${d13.slice(5,9)}-${d13.slice(9,12)}-${d13.slice(12)}`;
}

/** EAN-13 모듈 문자열 (95모듈). 가드바 위치도 함께 반환 */
export function encodeEan13(d13) {
  const first = Number(d13[0]);
  const parity = PARITY13[first];
  let bits = '101';
  for (let i = 1; i <= 6; i++) {
    const n = Number(d13[i]);
    bits += parity[i - 1] === 'L' ? L[n] : G[n];
  }
  bits += '01010';
  for (let i = 7; i <= 12; i++) bits += R[Number(d13[i])];
  bits += '101';
  return bits;
}

/** EAN-5 부가기호 (한국 도서 분류 번호) 모듈 문자열 */
export function encodeEan5(d5) {
  const d = onlyDigits(d5);
  if (d.length !== 5) return null;
  const chk = (3 * (Number(d[0]) + Number(d[2]) + Number(d[4])) + 9 * (Number(d[1]) + Number(d[3]))) % 10;
  const parity = PARITY5[chk];
  let bits = '1011';
  for (let i = 0; i < 5; i++) {
    const n = Number(d[i]);
    bits += parity[i] === 'L' ? L[n] : G[n];
    if (i < 4) bits += '01';
  }
  return bits;
}

/** 모듈 문자열 → [{x, w}] 바 목록 (모듈 단위) */
export function bitsToBars(bits) {
  const bars = [];
  let i = 0;
  while (i < bits.length) {
    if (bits[i] === '1') {
      let j = i;
      while (j < bits.length && bits[j] === '1') j++;
      bars.push({ x: i, w: j - i });
      i = j;
    } else i++;
  }
  return bars;
}
