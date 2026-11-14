import { useState } from 'react';
import { monthLabel, wonShort, won } from '../../lib/finance/format';

// 최근 N개월 수입 vs 지출 막대 (2계열, 범례 + 호버 툴팁)
export default function TrendChart({ data, height = 180 }) {
  const [hover, setHover] = useState(null);
  const W = 640, H = height, padL = 54, padB = 26, padT = 10, padR = 10;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const max = Math.max(1, ...data.flatMap((d) => [d.income, d.expense]));
  const groupW = innerW / Math.max(1, data.length);
  const barW = Math.min(26, groupW * 0.32);
  const y = (v) => padT + innerH - (v / max) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  return (
    <div style={{ position: 'relative' }}>
      <div className="legend" style={{ marginBottom: 6 }}>
        <span><i style={{ background: 'var(--series-2)' }} />수입</span>
        <span><i style={{ background: 'var(--series-1)' }} />지출</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', overflow: 'visible' }} onMouseLeave={() => setHover(null)}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="#e5e7eb" strokeWidth="1" />
            <text x={padL - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="#6b7280">{wonShort(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = padL + groupW * i + groupW / 2;
          const bars = [
            { k: 'income', v: d.income, x: cx - barW - 1, c: 'var(--series-2)' },
            { k: 'expense', v: d.expense, x: cx + 1, c: 'var(--series-1)' },
          ];
          return (
            <g key={d.month} onMouseEnter={() => setHover({ i, cx })}>
              <rect x={cx - groupW / 2} y={padT} width={groupW} height={innerH} fill={hover?.i === i ? 'rgba(31,56,100,.05)' : 'transparent'} />
              {bars.map((b) => {
                const h = Math.max(0, innerH - (y(b.v) - padT));
                return <rect key={b.k} x={b.x} y={y(b.v)} width={barW} height={h} fill={b.c} rx={h > 4 ? 3 : 0} />;
              })}
              <text x={cx} y={H - 8} fontSize="11" textAnchor="middle" fill="#6b7280">{d.month.slice(2).replace('-', '.')}</text>
            </g>
          );
        })}
      </svg>
      {hover && data[hover.i] && (
        <div className="tip" style={{ left: `${(hover.cx / W) * 100}%`, top: 30 }}>
          <b>{monthLabel(data[hover.i].month)}</b><br />
          수입 {won(data[hover.i].income)}<br />지출 {won(data[hover.i].expense)}<br />
          순 {won(data[hover.i].income - data[hover.i].expense, { plus: true })}
        </div>
      )}
    </div>
  );
}
