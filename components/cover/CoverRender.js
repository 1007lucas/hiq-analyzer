// 표지 렌더러 — 모든 치수는 mm 단위로 1:1 렌더링합니다. (미리보기는 바깥에서 transform: scale 로 축소)
import { FONTS, getPalette, getTrim, getSpine, luminance, hexToRgba } from '../../lib/cover/constants';
import { normalizeIsbn13, formatIsbn, encodeEan13, encodeEan5, bitsToBars } from '../../lib/cover/barcode';

const mm = (v) => `${v}mm`;

/** 렌더링에 필요한 치수 계산 */
export function coverDims(d, mode) {
  const { w: W, h: H } = getTrim(d);
  const B = Math.max(0, Number(d.bleed) || 0);
  const S = getSpine(d);
  const slug = d.marks ? 7 : 0;
  const panelW = mode === 'wrap' ? W * 2 + S : W;
  return {
    W, H, B, S, slug,
    totalW: panelW + B * 2 + slug * 2,
    totalH: H + B * 2 + slug * 2,
  };
}

/* ───────────────── 바코드 ───────────────── */
function Barcode({ isbn, addon, dark }) {
  const d13 = normalizeIsbn13(isbn);
  const MOD = 0.33; // mm per module (100% 배율)
  const Q = 9;      // quiet zone (modules)
  const barH = 60;  // modules (≈ 20mm)
  const addBits = encodeEan5(addon);
  const mainBits = d13 ? encodeEan13(d13) : null;
  const addW = addBits ? 47 : 0;
  const gap = addBits ? 8 : 0;
  const totalMods = Q + 95 + gap + addW + Q;
  const totalH = barH + 14;

  const bars = mainBits ? bitsToBars(mainBits) : [];
  const addBars = addBits ? bitsToBars(addBits) : [];
  const guard = new Set([0, 1, 2, 45, 46, 47, 48, 49, 92, 93, 94]);
  const isGuard = (b) => [...Array(b.w)].every((_, i) => guard.has(b.x + i));

  return (
    <div style={{ background: '#fff', padding: mm(2), display: 'inline-block', borderRadius: mm(0.8) }}>
      <div style={{ fontFamily: "'Noto Sans KR', sans-serif", fontSize: mm(2.6), color: '#111', letterSpacing: '.04em', marginBottom: mm(0.8), fontWeight: 500 }}>
        {d13 ? `ISBN ${formatIsbn(d13)}` : 'ISBN 미입력'}{addBits ? `   ${addon}` : ''}
      </div>
      {mainBits ? (
        <svg width={mm(totalMods * MOD)} height={mm(totalH * MOD)} viewBox={`0 0 ${totalMods} ${totalH}`} shapeRendering="crispEdges">
          {bars.map((b, i) => {
            const g = isGuard(b);
            return <rect key={i} x={Q + b.x} y={0} width={b.w} height={g ? barH + 5 : barH} fill="#000" />;
          })}
          <text x={Q - 2} y={barH + 11} fontSize="9" fontFamily="monospace" textAnchor="end" fill="#000">{d13[0]}</text>
          <text x={Q + 3 + 21} y={barH + 11} fontSize="9" fontFamily="monospace" textAnchor="middle" fill="#000" style={{ letterSpacing: 1.2 }}>{d13.slice(1, 7)}</text>
          <text x={Q + 50 + 21} y={barH + 11} fontSize="9" fontFamily="monospace" textAnchor="middle" fill="#000" style={{ letterSpacing: 1.2 }}>{d13.slice(7, 13)}</text>
          {addBits && (
            <>
              <text x={Q + 95 + gap + addW / 2} y={9} fontSize="9" fontFamily="monospace" textAnchor="middle" fill="#000" style={{ letterSpacing: 2 }}>{String(addon).replace(/\D/g, '')}</text>
              {addBars.map((b, i) => (
                <rect key={'a' + i} x={Q + 95 + gap + b.x} y={12} width={b.w} height={barH - 7} fill="#000" />
              ))}
            </>
          )}
        </svg>
      ) : (
        <div style={{ width: mm(40), height: mm(22), border: '0.3mm dashed #999', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: mm(2.6), color: '#777', fontFamily: "'Noto Sans KR', sans-serif", textAlign: 'center', lineHeight: 1.4 }}>
          바코드 영역<br />ISBN 12~13자리 입력
        </div>
      )}
    </div>
  );
}

/* ───────────────── 공통 요소 ───────────────── */
function Badge({ text, bg, fg, size, x, y, font }) {
  if (!text) return null;
  return (
    <div style={{
      position: 'absolute', left: mm(x), top: mm(y), width: mm(size), height: mm(size), borderRadius: '50%',
      background: bg, color: fg, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      fontFamily: font, fontWeight: 800, fontSize: mm(size * 0.17), lineHeight: 1.15, padding: mm(size * 0.12),
      wordBreak: 'keep-all', boxShadow: `0 ${mm(0.6)} ${mm(2)} rgba(0,0,0,.18)`,
    }}>{text}</div>
  );
}

const txt = (extra) => ({ position: 'absolute', whiteSpace: 'pre-wrap', wordBreak: 'keep-all', lineHeight: 1.2, ...extra });

/* ───────────────── 앞표지 템플릿 ───────────────── */
function FrontPanel({ d, pal, tf, bf, W, H, B, bl, br }) {
  const u = W / 188;                 // 판형 비례 계수
  const ts = Number(d.titleScale) || 1;
  const M = 14 * u;                  // 안쪽 여백
  const ox = bl, oy = B;             // 재단면 원점
  const outerW = bl + W + br, outerH = H + B * 2;
  const cw = W - M * 2;              // 콘텐츠 폭
  const titleSize = (v) => mm(v * u * ts);
  const s = (v) => mm(v * u);
  const levelLine = [d.level, d.subject].filter(Boolean).join(' ');
  const authorLine = [d.author, d.publisher].filter(Boolean).join('  ·  ');

  const base = { position: 'relative', width: mm(outerW), height: mm(outerH), overflow: 'hidden', fontFamily: bf, color: pal.ink };

  switch (d.template) {
    /* ── 1. 아카데믹 클래식 ── */
    case 'academic': {
      const bandH = oy + H * 0.21;
      return (
        <div style={{ ...base, background: pal.bg }}>
          <div style={{ position: 'absolute', left: 0, top: 0, width: '100%', height: mm(bandH), background: pal.primary }} />
          <div style={{ position: 'absolute', left: 0, top: mm(bandH), width: '100%', height: mm(1.4 * u), background: pal.accent }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + M * 0.85), color: pal.accent, fontSize: s(4.2), fontWeight: 700, letterSpacing: '.18em' })}>{d.series}</div>
          {levelLine && (
            <div style={txt({ right: mm(br + M), top: mm(oy + M * 0.75), color: '#fff', fontSize: s(4.4), fontWeight: 700, border: `${mm(0.45 * u)} solid ${hexToRgba('#ffffff', 0.7)}`, padding: `${s(1.6)} ${s(4)}`, letterSpacing: '.06em' })}>{levelLine}</div>
          )}
          <div style={txt({ left: mm(ox + M), top: mm(bandH - 11 * u), color: '#fff', fontSize: s(4), opacity: .85, letterSpacing: '.04em' })}>{d.volume}</div>
          <div style={txt({ left: mm(ox + M), top: mm(bandH + 22 * u), width: mm(cw), fontFamily: tf, fontSize: titleSize(17), fontWeight: 800, color: pal.primary, lineHeight: 1.18, letterSpacing: '-.01em' })}>{d.title}</div>
          <div style={txt({ left: mm(ox + M), top: mm(bandH + 22 * u + 17 * u * ts * 1.18 * (1 + ((d.title || '').split('\n').length - 1)) + 10 * u), width: mm(cw), fontSize: s(5.4), fontWeight: 500, color: pal.ink, lineHeight: 1.5 })}>{d.subtitle}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.70), width: mm(cw * 0.7), fontFamily: tf, fontSize: s(5), color: pal.accent, fontWeight: 600, lineHeight: 1.5 })}>{d.tagline}</div>
          <div style={{ position: 'absolute', left: mm(ox + M), top: mm(oy + H - M - 14 * u), width: mm(cw), height: mm(0.35 * u), background: pal.primary, opacity: .5 }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + H - M - 10 * u), fontSize: s(3.8), fontWeight: 700, color: pal.primary })}>{authorLine}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H - M - 4.5 * u), fontSize: s(3.2), color: '#6b7280' })}>{d.edition}</div>
          <Badge text={d.badge} bg={pal.accent} fg="#fff" size={30 * u} x={ox + W - M - 30 * u} y={oy + H * 0.62} font={bf} />
        </div>
      );
    }

    /* ── 2. 모던 그리드 ── */
    case 'grid': {
      const blockW = br + W * 0.56, blockH = B + H * 0.36;
      const gridC = hexToRgba(pal.primary, 0.08);
      return (
        <div style={{ ...base, background: pal.bg, backgroundImage: `linear-gradient(${gridC} ${mm(0.3)}, transparent ${mm(0.3)}), linear-gradient(90deg, ${gridC} ${mm(0.3)}, transparent ${mm(0.3)})`, backgroundSize: `${s(9)} ${s(9)}`, backgroundPosition: `${mm(ox)} ${mm(oy)}` }}>
          <div style={{ position: 'absolute', left: mm(ox + M), top: mm(oy + M), width: s(4), height: s(4), background: pal.accent }} />
          <div style={txt({ left: mm(ox + M + 7 * u), top: mm(oy + M - 0.4 * u), color: pal.primary, fontSize: s(4), fontWeight: 800, letterSpacing: '.14em' })}>{d.series}</div>
          <div style={txt({ right: mm(br + M), top: mm(oy + M - 0.4 * u), color: '#6b7280', fontSize: s(3.6), fontWeight: 600 })}>{d.volume}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + M + 20 * u), width: mm(cw), fontFamily: tf, fontSize: titleSize(19), fontWeight: 900, color: pal.ink, lineHeight: 1.1, letterSpacing: '-.02em' })}>{d.title}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + M + 20 * u + 19 * u * ts * 1.1 * ((d.title || '').split('\n').length) + 8 * u), width: mm(cw * 0.78), fontSize: s(5.2), fontWeight: 500, color: '#374151', lineHeight: 1.5 })}>{d.subtitle}</div>
          <div style={{ position: 'absolute', right: 0, bottom: 0, width: mm(blockW), height: mm(blockH), background: pal.primary }} />
          <div style={{ position: 'absolute', right: mm(blockW - 6 * u), bottom: mm(blockH - 6 * u), width: s(12), height: s(12), background: pal.accent }} />
          <div style={txt({ right: mm(br + M), bottom: mm(oy + H * 0.36 - 28 * u), color: '#fff', fontFamily: tf, fontSize: s(34), fontWeight: 900, lineHeight: 1, letterSpacing: '-.03em', textAlign: 'right' })}>{d.level}</div>
          <div style={txt({ right: mm(br + M), bottom: mm(oy + H * 0.36 - 36 * u), color: hexToRgba('#ffffff', 0.9), fontSize: s(6.5), fontWeight: 700, textAlign: 'right' })}>{d.subject}</div>
          <div style={txt({ right: mm(br + M), bottom: mm(oy + M * 0.8), color: hexToRgba('#ffffff', 0.75), fontSize: s(3.4), textAlign: 'right' })}>{d.edition}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.50), width: mm(W * 0.4), fontSize: s(4.4), fontWeight: 600, color: pal.primary, lineHeight: 1.5 })}>{d.tagline}</div>
          <div style={txt({ left: mm(ox + M), bottom: mm(oy + M * 0.8), width: mm(W * 0.42), fontSize: s(3.6), fontWeight: 700, color: pal.ink, lineHeight: 1.5 })}>{authorLine}</div>
          <Badge text={d.badge} bg={pal.accent} fg={luminance(pal.accent) > 0.6 ? pal.ink : '#fff'} size={26 * u} x={ox + M} y={oy + H * 0.59} font={bf} />
        </div>
      );
    }

    /* ── 3. 볼드 타이포 ── */
    case 'bold': {
      return (
        <div style={{ ...base, background: pal.primary, color: '#fff' }}>
          <div style={{ position: 'absolute', left: mm(-outerW * 0.2), bottom: mm(-outerH * 0.08), width: mm(outerW * 1.6), height: mm(outerH * 0.34), background: pal.secondary, transform: 'rotate(-14deg)', transformOrigin: 'center' }} />
          <div style={{ position: 'absolute', left: mm(-outerW * 0.2), bottom: mm(outerH * 0.235), width: mm(outerW * 1.6), height: mm(1.6 * u), background: pal.accent, transform: 'rotate(-14deg)', transformOrigin: 'center' }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + M), color: hexToRgba('#ffffff', 0.85), fontSize: s(4), fontWeight: 700, letterSpacing: '.2em' })}>{d.series}</div>
          {levelLine && (
            <div style={txt({ right: mm(br + M), top: mm(oy + M - 2 * u), color: '#fff', fontSize: s(5), fontWeight: 800, border: `${mm(0.6 * u)} solid #fff`, padding: `${s(1.6)} ${s(4)}` })}>{levelLine}</div>
          )}
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.17), width: mm(cw), fontFamily: tf, fontSize: titleSize(24), fontWeight: 900, color: '#fff', lineHeight: 1.05, letterSpacing: '-.02em' })}>{d.title}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.17 + 24 * u * ts * 1.05 * ((d.title || '').split('\n').length) + 8 * u), width: mm(cw * 0.85), fontSize: s(5.6), fontWeight: 500, color: hexToRgba('#ffffff', 0.9), lineHeight: 1.5 })}>{d.subtitle}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.56), width: mm(cw * 0.6), fontFamily: tf, fontSize: s(5.4), color: pal.accent, fontWeight: 700, lineHeight: 1.45 })}>{d.tagline}</div>
          <div style={txt({ left: mm(ox + M), bottom: mm(oy + M), fontSize: s(3.8), fontWeight: 700, color: '#fff', lineHeight: 1.6 })}>{authorLine}{'\n'}<span style={{ fontWeight: 400, opacity: .8, fontSize: s(3.2) }}>{d.edition}</span></div>
          <div style={txt({ right: mm(br + M), bottom: mm(oy + M), fontSize: s(3.4), color: hexToRgba('#ffffff', 0.8) })}>{d.volume}</div>
          <Badge text={d.badge} bg={pal.accent} fg={luminance(pal.accent) > 0.6 ? pal.ink : '#fff'} size={30 * u} x={ox + W - M - 30 * u} y={oy + H * 0.56} font={bf} />
        </div>
      );
    }

    /* ── 4. 미니멀 라인 ── */
    case 'minimal': {
      const inset = M * 0.6;
      return (
        <div style={{ ...base, background: pal.bg }}>
          <div style={{ position: 'absolute', left: mm(ox + inset), top: mm(oy + inset), width: mm(W - inset * 2), height: mm(H - inset * 2), border: `${mm(0.4 * u)} solid ${pal.primary}` }} />
          <div style={{ position: 'absolute', left: mm(ox + W / 2 - 3 * u), top: mm(oy + inset - 1.5 * u), width: s(6), height: s(3), background: pal.accent }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.17), width: mm(cw), textAlign: 'center', color: pal.primary, fontSize: s(3.8), fontWeight: 700, letterSpacing: '.3em' })}>{d.series}</div>
          <div style={{ position: 'absolute', left: mm(ox + W / 2 - 8 * u), top: mm(oy + H * 0.17 + 9 * u), width: s(16), height: mm(0.45 * u), background: pal.accent }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.17 + 17 * u), width: mm(cw), textAlign: 'center', fontFamily: tf, fontSize: titleSize(16), fontWeight: 700, color: pal.primary, lineHeight: 1.25 })}>{d.title}</div>
          <div style={txt({ left: mm(ox + M * 1.4), top: mm(oy + H * 0.17 + 17 * u + 16 * u * ts * 1.25 * ((d.title || '').split('\n').length) + 8 * u), width: mm(W - M * 2.8), textAlign: 'center', fontSize: s(4.8), fontWeight: 500, color: pal.ink, lineHeight: 1.55 })}>{d.subtitle}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.60), width: mm(cw), textAlign: 'center', fontFamily: tf, fontSize: s(4.4), color: '#6b7280', fontStyle: 'italic', lineHeight: 1.5 })}>{d.tagline}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.74), width: mm(cw), textAlign: 'center', fontSize: s(4.6), fontWeight: 700, color: pal.primary, letterSpacing: '.1em' })}>{[d.level, d.subject, d.volume].filter(Boolean).join('  ·  ')}</div>
          <div style={txt({ left: mm(ox + M), bottom: mm(oy + M + 2 * u), width: mm(cw), textAlign: 'center', fontSize: s(3.5), color: pal.ink, lineHeight: 1.7 })}>{authorLine}{'\n'}<span style={{ color: '#6b7280', fontSize: s(3) }}>{d.edition}</span></div>
          <Badge text={d.badge} bg={pal.primary} fg="#fff" size={22 * u} x={ox + W - M - 22 * u - 2 * u} y={oy + M + 2 * u} font={bf} />
        </div>
      );
    }

    /* ── 5. 그라디언트 ── */
    case 'gradient': {
      return (
        <div style={{ ...base, background: `linear-gradient(155deg, ${pal.primary} 0%, ${pal.secondary} 100%)`, color: '#fff' }}>
          <div style={{ position: 'absolute', right: mm(-W * 0.25), bottom: mm(-H * 0.12), width: mm(W * 0.9), height: mm(W * 0.9), borderRadius: '50%', background: hexToRgba(pal.accent, 0.28) }} />
          <div style={{ position: 'absolute', right: mm(W * 0.05), bottom: mm(H * 0.22), width: mm(W * 0.42), height: mm(W * 0.42), borderRadius: '50%', border: `${mm(0.6 * u)} solid ${hexToRgba('#ffffff', 0.25)}` }} />
          <div style={{ position: 'absolute', left: mm(-W * 0.18), top: mm(-W * 0.1), width: mm(W * 0.55), height: mm(W * 0.55), borderRadius: '50%', background: hexToRgba('#ffffff', 0.07) }} />
          <svg style={{ position: 'absolute', left: 0, bottom: 0, width: '100%', height: mm(outerH * 0.22) }} viewBox="0 0 100 40" preserveAspectRatio="none">
            <path d="M0 22 C 25 8, 45 40, 70 22 S 95 10, 100 16 L100 40 L0 40 Z" fill={hexToRgba('#ffffff', 0.10)} />
            <path d="M0 30 C 30 18, 50 42, 75 28 S 95 22, 100 26 L100 40 L0 40 Z" fill={hexToRgba('#ffffff', 0.08)} />
          </svg>
          <div style={txt({ left: mm(ox + M), top: mm(oy + M), color: '#fff', fontSize: s(3.8), fontWeight: 700, letterSpacing: '.14em', border: `${mm(0.4 * u)} solid ${hexToRgba('#ffffff', 0.55)}`, borderRadius: mm(20), padding: `${s(1.4)} ${s(4)}` })}>{d.series}</div>
          <div style={txt({ right: mm(br + M), top: mm(oy + M + 0.4 * u), color: hexToRgba('#ffffff', 0.85), fontSize: s(3.8), fontWeight: 600 })}>{d.volume}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.2), width: mm(cw), fontFamily: tf, fontSize: titleSize(19), fontWeight: 900, color: '#fff', lineHeight: 1.12, letterSpacing: '-.01em', textShadow: `0 ${mm(0.6)} ${mm(3)} rgba(0,0,0,.18)` })}>{d.title}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.2 + 19 * u * ts * 1.12 * ((d.title || '').split('\n').length) + 8 * u), width: mm(cw * 0.8), fontSize: s(5.2), fontWeight: 500, color: hexToRgba('#ffffff', 0.92), lineHeight: 1.5 })}>{d.subtitle}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.58), width: mm(cw * 0.6), fontSize: s(4.6), color: '#fff', fontWeight: 600, lineHeight: 1.5, opacity: .95 })}>{d.tagline}</div>
          <div style={txt({ left: mm(ox + M - 1 * u), bottom: mm(oy + M - 3 * u), fontFamily: tf, fontSize: s(46), fontWeight: 900, color: hexToRgba('#ffffff', 0.14), lineHeight: 1, letterSpacing: '-.04em' })}>{d.level}</div>
          <div style={txt({ right: mm(br + M), bottom: mm(oy + M), textAlign: 'right', fontSize: s(3.8), fontWeight: 700, color: '#fff', lineHeight: 1.6 })}>{d.subject}{'\n'}<span style={{ fontWeight: 500, opacity: .85, fontSize: s(3.4) }}>{authorLine}</span>{'\n'}<span style={{ fontWeight: 400, opacity: .7, fontSize: s(3) }}>{d.edition}</span></div>
          <Badge text={d.badge} bg="#fff" fg={pal.primary} size={26 * u} x={ox + W - M - 26 * u} y={oy + H * 0.52} font={bf} />
        </div>
      );
    }

    /* ── 6. 다크 프리미엄 ── */
    default: {
      const dark = '#121418';
      const inset = M * 0.55;
      return (
        <div style={{ ...base, background: dark, color: '#fff' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', background: `radial-gradient(ellipse at 20% 15%, ${hexToRgba(pal.primary, 0.55)} 0%, transparent 55%)` }} />
          <div style={{ position: 'absolute', left: mm(ox + inset), top: mm(oy + inset), width: mm(W - inset * 2), height: mm(H - inset * 2), border: `${mm(0.3 * u)} solid ${hexToRgba(pal.accent, 0.6)}` }} />
          <div style={{ position: 'absolute', left: mm(ox + inset + 1.6 * u), top: mm(oy + inset + 1.6 * u), width: mm(W - inset * 2 - 3.2 * u), height: mm(H - inset * 2 - 3.2 * u), border: `${mm(0.15 * u)} solid ${hexToRgba(pal.accent, 0.35)}` }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + M + 2 * u), color: pal.accent, fontSize: s(3.8), fontWeight: 600, letterSpacing: '.3em' })}>{d.series}</div>
          <div style={txt({ right: mm(br + M), top: mm(oy + M + 1.4 * u), color: hexToRgba('#ffffff', 0.7), fontSize: s(3.6), letterSpacing: '.08em' })}>{d.volume}</div>
          <div style={{ position: 'absolute', left: mm(ox + M), top: mm(oy + H * 0.23), width: s(14), height: mm(0.5 * u), background: pal.accent }} />
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.23 + 8 * u), width: mm(cw), fontFamily: tf, fontSize: titleSize(17), fontWeight: 700, color: '#fff', lineHeight: 1.2 })}>{d.title}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.23 + 8 * u + 17 * u * ts * 1.2 * ((d.title || '').split('\n').length) + 8 * u), width: mm(cw * 0.85), fontFamily: tf, fontSize: s(5.2), fontWeight: 500, color: pal.accent, lineHeight: 1.5 })}>{d.subtitle}</div>
          <div style={txt({ left: mm(ox + M), top: mm(oy + H * 0.64), width: mm(cw * 0.7), fontSize: s(4.2), color: hexToRgba('#ffffff', 0.7), lineHeight: 1.6 })}>{d.tagline}</div>
          <div style={txt({ left: mm(ox + M), bottom: mm(oy + M + 1 * u), fontFamily: tf, fontSize: s(16), fontWeight: 700, color: 'transparent', WebkitTextStroke: `${mm(0.25 * u)} ${hexToRgba(pal.accent, 0.8)}`, lineHeight: 1, letterSpacing: '.02em' })}>{levelLine}</div>
          <div style={txt({ right: mm(br + M), bottom: mm(oy + M + 1 * u), textAlign: 'right', fontSize: s(3.5), color: hexToRgba('#ffffff', 0.85), lineHeight: 1.7 })}>{authorLine}{'\n'}<span style={{ color: pal.accent, fontSize: s(3) }}>{d.edition}</span></div>
          <Badge text={d.badge} bg={pal.accent} fg={dark} size={24 * u} x={ox + W - M - 24 * u} y={oy + H * 0.6 - 24 * u} font={bf} />
        </div>
      );
    }
  }
}

/* ───────────────── 뒤표지 ───────────────── */
function BackPanel({ d, pal, tf, bf, W, H, B, bl, br }) {
  const u = W / 188;
  const M = 14 * u;
  const ox = bl, oy = B;
  const outerW = bl + W + br, outerH = H + B * 2;
  const cw = W - M * 2;
  const s = (v) => mm(v * u);
  const t = d.template;
  const darkBg = t === 'bold' ? pal.primary : t === 'gradient' ? `linear-gradient(155deg, ${pal.secondary} 0%, ${pal.primary} 100%)` : t === 'dark' ? '#121418' : null;
  const onDark = !!darkBg;
  const fg = onDark ? '#fff' : pal.ink;
  const sub = onDark ? hexToRgba('#ffffff', 0.75) : '#4b5563';
  const accent = onDark ? (t === 'dark' ? pal.accent : hexToRgba('#ffffff', 0.9)) : pal.primary;
  const features = (d.features || '').split('\n').map(x => x.trim()).filter(Boolean);
  const bandTop = t === 'academic';

  return (
    <div style={{ position: 'relative', width: mm(outerW), height: mm(outerH), overflow: 'hidden', fontFamily: bf, color: fg, background: darkBg || pal.bg }}>
      {bandTop && <div style={{ position: 'absolute', left: 0, top: 0, width: '100%', height: mm(oy + 12 * u), background: pal.primary }} />}
      {bandTop && <div style={{ position: 'absolute', left: 0, top: mm(oy + 12 * u), width: '100%', height: mm(1 * u), background: pal.accent }} />}
      {t === 'grid' && <div style={{ position: 'absolute', left: 0, bottom: 0, width: mm(bl + W * 0.54), height: mm(B + H * 0.17), background: pal.primary }} />}
      {t === 'minimal' && <div style={{ position: 'absolute', left: mm(ox + M * 0.6), top: mm(oy + M * 0.6), width: mm(W - M * 1.2), height: mm(H - M * 1.2), border: `${mm(0.4 * u)} solid ${pal.primary}` }} />}
      {t === 'dark' && <div style={{ position: 'absolute', left: mm(ox + M * 0.55), top: mm(oy + M * 0.55), width: mm(W - M * 1.1), height: mm(H - M * 1.1), border: `${mm(0.3 * u)} solid ${hexToRgba(pal.accent, 0.6)}` }} />}

      <div style={txt({ left: mm(ox + M), top: mm(oy + (bandTop ? 4 * u : M)), color: bandTop ? pal.accent : accent, fontSize: s(3.8), fontWeight: 700, letterSpacing: '.16em' })}>{d.series}</div>
      <div style={txt({ left: mm(ox + M), top: mm(oy + M + 14 * u), width: mm(cw), fontFamily: tf, fontSize: s(8.5), fontWeight: 800, color: accent, lineHeight: 1.3 })}>{d.tagline}</div>
      <div style={txt({ left: mm(ox + M), top: mm(oy + M + 14 * u + 8.5 * u * 1.3 * Math.max(1, Math.ceil((d.tagline || '').length / 22)) + 6 * u), width: mm(cw), fontSize: s(4.1), lineHeight: 1.75, color: fg, textAlign: 'justify' })}>{d.blurb}</div>

      <div style={{ position: 'absolute', left: mm(ox + M), top: mm(oy + H * 0.5), width: mm(cw) }}>
        <div style={{ fontSize: s(4.2), fontWeight: 800, color: accent, marginBottom: s(3), letterSpacing: '.04em' }}>이 책의 특징</div>
        {features.map((f, i) => (
          <div key={i} style={{ display: 'flex', gap: s(2.5), alignItems: 'flex-start', marginBottom: s(2.2), fontSize: s(4), lineHeight: 1.5, color: fg }}>
            <span style={{ flexShrink: 0, width: s(5.2), height: s(5.2), borderRadius: '50%', background: onDark ? hexToRgba('#ffffff', 0.18) : hexToRgba(pal.primary, 0.1), color: accent, fontSize: s(2.8), fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: s(0.4) }}>{String(i + 1).padStart(2, '0')}</span>
            <span>{f}</span>
          </div>
        ))}
      </div>

      <div style={txt({ left: mm(ox + M), bottom: mm(oy + M), width: mm(W * 0.42), fontSize: s(3.3), lineHeight: 1.7, color: t === 'grid' ? '#fff' : sub })}>
        <span style={{ fontWeight: 700, color: t === 'grid' ? '#fff' : fg }}>{[d.author, d.publisher].filter(Boolean).join('  ·  ')}</span>{'\n'}{d.contact}{'\n'}{d.edition}
      </div>
      <div style={{ position: 'absolute', right: mm(br + M), bottom: mm(oy + M), display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: s(2) }}>
        <Barcode isbn={d.isbn} addon={d.addon} dark={onDark} />
        <div style={{ fontSize: s(4.2), fontWeight: 800, color: fg }}>{d.price}</div>
      </div>
    </div>
  );
}

/* ───────────────── 책등 ───────────────── */
function SpinePanel({ d, pal, tf, bf, W, H, B, S }) {
  const u = W / 188;
  const t = d.template;
  const bg = t === 'dark' ? '#121418' : t === 'gradient' ? `linear-gradient(180deg, ${pal.primary}, ${pal.secondary})` : t === 'minimal' ? pal.bg : pal.primary;
  const fg = t === 'minimal' ? pal.primary : t === 'dark' ? pal.accent : '#fff';
  const fs = Math.min(S * 0.52, 6.5 * u);
  const outerH = H + B * 2;
  return (
    <div style={{ position: 'relative', width: mm(S), height: mm(outerH), background: bg, overflow: 'hidden', fontFamily: bf, color: fg }}>
      {t === 'minimal' && <><div style={{ position: 'absolute', left: 0, top: 0, width: mm(0.4 * u), height: '100%', background: pal.primary }} /><div style={{ position: 'absolute', right: 0, top: 0, width: mm(0.4 * u), height: '100%', background: pal.primary }} /></>}
      <div style={{ position: 'absolute', left: 0, top: mm(B + 10 * u), width: '100%', height: mm(H * 0.18), display: 'flex', justifyContent: 'center', alignItems: 'flex-start' }}>
        <div style={{ writingMode: 'vertical-rl', textOrientation: 'upright', fontSize: mm(Math.min(fs * 0.75, 4)), fontWeight: 800, letterSpacing: '.1em', whiteSpace: 'nowrap', lineHeight: 1 }}>{[d.level, d.subject].filter(Boolean).join(' ')}</div>
      </div>
      <div style={{ position: 'absolute', left: 0, top: mm(B + H * 0.25), width: '100%', height: mm(H * 0.5), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ writingMode: 'vertical-rl', textOrientation: 'upright', fontFamily: tf, fontSize: mm(fs), fontWeight: 800, letterSpacing: '.08em', whiteSpace: 'nowrap', lineHeight: 1 }}>{(d.title || '').replace(/\n/g, ' ')}</div>
      </div>
      <div style={{ position: 'absolute', left: 0, bottom: mm(B + 8 * u), width: '100%', height: mm(H * 0.18), display: 'flex', justifyContent: 'center', alignItems: 'flex-end' }}>
        <div style={{ writingMode: 'vertical-rl', textOrientation: 'upright', fontSize: mm(Math.min(fs * 0.6, 3.4)), fontWeight: 700, whiteSpace: 'nowrap', lineHeight: 1, opacity: .9 }}>{d.publisher}</div>
      </div>
    </div>
  );
}

/* ───────────────── 재단선 ───────────────── */
function Marks({ dims, mode }) {
  const { W, H, B, S, slug, totalW, totalH } = dims;
  if (!slug) return null;
  const len = slug - 1.5;
  const th = 0.25;
  const xs = mode === 'wrap' ? [slug + B, slug + B + W * 2 + S] : [slug + B, slug + B + W];
  const ys = [slug + B, slug + B + H];
  const lines = [];
  xs.forEach((x) => {
    lines.push({ left: x - th / 2, top: 0, width: th, height: len });
    lines.push({ left: x - th / 2, top: totalH - len, width: th, height: len });
  });
  ys.forEach((y) => {
    lines.push({ left: 0, top: y - th / 2, width: len, height: th });
    lines.push({ left: totalW - len, top: y - th / 2, width: len, height: th });
  });
  if (mode === 'wrap') {
    [slug + B + W, slug + B + W + S].forEach((x) => {
      lines.push({ left: x - th / 2, top: 0, width: th, height: len, dashed: true });
      lines.push({ left: x - th / 2, top: totalH - len, width: th, height: len, dashed: true });
    });
  }
  const info = `재단 ${W}×${H}mm · 도련 ${B}mm${mode === 'wrap' ? ` · 책등 ${S}mm` : ''} · 완성 ${Math.round((totalW - slug * 2) * 10) / 10}×${Math.round((totalH - slug * 2) * 10) / 10}mm (도련 포함)`;
  return (
    <>
      {lines.map((l, i) => (
        <div key={i} style={{ position: 'absolute', left: mm(l.left), top: mm(l.top), width: mm(l.width), height: mm(l.height), background: l.dashed ? `repeating-linear-gradient(180deg, #000 0 ${mm(0.8)}, transparent ${mm(0.8)} ${mm(1.6)})` : '#000' }} />
      ))}
      <div style={{ position: 'absolute', left: mm(slug + B + 2), top: mm(totalH - slug + 1.2), fontSize: mm(2.2), color: '#444', fontFamily: "'Noto Sans KR', sans-serif", whiteSpace: 'nowrap' }}>{info}</div>
    </>
  );
}

/* ───────────────── 메인 렌더러 ───────────────── */
export default function CoverRender({ design: d, mode = 'front', id }) {
  const pal = getPalette(d);
  const dims = coverDims(d, mode);
  const { W, H, B, S, slug, totalW, totalH } = dims;
  const tf = (FONTS[d.titleFont] || FONTS.notoSerif).css;
  const bf = (FONTS[d.bodyFont] || FONTS.notoSans).css;
  const common = { d, pal, tf, bf, W, H, B };

  return (
    <div id={id} style={{ position: 'relative', width: mm(totalW), height: mm(totalH), background: slug ? '#fff' : 'transparent', WebkitPrintColorAdjust: 'exact', printColorAdjust: 'exact', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: mm(slug), top: mm(slug), display: 'flex', alignItems: 'stretch' }}>
        {mode === 'wrap' ? (
          <>
            <BackPanel {...common} bl={B} br={0} />
            <SpinePanel {...common} S={S} />
            <FrontPanel {...common} bl={0} br={B} />
          </>
        ) : mode === 'back' ? (
          <BackPanel {...common} bl={B} br={B} />
        ) : (
          <FrontPanel {...common} bl={B} br={B} />
        )}
      </div>
      <Marks dims={dims} mode={mode} />
    </div>
  );
}
