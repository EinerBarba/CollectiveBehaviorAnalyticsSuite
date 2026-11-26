import { useState, useEffect, useMemo } from "react";
import * as api from "./api.js";

// Palette
function darken(hex, amount = 0.8) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgb(${Math.round(r * amount)},${Math.round(g * amount)},${Math.round(b * amount)})`;
}

const K_COLORS = ["#5BF235", "#35F2DC", "#35AEF2", "#5B35F2", "#CC35F2"].map((c) => darken(c));
const COND_COLORS = { a: darken("#5BF235"), b: darken("#F2A735"), c: darken("#35AEF2") };

function stateColor(i) { return K_COLORS[i % K_COLORS.length]; }

// SVG helpers
function linScale(dMin, dMax, rMin, rMax) {
  return (v) => dMax === dMin ? (rMin + rMax) / 2 : rMin + ((v - dMin) / (dMax - dMin)) * (rMax - rMin);
}

function fmt1(v) { return v == null ? "—" : v.toFixed(3); }

function naturalCompare(a, b) { return String(a).localeCompare(String(b), undefined, { numeric: true }); }

function SvgAxis({ x1, y1, x2, y2, ticks, scale, orient, label }) {
  const isH = orient === "bottom";
  return (
    <g style={{ fontSize: 10, fill: "#111", stroke: "none" }}>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--axis, #555)" strokeWidth={1} />
      {ticks.map((t, i) => {
        const pos = scale(t);
        return (
          <g key={i} transform={isH ? `translate(${pos},${y1})` : `translate(${x1},${pos})`}>
            <line x1={0} y1={0} x2={isH ? 0 : -4} y2={isH ? 4 : 0} stroke="var(--axis, #555)" strokeWidth={1} />
            <text x={isH ? 0 : -8} y={isH ? 14 : 3} textAnchor={isH ? "middle" : "end"} fontSize={9}>
              {typeof t === "number" ? (t < 1 ? t.toFixed(1) : Math.round(t)) : t}
            </text>
          </g>
        );
      })}
      {label && (
        <text
          x={isH ? (x1 + x2) / 2 : x1 - 36}
          y={isH ? y1 + 28 : (y1 + y2) / 2}
          textAnchor="middle"
          fontSize={10}
          transform={isH ? undefined : `rotate(-90, ${x1 - 36}, ${(y1 + y2) / 2})`}
        >
          {label}
        </text>
      )}
    </g>
  );
}

// Data helpers
function aggregateStates(windows, k) {
  const acc = Array.from({ length: k }, () => ({ count: 0, sumP: 0, sumPLocal: 0, sumM: 0, sumS: 0, nS: 0, sumEnt: 0 }));
  for (const w of windows) {
    const s = w.state;
    if (s == null || s < 0 || s >= k) continue;
    acc[s].count++;
    acc[s].sumP += w.P ?? 0;
    acc[s].sumPLocal += w.P_local ?? 0;
    acc[s].sumM += w.M ?? 0;
    if (w.S != null) { acc[s].sumS += w.S; acc[s].nS++; }
    acc[s].sumEnt += w.assignment_entropy ?? 0;
  }
  return acc.map((a, i) => ({
    state: i, count: a.count,
    meanP: a.count ? a.sumP / a.count : null,
    meanPLocal: a.count ? a.sumPLocal / a.count : null,
    meanM: a.count ? a.sumM / a.count : null,
    meanS: a.nS ? a.sumS / a.nS : null,
    meanEnt: a.count ? a.sumEnt / a.count : null,
  }));
}

function aggregateVideos(windows, k) {
  const byVid = {};
  for (const w of windows) {
    const vid = w.video_id ?? "?";
    if (!byVid[vid]) byVid[vid] = { video_id: vid, count: 0, sumP: 0, sumPLocal: 0, sumM: 0, sumS: 0, nS: 0, stateCounts: new Array(k).fill(0), N: 0 };
    const a = byVid[vid];
    a.count++;
    a.sumP += w.P ?? 0;
    a.sumPLocal += w.P_local ?? 0;
    a.sumM += w.M ?? 0;
    if (w.S != null) { a.sumS += w.S; a.nS++; }
    if (w.state != null && w.state >= 0 && w.state < k) a.stateCounts[w.state]++;
    if ((w.N ?? 0) > a.N) a.N = w.N;
  }
  return Object.values(byVid).map((a) => ({
    video_id: a.video_id, N: a.N, n_windows: a.count,
    dominant_state: a.stateCounts.indexOf(Math.max(...a.stateCounts)),
    meanP: a.count ? a.sumP / a.count : null,
    meanPLocal: a.count ? a.sumPLocal / a.count : null,
    meanM: a.count ? a.sumM / a.count : null,
    meanS: a.nS ? a.sumS / a.nS : null,
  })).sort((a, b) => a.video_id.localeCompare(b.video_id));
}

function buildHist(values, edges) {
  const counts = new Array(edges.length - 1).fill(0);
  for (const v of values) {
    if (v == null) continue;
    for (let i = 0; i < edges.length - 1; i++) {
      if (v >= edges[i] && (v < edges[i + 1] || i === edges.length - 2)) { counts[i]++; break; }
    }
  }
  return counts.map((c, i) => ({ lo: edges[i], hi: edges[i + 1], count: c }));
}

// Component 1: State Definition Table
function StateTable({ stateAgg, hasStimulus }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "9.5pt" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
            <th style={TH}>State</th>
            <th style={TH}>Count</th>
            <th style={TH}>Mean P</th>
            <th style={TH}>Mean P_local</th>
            <th style={TH}>Mean M</th>
            {hasStimulus && <th style={TH}>Mean S</th>}
          </tr>
        </thead>
        <tbody>
          {stateAgg.map((s) => {
            const means = [s.meanP, s.meanPLocal, s.meanM, ...(hasStimulus ? [s.meanS] : [])].filter((v) => v != null);
            const maxMean = means.length ? Math.max(...means) : null;
            const bold = (v) => v != null && v === maxMean ? { fontWeight: 700 } : {};
            return (
              <tr key={s.state} style={{ borderBottom: "1px solid var(--border-faint, #222)" }}>
                <td style={{ ...TD, display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: stateColor(s.state), display: "inline-block", flexShrink: 0 }} />
                  {s.state}
                </td>
                <td style={TD}>{s.count}</td>
                <td style={{ ...TD, ...bold(s.meanP) }}>{fmt1(s.meanP)}</td>
                <td style={{ ...TD, ...bold(s.meanPLocal) }}>{fmt1(s.meanPLocal)}</td>
                <td style={{ ...TD, ...bold(s.meanM) }}>{fmt1(s.meanM)}</td>
                {hasStimulus && <td style={{ ...TD, ...bold(s.meanS) }}>{fmt1(s.meanS)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// Component 2: M vs P Scatter
function MPScatter({ windows, hasStimulus }) {
  const W = 420, H = 280, pad = { t: 16, r: 16, b: 40, l: 48 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const sx = linScale(0, 1, 0, iw), sy = linScale(0, 1, ih, 0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      <g transform={`translate(${pad.l},${pad.t})`}>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <line key={`x${v}`} x1={sx(v)} y1={0} x2={sx(v)} y2={ih} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <line key={`y${v}`} x1={0} y1={sy(v)} x2={iw} y2={sy(v)} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />
        ))}
        {windows.map((w, i) => {
          const r = hasStimulus && w.S != null ? 2 + Math.abs(w.S) * 5 : 3.5;
          return <circle key={i} cx={sx(w.P ?? 0)} cy={sy(w.M ?? 0)} r={r} fill={stateColor(w.state ?? 0)} opacity={0.6} />;
        })}
        <SvgAxis x1={0} y1={ih} x2={iw} y2={ih} orient="bottom" label="Polarization P" ticks={[0, 0.25, 0.5, 0.75, 1]} scale={sx} />
        <SvgAxis x1={0} y1={0} x2={0} y2={ih} orient="left" label="Milling M" ticks={[0, 0.25, 0.5, 0.75, 1]} scale={sy} />
      </g>
    </svg>
  );
}

// Component 3: Transition Matrix Heatmap
function TransitionHeatmap({ matrix }) {
  const k = matrix.length;
  if (!k) return <p className="hint">No matrix data.</p>;
  const cell = Math.min(52, Math.floor(300 / k));
  const W = k * cell + 80, H = k * cell + 60;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      <g transform="translate(48,24)">
        {matrix[0].map((_, j) => (
          <text key={j} x={j * cell + cell / 2} y={-8} textAnchor="middle" fontSize={10} fill="#111">{j}</text>
        ))}
        {matrix.map((_, i) => (
          <text key={i} x={-6} y={i * cell + cell / 2 + 3} textAnchor="end" fontSize={10} fill="#111">{i}</text>
        ))}
        {matrix.map((row, i) =>
          row.map((val, j) => (
            <g key={`${i}-${j}`}>
              <rect x={j * cell} y={i * cell} width={cell} height={cell}
                fill={stateColor(j)} opacity={0.12 + Math.max(0, Math.min(1, val)) * 0.88}
                stroke="var(--bg, #111)" strokeWidth={1} />
              <text x={j * cell + cell / 2} y={i * cell + cell / 2 + 4}
                textAnchor="middle" fontSize={9} fill={val > 0.5 ? "#fff" : "#111"}>
                {val.toFixed(2)}
              </text>
            </g>
          ))
        )}
        <text x={k * cell / 2} y={k * cell + 22} textAnchor="middle" fontSize={10} fill="#111">To state</text>
        <text x={-32} y={k * cell / 2} textAnchor="middle" fontSize={10} fill="#111"
          transform={`rotate(-90,-32,${k * cell / 2})`}>From state</text>
      </g>
    </svg>
  );
}

// Components 4+5: Side-by-side bar chart
function TwoConditionBars({ condA, condB, yLabel }) {
  const allVals = [...(condA?.values ?? []), ...(condB?.values ?? [])].filter((v) => v != null);
  const maxV = allVals.length ? Math.max(...allVals) * 1.15 : 1;
  const k = Math.max((condA?.values ?? []).length, (condB?.values ?? []).length);
  if (!k) return <p className="hint">No data.</p>;
  const W = Math.max(280, k * 70 + 80), H = 220;
  const pad = { t: 16, r: 20, b: 48, l: 52 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const bw = (iw / k) * 0.36;
  const sy = linScale(0, maxV, ih, 0);
  const ticks = Array.from({ length: 5 }, (_, i) => +(maxV / 4 * i).toFixed(2));
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
        <g transform={`translate(${pad.l},${pad.t})`}>
          {ticks.map((v) => <line key={v} x1={0} y1={sy(v)} x2={iw} y2={sy(v)} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />)}
          {Array.from({ length: k }, (_, i) => {
            const cx = (iw / k) * (i + 0.5);
            const vA = condA?.values?.[i], vB = condB?.values?.[i];
            return (
              <g key={i}>
                <circle cx={cx} cy={ih + 14} r={4} fill={stateColor(i)} />
                <text x={cx} y={ih + 28} textAnchor="middle" fontSize={9} fill="#111">{i}</text>
                {vA != null && <rect x={cx - bw - 1} y={sy(vA)} width={bw} height={ih - sy(vA)} fill={COND_COLORS.a} opacity={0.85} rx={2} />}
                {vB != null && <rect x={cx + 1} y={sy(vB)} width={bw} height={ih - sy(vB)} fill={COND_COLORS.b} opacity={0.85} rx={2} />}
              </g>
            );
          })}
          <SvgAxis x1={0} y1={0} x2={0} y2={ih} orient="left" label={yLabel} ticks={ticks} scale={sy} />
          <line x1={0} y1={ih} x2={iw} y2={ih} stroke="var(--axis, #555)" strokeWidth={1} />
        </g>
      </svg>
      <div style={{ display: "flex", gap: 16, fontSize: "9pt", marginTop: 4 }}>
        {condA && <span><span style={{ display: "inline-block", width: 10, height: 10, background: COND_COLORS.a, marginRight: 4 }} />{condA.label}</span>}
        {condB && <span><span style={{ display: "inline-block", width: 10, height: 10, background: COND_COLORS.b, marginRight: 4 }} />{condB.label}</span>}
      </div>
    </div>
  );
}

// Component 6: State Sequence Swimlane
function StateSwimlane({ windows, k, nameOf }) {
  const videos = useMemo(() => {
    const m = {};
    for (const w of windows) {
      const vid = w.video_id ?? "?";
      if (!m[vid]) m[vid] = [];
      m[vid].push(w);
    }
    return Object.entries(m).sort((a, b) => naturalCompare(nameOf(a[0]), nameOf(b[0])));
  }, [windows, nameOf]);

  if (!videos.length) return <p className="hint">No windows data.</p>;
  const laneH = 22, gap = 2;
  const maxWin = Math.max(...videos.map(([, ws]) => ws.length));
  const W = 560, H = videos.length * (laneH + gap) + 40;
  const iw = W - 120;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      {videos.map(([vid, ws], row) => {
        const sorted = [...ws].sort((a, b) => (a.window_index ?? 0) - (b.window_index ?? 0));
        const y = row * (laneH + gap) + 24;
        const cellW = iw / Math.max(maxWin, 1);
        return (
          <g key={vid} transform={`translate(0,${y})`}>
            <text x={112} y={laneH / 2 + 4} textAnchor="end" fontSize={8.5} fill="#111">
              {nameOf(vid).length > 16 ? "…" + nameOf(vid).slice(-14) : nameOf(vid)}
            </text>
            {sorted.map((w, wi) => (
              <rect key={wi} x={116 + wi * cellW} y={0} width={Math.max(1, cellW - 0.5)} height={laneH}
                fill={stateColor(w.state ?? 0)} />
            ))}
          </g>
        );
      })}
      {Array.from({ length: k }, (_, i) => (
        <g key={i} transform={`translate(${116 + i * 30}, ${H - 12})`}>
          <rect x={0} y={0} width={12} height={8} fill={stateColor(i)} />
          <text x={14} y={8} fontSize={8} fill="#111">{i}</text>
        </g>
      ))}
    </svg>
  );
}

// Component 7: P and M over time
function PMTimeline({ windows, videoId }) {
  const vw = useMemo(() =>
    [...windows.filter((w) => w.video_id === videoId)]
      .sort((a, b) => (a.window_index ?? 0) - (b.window_index ?? 0)),
    [windows, videoId]
  );
  if (!vw.length) return <p className="hint">No windows for this video.</p>;
  const W = 560, H = 240, pad = { t: 16, r: 16, b: 36, l: 48 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const n = vw.length;
  const sx = linScale(0, n - 1, 0, iw), sy = linScale(0, 1, ih, 0);
  const pts = (fn) => vw.map((w, i) => `${sx(i).toFixed(1)},${sy(fn(w)).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      <g transform={`translate(${pad.l},${pad.t})`}>
        {vw.map((w, i) => {
          const x0 = sx(i), x1 = i < n - 1 ? sx(i + 1) : iw;
          return <rect key={i} x={x0} y={0} width={x1 - x0} height={ih} fill={stateColor(w.state ?? 0)} opacity={0.12} />;
        })}
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <line key={v} x1={0} y1={sy(v)} x2={iw} y2={sy(v)} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />
        ))}
        <polyline points={pts((w) => w.P ?? 0)} fill="none" stroke={COND_COLORS.a} strokeWidth={1.5} />
        <polyline points={pts((w) => w.P_local ?? 0)} fill="none" stroke={COND_COLORS.c} strokeWidth={1.5} strokeDasharray="4 2" />
        <polyline points={pts((w) => w.M ?? 0)} fill="none" stroke={COND_COLORS.b} strokeWidth={1.5} />
        <SvgAxis x1={0} y1={ih} x2={iw} y2={ih} orient="bottom" label="Window"
          ticks={[0, Math.round(n / 4), Math.round(n / 2), Math.round(3 * n / 4), n - 1]} scale={sx} />
        <SvgAxis x1={0} y1={0} x2={0} y2={ih} orient="left" label="Value" ticks={[0, 0.25, 0.5, 0.75, 1]} scale={sy} />
      </g>
      <g transform={`translate(${pad.l + iw - 130}, ${pad.t + 4})`}>
        <rect x={0} y={0} width={8} height={8} fill={COND_COLORS.a} />
        <text x={12} y={8} fontSize={9} fill="#111">P</text>
        <rect x={28} y={0} width={8} height={8} fill={COND_COLORS.c} />
        <text x={40} y={8} fontSize={9} fill="#111">P_local</text>
        <rect x={82} y={0} width={8} height={8} fill={COND_COLORS.b} />
        <text x={94} y={8} fontSize={9} fill="#111">M</text>
      </g>
    </svg>
  );
}

// Component 8: Assignment Entropy per state
function EntropyChart({ stateAgg }) {
  const maxV = Math.max(...stateAgg.map((s) => s.meanEnt ?? 0), 0.01) * 1.2;
  const k = stateAgg.length;
  const W = Math.max(240, k * 70 + 60), H = 180, pad = { t: 12, r: 12, b: 40, l: 48 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const bw = (iw / k) * 0.5;
  const sy = linScale(0, maxV, ih, 0);
  const ticks = Array.from({ length: 5 }, (_, i) => +(maxV / 4 * i).toFixed(2));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      <g transform={`translate(${pad.l},${pad.t})`}>
        {ticks.map((v) => <line key={v} x1={0} y1={sy(v)} x2={iw} y2={sy(v)} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />)}
        {stateAgg.map((s, i) => {
          const cx = (iw / k) * (i + 0.5);
          const val = s.meanEnt ?? 0;
          return (
            <g key={i}>
              <rect x={cx - bw / 2} y={sy(val)} width={bw} height={ih - sy(val)} fill={stateColor(i)} opacity={0.85} rx={2} />
              <circle cx={cx} cy={ih + 14} r={4} fill={stateColor(i)} />
              <text x={cx} y={ih + 28} textAnchor="middle" fontSize={9} fill="#111">{i}</text>
            </g>
          );
        })}
        <SvgAxis x1={0} y1={0} x2={0} y2={ih} orient="left" label="Mean entropy" ticks={ticks} scale={sy} />
        <line x1={0} y1={ih} x2={iw} y2={ih} stroke="var(--axis, #555)" strokeWidth={1} />
      </g>
    </svg>
  );
}

// Component 9: Valid Fraction Histogram
function ValidFractionHist({ condA, condB }) {
  const edges = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.01];
  const histA = condA ? buildHist(condA.values, edges) : [];
  const histB = condB ? buildHist(condB.values, edges) : [];
  const maxC = Math.max(...histA.map((b) => b.count), ...histB.map((b) => b.count), 1);
  const n = edges.length - 1;
  const W = Math.max(280, n * 60 + 80), H = 200, pad = { t: 12, r: 12, b: 40, l: 48 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const bw = (iw / n) * 0.35;
  const sy = linScale(0, maxC, ih, 0);
  const labels = ["0.5", "0.6", "0.7", "0.8", "0.9", "1.0"];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      <g transform={`translate(${pad.l},${pad.t})`}>
        {[0, maxC * 0.5, maxC].map((v) => <line key={v} x1={0} y1={sy(v)} x2={iw} y2={sy(v)} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />)}
        {Array.from({ length: n }, (_, i) => {
          const cx = (iw / n) * (i + 0.5);
          return (
            <g key={i}>
              {histA[i]?.count > 0 && <rect x={cx - bw - 1} y={sy(histA[i].count)} width={bw} height={ih - sy(histA[i].count)} fill={COND_COLORS.a} opacity={0.85} rx={2} />}
              {histB[i]?.count > 0 && <rect x={cx + 1} y={sy(histB[i].count)} width={bw} height={ih - sy(histB[i].count)} fill={COND_COLORS.b} opacity={0.85} rx={2} />}
              <text x={cx} y={ih + 12} textAnchor="middle" fontSize={9} fill="#111">{labels[i]}</text>
            </g>
          );
        })}
        <SvgAxis x1={0} y1={0} x2={0} y2={ih} orient="left" label="Count"
          ticks={[0, Math.round(maxC * 0.5), maxC].map(Math.round)} scale={sy} />
        <line x1={0} y1={ih} x2={iw} y2={ih} stroke="var(--axis, #555)" strokeWidth={1} />
        <text x={iw / 2} y={ih + 28} textAnchor="middle" fontSize={10} fill="#111">Valid fraction</text>
      </g>
    </svg>
  );
}

// Component 10: Per-Video Summary Table
function VideoSummaryTable({ rows, anyStimulus }) {
  const [sortCol, setSortCol] = useState("video_name");
  const [sortDir, setSortDir] = useState(1);

  function toggleSort(col) {
    if (col === sortCol) setSortDir(-sortDir);
    else { setSortCol(col); setSortDir(1); }
  }

  const sorted = [...rows].sort((a, b) => {
    const va = a[sortCol] ?? "", vb = b[sortCol] ?? "";
    return (typeof va === "string" ? naturalCompare(va, vb) : va - vb) * sortDir;
  });

  function ColH({ col, label }) {
    return (
      <th style={{ ...TH, cursor: "pointer", userSelect: "none" }} onClick={() => toggleSort(col)}>
        {label}{sortCol === col ? (sortDir > 0 ? " ↑" : " ↓") : ""}
      </th>
    );
  }

  return (
    <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: 320 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "9pt" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
            <ColH col="video_name" label="Video" />
            <ColH col="condition" label="Condition" />
            <ColH col="N" label="N" />
            <ColH col="n_windows" label="Windows" />
            <ColH col="dominant_state" label="Dom. state" />
            <ColH col="meanP" label="Mean P" />
            <ColH col="meanPLocal" label="Mean P_local" />
            <ColH col="meanM" label="Mean M" />
            {anyStimulus && <ColH col="meanS" label="Mean S" />}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border-faint, #1a1a1a)" }}>
              <td style={TD}>{r.video_name}</td>
              <td style={TD}>
                <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: r.conditionColor, marginRight: 6 }} />
                {r.condition}
              </td>
              <td style={TDN}>{r.N}</td>
              <td style={TDN}>{r.n_windows}</td>
              <td style={TD}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: stateColor(r.dominant_state), display: "inline-block" }} />
                  {r.dominant_state}
                </span>
              </td>
              <td style={TDN}>{fmt1(r.meanP)}</td>
              <td style={TDN}>{fmt1(r.meanPLocal)}</td>
              <td style={TDN}>{fmt1(r.meanM)}</td>
              {anyStimulus && <td style={TDN}>{fmt1(r.meanS)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Component 11: N vs State fraction
function NvsStatePlot({ windows, k }) {
  const byN = useMemo(() => {
    const m = {};
    for (const w of windows) {
      const n = w.N;
      if (n == null || w.state == null) continue;
      if (!m[n]) m[n] = { N: n, counts: new Array(k).fill(0), total: 0 };
      m[n].counts[w.state]++;
      m[n].total++;
    }
    return Object.values(m).sort((a, b) => a.N - b.N);
  }, [windows, k]);

  if (!byN.length) return <p className="hint">No data.</p>;
  const Ns = byN.map((d) => d.N);
  const [minN, maxN] = [Ns[0], Ns[Ns.length - 1]];
  const W = 440, H = 240, pad = { t: 16, r: 16, b: 36, l: 48 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const sx = linScale(minN, maxN === minN ? minN + 1 : maxN, 0, iw), sy = linScale(0, 1, ih, 0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }}>
      <g transform={`translate(${pad.l},${pad.t})`}>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => <line key={v} x1={0} y1={sy(v)} x2={iw} y2={sy(v)} stroke="var(--grid, #2a2a2a)" strokeWidth={0.5} />)}
        {Array.from({ length: k }, (_, si) => (
          <polyline key={si}
            points={byN.map((d) => `${sx(d.N).toFixed(1)},${sy(d.total ? d.counts[si] / d.total : 0).toFixed(1)}`).join(" ")}
            fill="none" stroke={stateColor(si)} strokeWidth={2} />
        ))}
        {byN.map((d, di) =>
          Array.from({ length: k }, (_, si) => (
            <circle key={`${di}-${si}`} cx={sx(d.N)} cy={sy(d.total ? d.counts[si] / d.total : 0)} r={3} fill={stateColor(si)} />
          ))
        )}
        <SvgAxis x1={0} y1={ih} x2={iw} y2={ih} orient="bottom" label="Group size N"
          ticks={[...new Set([minN, ...Ns.slice(0, 6), maxN])]} scale={sx} />
        <SvgAxis x1={0} y1={0} x2={0} y2={ih} orient="left" label="Fraction" ticks={[0, 0.25, 0.5, 0.75, 1]} scale={sy} />
      </g>
      <g transform={`translate(${pad.l + iw - k * 30 - 4}, ${pad.t + 4})`}>
        {Array.from({ length: k }, (_, i) => (
          <g key={i} transform={`translate(${i * 30}, 0)`}>
            <line x1={0} y1={5} x2={14} y2={5} stroke={stateColor(i)} strokeWidth={2} />
            <text x={16} y={9} fontSize={9} fill="#111">{i}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

// Cell styles
const TH = { textAlign: "left", padding: "5px 10px", fontSize: "9pt", color: "var(--text-muted, #888)", fontWeight: 600 };
const TD = { padding: "4px 10px", verticalAlign: "middle" };
const TDN = { ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" };

function Section({ title, children }) {
  return (
    <section style={{ marginBottom: 32 }}>
      <p className="section-label" style={{ marginBottom: 10 }}>{title}</p>
      {children}
    </section>
  );
}

const COND_LABELS = { stimulus: "Stimulus", no_stimulus: "No Stimulus" };

// Main dashboard
export default function CbResultsDashboard({ runIds, videoNames }) {
  const nameOf = useMemo(() => (id) => videoNames?.[id] ?? id, [videoNames]);
  const [results, setResults] = useState({});
  const [activeId, setActiveId] = useState(runIds[0]?.id ?? null);
  const [activeCond, setActiveCond] = useState(null);
  const [videoId, setVideoId] = useState(null);


  useEffect(() => {
    for (const { id } of runIds) {
      if (results[id]) continue;
      setResults((r) => ({ ...r, [id]: "loading" }));
      api.getCbResults(id)
        .then((data) => setResults((r) => ({ ...r, [id]: data })))
        .catch((e) => setResults((r) => ({ ...r, [id]: e })));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runIds.map((r) => r.id).join(",")]);

  const rawData = results[activeId];
  const isRawReady = rawData && rawData !== "loading" && !(rawData instanceof Error);

  // Experiment runs return { conditions: { stimulus: {...}, no_stimulus: {...} } }
  const conditionMap = isRawReady && rawData.conditions ? rawData.conditions : null;
  const conditionKeys = conditionMap ? Object.keys(conditionMap) : null;

  useEffect(() => {
    if (conditionKeys && (!activeCond || !conditionKeys.includes(activeCond))) {
      setActiveCond(conditionKeys[0]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conditionKeys?.join(",")]);

  useEffect(() => { setVideoId(null); }, [activeCond, activeId]);

  const activeData = conditionMap
    ? (activeCond ? conditionMap[activeCond] : null)
    : (isRawReady ? rawData : null);
  const isReady = Boolean(activeData);

  const k = isReady ? (activeData.best_k ?? activeData.transition_matrix?.length ?? 0) : 0;
  const windows = isReady ? activeData.windows : [];
  const allWindows = useMemo(() => {
    if (conditionMap) return Object.values(conditionMap).flatMap((d) => d.windows ?? []);
    return windows;
  }, [conditionMap, windows]);
  const stateAgg = useMemo(() => (isReady ? aggregateStates(windows, k) : []), [windows, k, isReady]);
  const hasStimulus = isReady ? activeData.has_stimulus : false;

  const videoList = useMemo(
    () => [...new Set(allWindows.map((w) => w.video_id).filter(Boolean))].sort((a, b) => naturalCompare(nameOf(a), nameOf(b))),
    [allWindows, nameOf],
  );
  useEffect(() => { if (videoList.length && !videoId) setVideoId(videoList[0]); }, [videoList]);

  const condPairs = useMemo(() => {
    if (conditionMap) {
      return Object.entries(conditionMap).map(([name, d], idx) => ({
        label: COND_LABELS[name] ?? name, id: name,
        k: d.best_k ?? d.transition_matrix?.length ?? 0,
        markov: d.markov, windows: d.windows, hasStimulus: d.has_stimulus, colorIdx: idx,
      }));
    }
    return runIds.map(({ label, id }, idx) => {
      const d = results[id];
      if (!d || d === "loading" || d instanceof Error) return null;
      return { label, id, k: d.best_k ?? d.transition_matrix?.length ?? 0, markov: d.markov, windows: d.windows, hasStimulus: d.has_stimulus, colorIdx: idx };
    });
  }, [conditionMap, results, runIds]);

  const condA = condPairs[0];
  const condB = condPairs[1] ?? null;

  const activePair = useMemo(
    () => condPairs.find((c) => c?.id === activeCond) ?? condA,
    [condPairs, activeCond, condA],
  );
  const kDiffer = Boolean(
    condA && condB &&
    (condA.markov?.stationary_distribution?.length ?? 0) !==
    (condB.markov?.stationary_distribution?.length ?? 0)
  );

  const videoRows = useMemo(() => {
    const rows = [];
    for (const cond of condPairs) {
      if (!cond) continue;
      for (const row of aggregateVideos(cond.windows, cond.k)) {
        rows.push({ ...row, video_name: nameOf(row.video_id), condition: cond.label, conditionColor: cond.colorIdx === 0 ? COND_COLORS.a : COND_COLORS.b });
      }
    }
    return rows;
  }, [condPairs, nameOf]);

  const anyStimulus = condPairs.some((c) => c?.hasStimulus);
  const showTabs = conditionMap ? conditionKeys.length > 1 : runIds.length > 1;

  if (!activeId) return <p className="hint">No run IDs provided.</p>;
  if (!rawData || rawData === "loading") return <p className="hint">Loading results…</p>;
  if (rawData instanceof Error) return <p style={{ color: "#f08080", fontSize: "9pt" }}>Failed to load: {rawData.message}</p>;
  if (conditionMap && !activeCond) return <p className="hint">Loading results…</p>;

  return (
    <div style={{ marginTop: 24 }}>
      {showTabs && (
        <div style={{ display: "flex", gap: 6, marginBottom: 16, position: "sticky", top: 68, zIndex: 10, background: "var(--bg)", padding: "6px 0" }}>
          {conditionMap
            ? conditionKeys.map((name, idx) => (
                <button key={name}
                  style={{ padding: "4px 14px", borderRadius: 4, cursor: "pointer",
                    background: activeCond === name ? (idx === 0 ? COND_COLORS.a : COND_COLORS.b) : "transparent",
                    color: activeCond === name ? "#fff" : "var(--fg, #ccc)",
                    border: `1px solid ${idx === 0 ? COND_COLORS.a : COND_COLORS.b}`, fontSize: "9pt" }}
                  onClick={() => setActiveCond(name)}>
                  {COND_LABELS[name] ?? name}
                </button>
              ))
            : runIds.map(({ label, id }, idx) => (
                <button key={id}
                  style={{ padding: "4px 14px", borderRadius: 4, cursor: "pointer",
                    background: activeId === id ? (idx === 0 ? COND_COLORS.a : COND_COLORS.b) : "transparent",
                    color: activeId === id ? "#fff" : "var(--fg, #ccc)",
                    border: `1px solid ${idx === 0 ? COND_COLORS.a : COND_COLORS.b}`, fontSize: "9pt" }}
                  onClick={() => setActiveId(id)}>
                  {label}
                </button>
              ))
          }
        </div>
      )}

      <Section title="GMM-Identified Behavioral States">
        <StateTable stateAgg={stateAgg} hasStimulus={hasStimulus} />
      </Section>

      <Section title="Milling vs. Polarization">
        <MPScatter windows={windows} hasStimulus={hasStimulus} />
        {hasStimulus && <p className="hint" style={{ marginTop: 4 }}>Dot size encodes |S|.</p>}
      </Section>

      <Section title="Transition matrix">
        <TransitionHeatmap matrix={activeData.transition_matrix ?? []} />
      </Section>

      <Section title="Mean dwell time per state">
        {kDiffer && <p className="hint" style={{ marginBottom: 6 }}>(Chosen K value is different depending on Stimulus)</p>}
        <TwoConditionBars yLabel="Seconds"
          condA={kDiffer
            ? (activePair ? { label: activePair.label, values: activePair.markov.mean_dwell_seconds } : null)
            : (condA ? { label: condA.label, values: condA.markov.mean_dwell_seconds } : null)}
          condB={kDiffer ? null : (condB ? { label: condB.label, values: condB.markov.mean_dwell_seconds } : null)} />
      </Section>

      <Section title="Stationary distribution">
        {kDiffer && <p className="hint" style={{ marginBottom: 6 }}>(Chosen K value is different depending on Stimulus)</p>}
        <TwoConditionBars yLabel="Fraction"
          condA={kDiffer
            ? (activePair ? { label: activePair.label, values: activePair.markov.stationary_distribution } : null)
            : (condA ? { label: condA.label, values: condA.markov.stationary_distribution } : null)}
          condB={kDiffer ? null : (condB ? { label: condB.label, values: condB.markov.stationary_distribution } : null)} />
      </Section>

      <Section title="State sequence">
        <div style={{ overflowY: "auto", maxHeight: 320 }}>
          <StateSwimlane windows={allWindows} k={k} nameOf={nameOf} />
        </div>
      </Section>

      <Section title="P, P_local & M over time">
        <div style={{ marginBottom: 8 }}>
          <select value={videoId ?? ""} onChange={(e) => setVideoId(e.target.value)} style={{ fontSize: "9pt" }}>
            {videoList.map((v) => <option key={v} value={v}>{nameOf(v)}</option>)}
          </select>
        </div>
        {videoId && <PMTimeline windows={allWindows} videoId={videoId} />}
      </Section>

      <Section title="Assignment entropy per state">
        <EntropyChart stateAgg={stateAgg} />
        <p className="hint" style={{ marginTop: 4 }}>High entropy: windows near state boundaries.</p>
      </Section>

      <Section title="Valid fraction distribution">
        <ValidFractionHist
          condA={condA ? { values: condA.windows.map((w) => w.valid_fraction) } : null}
          condB={condB ? { values: condB.windows.map((w) => w.valid_fraction) } : null} />
        {showTabs && (
          <div style={{ display: "flex", gap: 16, fontSize: "9pt", marginTop: 4 }}>
            {condPairs.filter(Boolean).map((c, i) => (
              <span key={c.label}><span style={{ display: "inline-block", width: 10, height: 10, background: i === 0 ? COND_COLORS.a : COND_COLORS.b, marginRight: 4 }} />{c.label}</span>
            ))}
          </div>
        )}
      </Section>

      <Section title="Per-video summary">
        <VideoSummaryTable rows={videoRows} anyStimulus={anyStimulus} />
      </Section>

      <Section title="Group size vs. state distribution">
        <NvsStatePlot windows={windows} k={k} />
        {showTabs && <p className="hint" style={{ marginTop: 4 }}>Showing active condition tab above.</p>}
      </Section>
    </div>
  );
}
