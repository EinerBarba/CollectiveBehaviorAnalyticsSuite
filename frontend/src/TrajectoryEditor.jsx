import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import * as api from "./api.js";

const CANVAS_WIDTH = 1080;

const COLORS = [
  "#F23535","#F24C35","#F26335","#F27935","#F29035","#F2A735","#F2BD35","#F2D435","#F2EB35","#E3F235",
  "#CCF235","#B6F235","#9FF235","#88F235","#72F235","#5BF235","#44F235","#35F23D","#35F254","#35F26A",
  "#35F281","#35F298","#35F2AE","#35F2C5","#35F2DC","#35F2F2","#35DCF2","#35C5F2","#35AEF2","#3598F2",
  "#3581F2","#356AF2","#3554F2","#353DF2","#4435F2","#5B35F2","#7235F2","#8835F2","#9F35F2","#B635F2",
];

// Trajectory markers using colors and shapes

const COLOR_STEP = 4;
const COLORS_PER_SHAPE = 10;
const SHAPES = ["circle", "triangle", "square", "pentagon", "hexagon"];
const SHAPE_SIDES = { triangle: 3, square: 4, pentagon: 5, hexagon: 6 };
const SHAPE_SCALE = { circle: 1, triangle: 1.3, square: 1.15, pentagon: 1.15, hexagon: 1.1 };
const UNASSIGNED_STYLE = { color: "#888", shape: "circle" };

function trajectoryStyle(trajectoryNumber) {
  const n = (((trajectoryNumber - 1) % (COLORS_PER_SHAPE * SHAPES.length)) + (COLORS_PER_SHAPE * SHAPES.length)) % (COLORS_PER_SHAPE * SHAPES.length);
  return {
    color: COLORS[(n % COLORS_PER_SHAPE) * COLOR_STEP],
    shape: SHAPES[Math.floor(n / COLORS_PER_SHAPE)],
  };
}

// Vertices for a polygon
function shapePoints(shape, cx, cy, r) {
  const sides = SHAPE_SIDES[shape];
  if (!sides) return null;
  const R = r * (SHAPE_SCALE[shape] ?? 1);
  const start = sides === 4 ? -Math.PI / 4 : -Math.PI / 2;
  return Array.from({ length: sides }, (_, i) => {
    const a = start + (i * 2 * Math.PI) / sides;
    return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
  });
}

// Fills marker
function drawMarker(ctx, shape, x, y, r) {
  ctx.beginPath();
  const pts = shapePoints(shape, x, y, r);
  if (pts) {
    pts.forEach(([px, py], i) => (i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
    ctx.closePath();
  } else {
    ctx.arc(x, y, r, 0, 2 * Math.PI);
  }
  ctx.fill();
  ctx.stroke();
}

// 5-point star
function drawStar(ctx, x, y, outerR) {
  const innerR = outerR * 0.45;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const rad = i % 2 === 0 ? outerR : innerR;
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const px = x + rad * Math.cos(a), py = y + rad * Math.sin(a);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
}

function ShapeIcon({ shape, color, size = 12 }) {
  const pts = shapePoints(shape, 0, 0, 1);
  const common = { fill: color, stroke: "rgba(0,0,0,0.6)", strokeWidth: 0.12 };
  return (
    <svg width={size} height={size} viewBox="-1.4 -1.4 2.8 2.8" style={{ flexShrink: 0 }}>
      {pts
        ? <polygon points={pts.map((p) => p.join(",")).join(" ")} {...common} />
        : <circle r="1" {...common} />}
    </svg>
  );
}

function parseCSV(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
  if (lines.length === 0) return { headers: [], tracks: new Map() };
  const headers = lines[0].split(",");
  const tidIdx = headers.indexOf("track_id");
  const frameIdx = headers.indexOf("frame");
  const xIdx = headers.indexOf("x");
  const yIdx = headers.indexOf("y");
  const isPredIdx = headers.indexOf("is_predicted");
  const tracks = new Map();
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    if (parts.length < 5) continue;
    const tid = parseInt(parts[tidIdx], 10);
    const frame = parseInt(parts[frameIdx], 10);
    const x = parseFloat(parts[xIdx]);
    const y = parseFloat(parts[yIdx]);
    const is_predicted = parts[isPredIdx]?.trim().toLowerCase() === "true";
    if (!tracks.has(tid)) tracks.set(tid, []);
    tracks.get(tid).push({ frame, x, y, is_predicted, _row: parts });
  }
  for (const [, pts] of tracks) pts.sort((a, b) => a.frame - b.frame);
  return { headers, tracks };
}

// Rebuild track points from saved CSV rows
function pointsFromRows(headers, rows) {
  const frameIdx = headers.indexOf("frame");
  const xIdx = headers.indexOf("x");
  const yIdx = headers.indexOf("y");
  const isPredIdx = headers.indexOf("is_predicted");
  const pts = rows.map((row) => ({
    frame: parseInt(row[frameIdx], 10),
    x: parseFloat(row[xIdx]),
    y: parseFloat(row[yIdx]),
    is_predicted: row[isPredIdx]?.trim().toLowerCase() === "true",
    _row: [...row],
  }));
  return pts.sort((a, b) => a.frame - b.frame);
}

function serializeCSV(headers, tracks) {
  const tidIdx = headers.indexOf("track_id");
  const rows = [];
  const sortedTids = [...tracks.keys()].sort((a, b) => a - b);
  for (const tid of sortedTids) {
    for (const pt of tracks.get(tid)) {
      const row = [...pt._row];
      row[tidIdx] = String(tid);
      rows.push(row.join(","));
    }
  }
  return [headers.join(","), ...rows].join("\n");
}

function firstReal(pts) {
  return pts.find((p) => !p.is_predicted) ?? pts[0];
}

function lastReal(pts) {
  for (let i = pts.length - 1; i >= 0; i--) if (!pts[i].is_predicted) return pts[i];
  return pts[pts.length - 1];
}

function getPositionAtFrame(points, frame) {
  for (const pt of points) {
    if (pt.frame === frame) return pt;
    if (pt.frame > frame) break;
  }
  return null;
}

function autoSort(tracks, numTrajectories) {
  const allPts = [...tracks.values()];
  if (allPts.length === 0) return { assignments: {}, unassigned: [] };

  const minFrame = Math.min(...allPts.map((pts) => pts[0]?.frame ?? Infinity));
  const START_TOLERANCE = 10;
  const trackList = [...tracks.entries()];
  const used = new Set();
  const assignments = {};
  for (let t = 1; t <= numTrajectories; t++) assignments[String(t)] = [];

  for (let t = 1; t <= numTrajectories; t++) {
    let startTid = null, startFrameFound = Infinity;
    for (const [tid, pts] of trackList) {
      if (used.has(tid)) continue;
      const s = pts[0]?.frame ?? Infinity;
      if (s <= minFrame + START_TOLERANCE && s < startFrameFound) {
        startFrameFound = s;
        startTid = tid;
      }
    }
    if (startTid === null) break;
    assignments[String(t)].push(startTid);
    used.add(startTid);
    let endFrame = tracks.get(startTid).at(-1)?.frame ?? 0;

    let chaining = true;
    while (chaining) {
      let nextTid = null, nextStart = Infinity;
      for (const [tid, pts] of trackList) {
        if (used.has(tid)) continue;
        const s = pts[0]?.frame ?? Infinity;
        if (s > endFrame && s < nextStart) { nextStart = s; nextTid = tid; }
      }
      if (nextTid === null) { chaining = false; break; }
      assignments[String(t)].push(nextTid);
      used.add(nextTid);
      endFrame = tracks.get(nextTid).at(-1)?.frame ?? endFrame;
    }
  }

  const unassigned = [...tracks.keys()].filter((tid) => !used.has(tid));
  return { assignments, unassigned };
}

function StaticChip({ tid, pts, styleMap }) {
  const first = pts.length > 0 ? pts[0].frame + 1 : "?";
  const last  = pts.length > 0 ? pts[pts.length - 1].frame + 1 : "?";
  const st = styleMap.get(tid) ?? UNASSIGNED_STYLE;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6,
      padding: "4px 8px", borderRadius: 4,
      fontSize: "9pt", marginBottom: 3,
      background: "rgba(255,255,255,0.04)",
      border: "1px solid var(--border, #333)",
    }}>
      <ShapeIcon shape={st.shape} color={st.color} />
      <span style={{ fontWeight: 500 }}>Track #{tid}</span>
      <span style={{ color: "var(--muted, #888)", fontSize: "8pt", whiteSpace: "nowrap" }}>
        {first}–{last} · {pts.length}f
      </span>
    </div>
  );
}


// Draw Missing Track preferences: Simple/Advanced mode and playback speed.
const DRAW_PREFS_KEY = "cba-draw-track-prefs";
const DRAW_SPEEDS = [1, 2, 4];
function loadDrawPrefs() {
  const defaults = { advanced: false, speed: 1 };
  try {
    const p = JSON.parse(localStorage.getItem(DRAW_PREFS_KEY) || "null");
    if (!p) return defaults;
    return {
      advanced: p.advanced === true,
      speed: DRAW_SPEEDS.includes(p.speed) ? p.speed : 1,
    };
  } catch { return defaults; }
}
function saveDrawPrefs(prefs) {
  try { localStorage.setItem(DRAW_PREFS_KEY, JSON.stringify(prefs)); } catch {}
}

// Trajectory viewer preferences: "Hide Track Lines" / "Hide Dots".
const VIEWER_PREFS_KEY = "cba-trajectory-viewer-prefs";
function loadViewerPrefs() {
  const defaults = { showLines: true, showDots: true };
  try {
    const p = JSON.parse(localStorage.getItem(VIEWER_PREFS_KEY) || "null");
    if (!p) return defaults;
    return { showLines: p.showLines !== false, showDots: p.showDots !== false };
  } catch { return defaults; }
}
function saveViewerPrefs(prefs) {
  try { localStorage.setItem(VIEWER_PREFS_KEY, JSON.stringify(prefs)); } catch {}
}

// Advanced mode: frames of human reaction delay removed from each press-and-hold recording.
const REACTION_LAG_FRAMES = 2;

function DrawTrackModal({ modal, tracks, unassigned, headers, styleMap, videoVersionId, frameStep, effectiveFrameCount, onGenerate, onClose }) {
  const canvasRef = useRef(null);
  const [image, setImage] = useState(null);
  const [modalFrame, setModalFrame] = useState(() => {
    // Start at the last frame of the before-track, or the first frame of the after-track for start gaps
    // (or frame 0 when the trajectory has no tracks at all)
    const f = modal.beforeEnd.frame >= 0 ? modal.beforeEnd.frame
      : modal.afterStart.x != null ? modal.afterStart.frame : 0;
    return Math.max(0, f);
  });
  const [keypoints, setKeypoints] = useState([]); // { frame, x, y }[]
  // Advanced mode: hold the mouse button and the video advances `speed` frames per step,
  const [advanced, setAdvanced] = useState(() => loadDrawPrefs().advanced);
  const [speed, setSpeed] = useState(() => loadDrawPrefs().speed);
  const [holding, setHolding] = useState(false);
  const [imageFrame, setImageFrame] = useState(null); 
  const pointerRef = useRef(null);                    
  const runRef = useRef(0);                           

  const { trajKey, beforeTid, afterTid, beforeEnd, afterStart } = modal;
  const gapStart = beforeEnd.frame + 1;
  const gapEnd = afterStart.frame - 1;
  const gap = gapEnd - gapStart + 1;
  const inGap = modalFrame >= gapStart && modalFrame <= gapEnd;
  const kpAtFrame = keypoints.find((kp) => kp.frame === modalFrame) ?? null;

  useEffect(() => {
    if (!videoVersionId) return;
    const safeFrame = Math.max(0, modalFrame);
    let blobUrl = null;
    let cancelled = false;
    api.getVideoFrame(videoVersionId, safeFrame * frameStep)
      .then((blob) => {
        if (cancelled) return;
        blobUrl = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          if (cancelled) return;
          setImage(img);
          setImageFrame(safeFrame);
        };
        img.src = blobUrl;
      })
      .catch(() => {});
    return () => { cancelled = true; if (blobUrl) URL.revokeObjectURL(blobUrl); };
  }, [videoVersionId, modalFrame, frameStep]);

  // Advanced-mode loop: each time the frame being shown changes while the button is held,
  // record the pointer position for that frame, then request the next frame (+speed).

  useEffect(() => {
    if (!advanced || !holding || imageFrame == null || imageFrame !== modalFrame) return;
    if (imageFrame < gapStart || imageFrame > gapEnd) { setHolding(false); return; }
    const p = pointerRef.current;
    if (p) {
      const run = runRef.current;
      setKeypoints((prev) => [...prev.filter((kp) => kp.frame !== imageFrame), { frame: imageFrame, x: p.x, y: p.y, run }]);
    }
    const next = imageFrame + speed;
    if (next > gapEnd) { setHolding(false); return; }
    setModalFrame(next);
  }, [advanced, holding, imageFrame]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image) return;
    const s = CANVAS_WIDTH / image.naturalWidth;
    canvas.width = CANVAS_WIDTH;
    canvas.height = Math.round(image.naturalHeight * s);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    // Faint previous path + larger dot at current frame
    for (const tid of [beforeTid, afterTid]) {
      if (tid === null) continue;
      const pts = tracks?.get(tid) ?? [];
      if (!pts.length) continue;
      const color = (styleMap.get(tid) ?? UNASSIGNED_STYLE).color;
      if (!advanced) {
        ctx.globalAlpha = 0.45;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        pts.forEach((pt, i) => {
          if (i === 0) ctx.moveTo(pt.x * s, pt.y * s);
          else ctx.lineTo(pt.x * s, pt.y * s);
        });
        ctx.stroke();
      }
      const cur = getPositionAtFrame(pts, modalFrame);
      if (cur && !cur.is_predicted) {
        ctx.globalAlpha = 1;
        ctx.fillStyle = color;
        ctx.strokeStyle = "rgba(0,0,0,0.6)";
        ctx.lineWidth = 1;
        // Star = a track bordering the gap being filled (all other tracks keep their trajectory's shape)
        drawStar(ctx, cur.x * s, cur.y * s, 9);
      }
    }

    // All other assigned tracks: dot at current frame only
    const unassignedSet = new Set(unassigned ?? []);
    for (const [tid, pts] of (tracks ?? new Map())) {
      if (unassignedSet.has(tid)) continue;
      if (tid === beforeTid || tid === afterTid) continue;
      const cur = getPositionAtFrame(pts, modalFrame);
      if (!cur) continue;
      const st = styleMap.get(tid) ?? UNASSIGNED_STYLE;
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = st.color;
      ctx.strokeStyle = "rgba(0,0,0,0.5)";
      ctx.lineWidth = 1;
      drawMarker(ctx, st.shape, cur.x * s, cur.y * s, 4.5);
    }

    const sorted = keypoints.slice().sort((a, b) => a.frame - b.frame);
    const refs = [beforeEnd, ...sorted, afterStart].filter((pt) => pt.x != null);
    if (!advanced && refs.length >= 2) {
      ctx.globalAlpha = 0.5;
      ctx.strokeStyle = "rgba(53,129,242,0.7)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      refs.forEach((pt, i) => {
        if (i === 0) ctx.moveTo(pt.x * s, pt.y * s);
        else ctx.lineTo(pt.x * s, pt.y * s);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.globalAlpha = 1;
    for (const kp of keypoints) {
      const isHere = kp.frame === modalFrame;
      if (advanced && !isHere) continue; // Avoid clutter of dots
      ctx.fillStyle = isHere ? "#3581f2" : "rgba(53,129,242,0.6)";
      ctx.strokeStyle = isHere ? "#fff" : "#000";
      ctx.lineWidth = isHere ? 2 : 1;
      ctx.beginPath();
      ctx.arc(kp.x * s, kp.y * s, isHere ? 8 : 6, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
    }

    ctx.globalAlpha = 1;
  }, [image, tracks, unassigned, styleMap, keypoints, modalFrame, beforeTid, afterTid, beforeEnd, afterStart, advanced]);

  // Pointer position in video coordinates, clamped to the frame.
  function pointerToVideo(e) {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const cx = Math.min(Math.max(((e.clientX - rect.left) * canvas.width) / rect.width, 0), canvas.width);
    const cy = Math.min(Math.max(((e.clientY - rect.top) * canvas.height) / rect.height, 0), canvas.height);
    const s = CANVAS_WIDTH / image.naturalWidth;
    return { x: cx / s, y: cy / s };
  }

  function handleCanvasClick(e) {
    if (advanced || !image || !inGap) return;
    const { x, y } = pointerToVideo(e);
    // Replace any existing keypoint at this frame
    setKeypoints((prev) => [...prev.filter((kp) => kp.frame !== modalFrame), { frame: modalFrame, x, y }]);
  }

  function handlePointerDown(e) {
    if (!advanced || !image || !inGap || e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId); // keep tracking if the pointer leaves the canvas
    pointerRef.current = pointerToVideo(e);
    runRef.current += 1;
    setHolding(true);
  }

  function handlePointerMove(e) {
    if (!advanced || !image) return;
    pointerRef.current = pointerToVideo(e);
  }

  function stopHolding() {
    setHolding(false);
  }

  function changeMode(adv) {
    setHolding(false);
    setAdvanced(adv);
    saveDrawPrefs({ advanced: adv, speed });
  }

  function changeSpeed(value) {
    setSpeed(value);
    saveDrawPrefs({ advanced, speed: value });
  }

  function handleGenerate() {
    const frameIdx = headers.indexOf("frame");
    const xIdx = headers.indexOf("x");
    const yIdx = headers.indexOf("y");
    const isPredIdx = headers.indexOf("is_predicted");
    const rowLen = headers.length;

    function makeRow(frame, x, y, isPred) {
      const row = Array(rowLen).fill("");
      if (frameIdx >= 0) row[frameIdx] = String(frame);
      if (xIdx >= 0) row[xIdx] = x.toFixed(2);
      if (yIdx >= 0) row[yIdx] = y.toFixed(2);
      if (isPredIdx >= 0) row[isPredIdx] = isPred ? "true" : "false";
      return row;
    }

    // In Advanced mode only Advanced recordings count; positions placed in Simple mode are ignored.
    const usable = advanced ? keypoints.filter((kp) => kp.run != null) : keypoints;

    // Reaction-time compensation for Advanced recordings
    const byFrame = new Map();
    for (const kp of usable) if (kp.run == null) byFrame.set(kp.frame, kp);
    const runs = new Map();
    for (const kp of usable) {
      if (kp.run == null) continue;
      if (!runs.has(kp.run)) runs.set(kp.run, []);
      runs.get(kp.run).push(kp);
    }
    for (const run of [...runs.keys()].sort((a, b) => a - b)) {
      const pts = runs.get(run).sort((a, b) => a.frame - b.frame);
      const firstFrame = pts[0].frame;
      for (const kp of pts) {
        if (kp.frame < firstFrame + REACTION_LAG_FRAMES) continue;
        byFrame.set(kp.frame - REACTION_LAG_FRAMES, { ...kp, frame: kp.frame - REACTION_LAG_FRAMES });
      }
    }
    const sorted = [...byFrame.values()].sort((a, b) => a.frame - b.frame);

    // Advanced recordings (no Simple-mode positions): the track is exactly what was recorded.
    // Frames are only filled in between recorded steps of the same hold (x2/x4 skip frames);
    // nothing is extended towards the neighboring tracks, so the rest of the gap stays missing.
    if (!usable.some((kp) => kp.run == null)) {
      if (sorted.length === 0) return;
      const dense = [];
      const holds = new Map();
      for (const kp of sorted) {
        if (!holds.has(kp.run)) holds.set(kp.run, []);
        holds.get(kp.run).push(kp);
      }
      for (const hold of holds.values()) {
        hold.forEach((P1, i) => {
          dense.push({ frame: P1.frame, x: P1.x, y: P1.y, is_predicted: false, _row: makeRow(P1.frame, P1.x, P1.y, false) });
          const P2 = hold[i + 1];
          if (!P2) return;
          for (let f = P1.frame + 1; f < P2.frame; f++) {
            const t = (f - P1.frame) / (P2.frame - P1.frame);
            const x = P1.x + t * (P2.x - P1.x);
            const y = P1.y + t * (P2.y - P1.y);
            dense.push({ frame: f, x, y, is_predicted: false, _row: makeRow(f, x, y, false) });
          }
        });
      }
      dense.sort((a, b) => a.frame - b.frame);
      onGenerate(dense, trajKey, beforeTid, afterTid);
      return;
    }

    if (sorted.length === 0) return;
    const refs = beforeEnd.x == null ? [...sorted] : [beforeEnd, ...sorted];
    const points = [];
    const lastRef = refs.length - 1;

    for (let i = 0; i < refs.length; i++) {
      const P1 = refs[i], P2 = refs[i + 1];
      if (i > 0 || beforeEnd.x == null) {
        points.push({ frame: P1.frame, x: P1.x, y: P1.y, is_predicted: false, _row: makeRow(P1.frame, P1.x, P1.y, false) });
      }
      if (i === lastRef) break;
      for (let f = P1.frame + 1; f < P2.frame; f++) {
        const t = (f - P1.frame) / (P2.frame - P1.frame);
        const x = P1.x + t * (P2.x - P1.x);
        const y = P1.y + t * (P2.y - P1.y);
        points.push({ frame: f, x, y, is_predicted: false, _row: makeRow(f, x, y, false) });
      }
    }
    points.sort((a, b) => a.frame - b.frame);

    onGenerate(points, trajKey, beforeTid, afterTid);
  }

  function jump(delta) {
    if (effectiveFrameCount == null) return;
    setModalFrame((f) => Math.max(0, Math.min(effectiveFrameCount - 1, f + delta)));
  }

  function jumpTo(frame) {
    if (effectiveFrameCount == null) return;
    setModalFrame(Math.max(0, Math.min(effectiveFrameCount - 1, frame)));
  }

  const beforePts = tracks?.get(beforeTid) ?? [];
  const afterPts = tracks?.get(afterTid) ?? [];
  const sorted = keypoints.slice().sort((a, b) => a.frame - b.frame);
  const recorded = sorted.filter((kp) => kp.run != null);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        borderRadius: 8, padding: 32,
        width: "min(98vw, 2000px)", maxHeight: "96vh",
        overflowY: "auto",
        display: "flex", flexDirection: "column", gap: 18,
        boxShadow: "0 8px 40px rgba(0,0,0,0.45)",
      }}>

        {/* Close row */}
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10 }}>
          {advanced && (
            <label className="hint" style={{
              display: "flex", flexDirection: "row", flexWrap: "nowrap", alignItems: "center", gap: 6,
              fontSize: "9pt", whiteSpace: "nowrap", margin: "0 16px 0 0",
            }}>
              Speed
              <select
                value={speed}
                onChange={(e) => changeSpeed(Number(e.target.value))}
                style={{ width: 52, minWidth: 0, padding: "2px 4px" }}
              >
                <option value={1}>x1</option>
                <option value={2}>x2</option>
                <option value={4}>x4</option>
              </select>
            </label>
          )}
          <div style={{ display: "flex" }} role="group" aria-label="Drawing mode">
            <button
              className={!advanced ? "primary" : undefined}
              onClick={() => changeMode(false)}
              style={{ borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
            >Simple</button>
            <button
              className={advanced ? "primary" : undefined}
              onClick={() => changeMode(true)}
              style={{ borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
            >Advanced</button>
          </div>
          <button onClick={onClose}>✕ Close</button>
        </div>

        {/* Body */}
        <div style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>

          {/* Left: mini video player */}
          <div style={{ flex: "0 0 58%", minWidth: 0 }}>
            <canvas
              ref={canvasRef}
              onClick={handleCanvasClick}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={stopHolding}
              onPointerCancel={stopHolding}
              style={{
                touchAction: advanced ? "none" : undefined,
                display: "block", width: "100%", height: "auto",
                borderRadius: 4, cursor: inGap ? "crosshair" : "default",
                border: `2px solid ${inGap ? (kpAtFrame ? "var(--success, #35b858)" : "var(--accent)") : "transparent"}`,
              }}
            />
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
              <button onClick={() => jumpTo(0)}>Start</button>
              <button onClick={() => jump(-100)}>−100</button>
              <button onClick={() => jump(-10)}>−10</button>
              <button onClick={() => jump(-1)}>−1</button>
              <span className="hint" style={{ margin: "0 4px", minWidth: 110, textAlign: "center", fontSize: "9pt" }}>
                Frame {modalFrame + 1}
              </span>
              <button onClick={() => jump(1)}>+1</button>
              <button onClick={() => jump(10)}>+10</button>
              <button onClick={() => jump(100)}>+100</button>
              <button onClick={() => jumpTo((effectiveFrameCount ?? 1) - 1)}>End</button>
            </div>
            <p className="hint" style={{ marginTop: 6, fontSize: "8.5pt" }}>
              {advanced
                ? inGap
                  ? `Hold the mouse button and follow the subject — the video advances ${speed} frame${speed > 1 ? "s" : ""} at a time while held. Release to pause.`
                  : `Gap: frames ${gapStart + 1}–${gapEnd + 1}. Navigate into the gap, then hold the mouse button to start.`
                : inGap
                ? kpAtFrame
                  ? `Position set at frame ${modalFrame + 1} — click to update, or navigate to another frame.`
                  : `Click on the subject to mark frame ${modalFrame + 1}.`
                : `Gap: frames ${gapStart + 1}–${gapEnd + 1}. Navigate into the gap to place positions.`}
            </p>
          </div>

          {/* Right: context + controls */}
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>

            {/* Trajectory context */}
            <div style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px" }}>
              <p className="section-label" style={{ fontSize: "8.5pt", marginBottom: 6 }}>Trajectory {trajKey}</p>
              {beforeTid !== null
                ? <StaticChip tid={beforeTid} pts={beforePts} styleMap={styleMap} />
                : <div style={{ padding: "4px 8px", fontSize: "8.5pt", color: "var(--muted)", marginBottom: 3 }}>▲ Video Start</div>}
              <div style={{
                padding: "5px 8px", borderRadius: 4, marginBottom: 3,
                border: "1px dashed var(--border)", background: "var(--bg)",
                fontSize: "8.5pt", color: "var(--muted)",
                display: "flex", gap: 8, alignItems: "center",
              }}>
                <span>{gap} frames</span>
                {keypoints.length > 0 && (
                  <span style={{ color: "var(--muted)" }}>
                    {keypoints.length} position{keypoints.length !== 1 ? "s" : ""} placed
                  </span>
                )}
              </div>
              {afterTid !== null
                ? <StaticChip tid={afterTid} pts={afterPts} styleMap={styleMap} />
                : <div style={{ padding: "4px 8px", fontSize: "8.5pt", color: "var(--muted)", marginBottom: 3 }}>▼ Video End</div>}
            </div>

            <button
              className="primary"
              onClick={handleGenerate}
              disabled={(beforeEnd.x == null && keypoints.length === 0) || (advanced && recorded.length === 0)}
              style={{ fontSize: "9pt" }}
            >
              Generate Track
            </button>

            {/* Placed positions list */}
            {advanced && recorded.length > 0 && (
              <div style={{ fontSize: "8pt", color: "var(--muted)", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ flex: 1 }}>
                  {recorded.length} positions recorded (f{recorded[0].frame + 1}–f{recorded[recorded.length - 1].frame + 1})
                </span>
                <button
                  onClick={() => setKeypoints((prev) => prev.filter((kp) => kp.run == null))}
                  style={{ padding: "1px 6px", fontSize: "8pt" }}
                >Clear recording</button>
              </div>
            )}
            {!advanced && sorted.length > 0 && (
              <div style={{ fontSize: "8pt", color: "var(--muted)" }}>
                <p style={{ margin: "0 0 3px", fontWeight: 500 }}>Positions placed</p>
                {sorted.map((kp) => (
                  <div key={kp.frame} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ flex: 1 }}>f{kp.frame + 1} — ({Math.round(kp.x)}, {Math.round(kp.y)})</span>
                    <button
                      onClick={() => setKeypoints((prev) => prev.filter((k) => k.frame !== kp.frame))}
                      style={{ padding: "1px 5px", fontSize: "8pt", lineHeight: 1 }}
                    >×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


export default function TrajectoryEditor({
  videoVersionId, trajectoryFileVersionId, experimentFps, nativeFps, onSaved, maxTracks,
  progressLoadFvId, onProgressListChange, detectionsFvId, maxDistance, maxMissedFrames = 5,
}) {
  const canvasRef = useRef(null);
  const panelRef = useRef(null);
  // Give every track chip and "Missing" button the width and height of the largest one.
  // Runs after each render: reset to natural size, measure, then apply the max.
  useLayoutEffect(() => {
    const els = panelRef.current?.querySelectorAll("[data-uchip]");
    if (!els || els.length === 0) return;
    els.forEach((el) => { el.style.width = ""; el.style.height = ""; });
    const rects = Array.from(els, (el) => el.getBoundingClientRect());
    const widest = Math.max(...rects.map((r) => Math.ceil(r.width)));
    const tallest = Math.max(...rects.map((r) => Math.ceil(r.height)));
    els.forEach((el) => { el.style.width = `${widest}px`; el.style.height = `${tallest}px`; });
  });
  const [image, setImage] = useState(null);
  const [meta, setMeta] = useState(null);
  const [frameIndex, setFrameIndex] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [tracks, setTracks] = useState(null);
  const [loading, setLoading] = useState(true);
  // Viewer toggles are remembered between sessions (browser preference).
  const [showLines, setShowLines] = useState(() => loadViewerPrefs().showLines);
  const [showDots, setShowDots] = useState(() => loadViewerPrefs().showDots);
  useEffect(() => { saveViewerPrefs({ showLines, showDots }); }, [showLines, showDots]);
  const [assignments, setAssignments] = useState(null);
  const [unassigned, setUnassigned] = useState([]);
  const [selectedTid, setSelectedTid] = useState(null);
  const [dragOverZone, setDragOverZone] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [progressList, setProgressList] = useState([]);
  const [drawModal, setDrawModal] = useState(null);
  // Trajectory keys ("1", "2", …) the user marked as correctly finished; their track lists are frozen.
  const [locked, setLocked] = useState(() => new Set());
  const [pending, setPending] = useState([]);
  const [trackIter, setTrackIter] = useState({});
  const dragRef = useRef(null);
  const [dragHover, setDragHover] = useState(null);
  const [minFrames, setMinFrames] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateMsg, setGenerateMsg] = useState("");

  const originalTracksRef = useRef(null);

  const maxCount = Math.max(1, parseInt(maxTracks, 10) || 1);

  const resolvedNativeFps = nativeFps ?? meta?.fps;
  const frameStep = (experimentFps && resolvedNativeFps && experimentFps < resolvedNativeFps)
    ? Math.max(1, Math.round(resolvedNativeFps / experimentFps)) : 1;
  const effectiveFrameCount = meta ? Math.ceil(meta.frame_count / frameStep) : null;
  const effectiveFps = frameStep > 1 ? experimentFps : resolvedNativeFps;
  const minMissingFrames = effectiveFps ? Math.max(1, Math.round(effectiveFps)) : 2;

  useEffect(() => {
    if (!videoVersionId || !trajectoryFileVersionId) return;
    setLoading(true);
    setImage(null);
    setFrameIndex(null);
    setAssignments(null);
    setUnassigned([]);
    setLocked(new Set());
    setPending([]);
    setTrackIter({});
    setGenerateMsg("");
    originalTracksRef.current = null;
    setConfirmed(false);
    setConfirmError("");
    setSaveMsg("");

    Promise.all([
      api.getVideoMetadata(videoVersionId),
      api.downloadFileVersion(trajectoryFileVersionId),
    ])
      .then(([m, csvBlob]) => {
        setMeta(m);
        const step = (experimentFps && experimentFps < m.fps)
          ? Math.max(1, Math.round(m.fps / experimentFps)) : 1;
        const effCount = Math.ceil(m.frame_count / step);
        setFrameIndex(Math.floor((effCount - 1) / 2));
        return csvBlob.text();
      })
      .then((csvText) => {
        const parsed = parseCSV(csvText);
        setHeaders(parsed.headers);
        originalTracksRef.current = parsed.tracks;
        setTracks(parsed.tracks);
        const sorted = autoSort(parsed.tracks, maxCount);
        setAssignments(sorted.assignments);
        setUnassigned(sorted.unassigned);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [videoVersionId, trajectoryFileVersionId]);

  useEffect(() => {
    if (!trajectoryFileVersionId) return;
    api.listTrajectoryProgress(trajectoryFileVersionId)
      .then(setProgressList)
      .catch(() => {});
  }, [trajectoryFileVersionId]);

  useEffect(() => {
    onProgressListChange?.(progressList);
  }, [progressList]);

  useEffect(() => {
    if (!progressLoadFvId) return;
    loadProgress(progressLoadFvId);
  }, [progressLoadFvId]);

  useEffect(() => {
    if (!videoVersionId || frameIndex == null) return;
    let blobUrl = null;
    api.getVideoFrame(videoVersionId, frameIndex * frameStep)
      .then((blob) => {
        blobUrl = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => setImage(img);
        img.src = blobUrl;
      })
      .catch(() => {});
    return () => { if (blobUrl) URL.revokeObjectURL(blobUrl); };
  }, [videoVersionId, frameIndex, frameStep]);

  // Follow the subject: when the viewer moves out of the selected track's frames and into another
  // track of the same trajectory, select that track (no frame jump), so it can be split right there.
  const skipFollowRef = useRef(false);
  useEffect(() => {
    if (skipFollowRef.current) { skipFollowRef.current = false; return; }
    if (selectedTid === null || frameIndex == null || !tracks || !assignments) return;
    const range = (tid) => {
      const pts = tracks.get(tid);
      return pts?.length ? [pts[0].frame, pts[pts.length - 1].frame] : null;
    };
    const cur = range(selectedTid);
    if (cur && frameIndex >= cur[0] && frameIndex <= cur[1]) return; // still inside the selected track
    const key = Object.keys(assignments).find((k) => assignments[k].includes(selectedTid));
    if (!key) return; // unassigned tracks don't belong to a trajectory
    const next = assignments[key].find((tid) => {
      if (tid === selectedTid) return false;
      const r = range(tid);
      return r && frameIndex >= r[0] && frameIndex <= r[1];
    });
    if (next !== undefined) setSelectedTid(next);
  }, [frameIndex, selectedTid, tracks, assignments]);

  // Color + shape per track, taken from the trajectory it currently sits in.
  const styleMap = useMemo(() => {
    const map = new Map();
    for (const tid of tracks?.keys() ?? []) map.set(tid, UNASSIGNED_STYLE);
    for (const [key, tids] of Object.entries(assignments ?? {})) {
      const st = trajectoryStyle(Number(key));
      for (const tid of tids) map.set(tid, st);
    }
    return map;
  }, [tracks, assignments]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image || !tracks || frameIndex == null) return;
    const s = CANVAS_WIDTH / image.naturalWidth;
    canvas.width = CANVAS_WIDTH;
    canvas.height = Math.round(image.naturalHeight * s);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    const unassignedSet = new Set(unassigned);
    const pendingSet = new Set(pending);

    if (showLines) {
      for (const [trackId, points] of tracks) {
        if (unassignedSet.has(trackId) || pendingSet.has(trackId) || points.length === 0) continue;
        const color = (styleMap.get(trackId) ?? UNASSIGNED_STYLE).color;
        const isSel = trackId === selectedTid;
        ctx.globalAlpha = isSel ? 1.0 : 0.35;
        ctx.strokeStyle = color;
        ctx.lineWidth = isSel ? 2.5 : 1.0;
        ctx.beginPath();
        let started = false;
        for (const pt of points) {
          if (!started) { ctx.moveTo(pt.x * s, pt.y * s); started = true; }
          else ctx.lineTo(pt.x * s, pt.y * s);
        }
        ctx.stroke();
      }
    }

    if (showDots) {
      for (const [trackId, points] of tracks) {
        if (unassignedSet.has(trackId)) continue;
        const cur = getPositionAtFrame(points, frameIndex);
        if (!cur) continue;
        const st = styleMap.get(trackId) ?? UNASSIGNED_STYLE;
        const isSel = trackId === selectedTid;
        ctx.globalAlpha = 1.0;
        ctx.fillStyle = st.color;
        ctx.strokeStyle = isSel ? "#fff" : "rgba(0,0,0,0.6)";
        ctx.lineWidth = isSel ? 1.5 : 1.0;
        drawMarker(ctx, st.shape, cur.x * s, cur.y * s, isSel ? 7 : 5);
        if (isSel && pendingSet.has(trackId)) {
          ctx.strokeStyle = "#F2D435";
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.arc(cur.x * s, cur.y * s, 12, 0, 2 * Math.PI);
          ctx.stroke();
        }
      }
    }

    if (dragHover) {
      const cur = getPositionAtFrame(tracks.get(dragHover.tid) ?? [], frameIndex);
      if (cur) {
        const isLocked = locked.has(dragHover.key);
        const color = isLocked ? "#f08080" : "#ffffff";
        const px = cur.x * s, py = cur.y * s;
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(px, py, 13, 0, 2 * Math.PI);
        ctx.stroke();
        const label = `Trajectory ${dragHover.key}${isLocked ? " (locked)" : ""}`;
        ctx.font = "bold 13px sans-serif";
        const w = ctx.measureText(label).width + 10;
        const lx = Math.min(px + 16, canvas.width - w - 2);
        const ly = Math.max(py - 30, 2);
        ctx.fillStyle = "rgba(0,0,0,0.85)";
        ctx.fillRect(lx, ly, w, 20);
        ctx.fillStyle = color;
        ctx.fillText(label, lx + 5, ly + 14);
      }
    }

    ctx.globalAlpha = 1.0;
  }, [image, tracks, selectedTid, frameIndex, showLines, showDots, styleMap, unassigned, pending, dragHover, locked]);

  useEffect(() => { draw(); }, [draw]);

  function jump(delta) {
    if (!effectiveFrameCount || frameIndex == null) return;
    setFrameIndex(Math.max(0, Math.min(effectiveFrameCount - 1, frameIndex + delta)));
  }

  function jumpTo(frame) {
    if (!effectiveFrameCount) return;
    setFrameIndex(Math.max(0, Math.min(effectiveFrameCount - 1, frame)));
  }

  function handleCanvasClick(e) {
    if (!image || !tracks) return;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const cx = ((e.clientX - rect.left) * canvas.width) / rect.width;
    const cy = ((e.clientY - rect.top) * canvas.height) / rect.height;
    const s = CANVAS_WIDTH / image.naturalWidth;
    const RADIUS_SQ = 14 * 14;
    let best = null, bestDist = RADIUS_SQ;
    for (const [tid, points] of tracks) {
      const pt = getPositionAtFrame(points, frameIndex);
      if (!pt) continue;
      const d = (pt.x * s - cx) ** 2 + (pt.y * s - cy) ** 2;
      if (d < bestDist) { bestDist = d; best = tid; }
    }
    setSelectedTid(best !== null ? (selectedTid === best ? null : best) : null);
  }

  function zoneOf(tid) {
    return Object.keys(assignments ?? {}).find((k) => assignments[k].includes(tid)) ?? null;
  }

  function toggleLock(key) {
    setLocked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function moveToUnassigned(tid) {
    if (locked.has(zoneOf(tid))) return;
    setAssignments((prev) => {
      const next = {};
      for (let t = 1; t <= maxCount; t++) {
        next[String(t)] = (prev?.[String(t)] ?? []).filter((x) => x !== tid);
      }
      return next;
    });
    setUnassigned((prev) => (prev.includes(tid) ? prev : [...prev, tid]));
    setPending((prev) => prev.filter((x) => x !== tid));
    setConfirmed(false);
  }

  function discardAllPending() {
    if (pending.length === 0) return;
    setUnassigned((prev) => [...prev, ...pending.filter((t) => !prev.includes(t))]);
    setPending([]);
    setConfirmed(false);
  }

  function handleDragStart(e, tid, source) {
    dragRef.current = { tid, source };
    e.dataTransfer.setData("text/plain", JSON.stringify({ tid, source }));
    e.dataTransfer.effectAllowed = "move";
  }

  function endDrag() {
    dragRef.current = null;
    setDragOverZone(null);
    setDragHover(null);
  }

  function markerAt(e) {
    const info = dragRef.current;
    if (!info || !image || !tracks || frameIndex == null || !showDots) return null;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const cx = ((e.clientX - rect.left) * canvas.width) / rect.width;
    const cy = ((e.clientY - rect.top) * canvas.height) / rect.height;
    const s = CANVAS_WIDTH / image.naturalWidth;
    let best = null, bestDist = 14 * 14;
    for (const [tid, points] of tracks) {
      if (tid === info.tid) continue;
      const key = zoneOf(tid);
      if (key === null) continue;
      const pt = getPositionAtFrame(points, frameIndex);
      if (!pt) continue;
      const d = (pt.x * s - cx) ** 2 + (pt.y * s - cy) ** 2;
      if (d < bestDist) { bestDist = d; best = { tid, key }; }
    }
    return best;
  }

  function handleCanvasDragOver(e) {
    if (!dragRef.current) return;
    const hit = markerAt(e);
    setDragHover((prev) => (prev?.tid === hit?.tid ? prev : hit));
    if (hit && !locked.has(hit.key)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    }
  }

  function handleCanvasDrop(e) {
    e.preventDefault();
    const info = dragRef.current;
    const hit = markerAt(e);
    endDrag();
    if (info && hit) moveTrack(info.tid, info.source, hit.key);
  }

  function handleDrop(e, dest) {
    e.preventDefault();
    setDragOverZone(null);
    let data;
    try { data = JSON.parse(e.dataTransfer.getData("text/plain")); } catch { return; }
    moveTrack(data.tid, data.source, dest);
  }

  function moveTrack(tid, source, dest) {
    if (dest === "new" || source === dest) return;
    if (locked.has(source) || locked.has(dest)) return; // locked trajectories are frozen

    if (source === "new") setPending((prev) => prev.filter((t) => t !== tid));
    setAssignments((prev) => {
      const next = {};
      for (let t = 1; t <= maxCount; t++) next[String(t)] = [...(prev?.[String(t)] ?? [])];
      if (source !== "unassigned" && source !== "new") next[source] = (next[source] ?? []).filter((t) => t !== tid);
      if (dest !== "unassigned" && !(next[dest] ?? []).includes(tid)) next[dest] = [...(next[dest] ?? []), tid];
      return next;
    });
    setUnassigned((prev) => {
      let next = [...prev];
      if (source === "unassigned") next = next.filter((t) => t !== tid);
      if (dest === "unassigned" && !next.includes(tid)) next = [...next, tid];
      return next;
    });
    setConfirmed(false);
  }

  async function confirmTrajectories() {
    if (!headers || !tracks || !assignments) return;
    for (let t = 1; t <= maxCount; t++) {
      const empty = (assignments[String(t)] ?? []).find((tid) => !(tracks.get(tid)?.length > 0));
      if (empty !== undefined) {
        setConfirmError(`Trajectory ${t} contains track #${empty}, which has no data. Remove it before confirming.`);
        return;
      }
    }
    setConfirming(true);
    setConfirmError("");
    try {
      const tidIdx = headers.indexOf("track_id");
      const mergedTracks = new Map();
      for (let t = 1; t <= maxCount; t++) {
        const tids = (assignments[String(t)] ?? []).slice().sort((a, b) => {
          const sA = tracks.get(a)?.[0]?.frame ?? 0;
          const sB = tracks.get(b)?.[0]?.frame ?? 0;
          return sA - sB;
        });
        if (tids.length === 0) continue;
        const frameMap = new Map();
        for (const tid of tids) {
          for (const pt of tracks.get(tid) ?? []) {
            if (!frameMap.has(pt.frame)) {
              frameMap.set(pt.frame, { ...pt, _row: [...pt._row] });
            } else {
              const ex = frameMap.get(pt.frame);
              if (!pt.is_predicted && ex.is_predicted) frameMap.set(pt.frame, { ...pt, _row: [...pt._row] });
            }
          }
        }
        const real = [...frameMap.values()].filter((p) => !p.is_predicted).sort((a, b) => a.frame - b.frame);
        for (let i = 0; i < real.length - 1; i++) {
          const a = real[i], b = real[i + 1];
          const gap = b.frame - a.frame - 1;
          if (gap < 1 || gap >= minMissingFrames) continue;
          for (let f = a.frame + 1; f < b.frame; f++) {
            const k = (f - a.frame) / (b.frame - a.frame);
            const x = a.x + k * (b.x - a.x);
            const y = a.y + k * (b.y - a.y);
            const row = Array(headers.length).fill("");
            row[headers.indexOf("frame")] = String(f);
            row[headers.indexOf("x")] = x.toFixed(2);
            row[headers.indexOf("y")] = y.toFixed(2);
            row[headers.indexOf("is_predicted")] = "false";
            frameMap.set(f, { frame: f, x, y, is_predicted: false, _row: row });
          }
        }
        const merged = [...frameMap.values()].sort((a, b) => a.frame - b.frame);
        for (const pt of merged) pt._row[tidIdx] = String(t);
        mergedTracks.set(t, merged);
      }
      const csv = serializeCSV(headers, mergedTracks);
      const result = await api.saveTrajectoryEdit(trajectoryFileVersionId, csv);
      setConfirmed(true);
      onSaved(result.file_version_id);
    } catch (err) {
      setConfirmError(err.message);
    } finally {
      setConfirming(false);
    }
  }

  async function saveProgress() {
    if (!assignments) return;
    setSaving(true);
    setSaveMsg("");
    try {
      // Tracks that are new or differ from the original CSV (split halves, drawn tracks),
      // stored as CSV rows so they can be rebuilt exactly on load.
      const original = originalTracksRef.current;
      const trackEdits = {};
      for (const [tid, pts] of tracks ?? []) {
        if (!original || original.get(tid) !== pts) trackEdits[String(tid)] = pts.map((p) => p._row);
      }
      const payload = JSON.stringify({
        source_file_version_id: trajectoryFileVersionId,
        trajectory_assignments: assignments,
        unassigned,
        locked_trajectories: [...locked],
        pending_tracks: pending,
        track_iterations: trackIter,
        track_edits: trackEdits,
        saved_at: new Date().toISOString(),
      });
      await api.saveTrajectoryProgress(trajectoryFileVersionId, payload);
      setSaveMsg("Progress saved.");
      const list = await api.listTrajectoryProgress(trajectoryFileVersionId);
      setProgressList(list);
    } catch (err) {
      setSaveMsg("Error: " + err.message);
    } finally {
      setSaving(false);
    }
  }

  async function loadProgress(fvId) {
    try {
      const blob = await api.downloadFileVersion(fvId);
      const text = await blob.text();
      const data = JSON.parse(text);
      const original = originalTracksRef.current;
      if (!original) { setSaveMsg("Tracks are still loading — try again in a moment."); return; }
      if (data.source_file_version_id && data.source_file_version_id !== trajectoryFileVersionId) {
        setSaveMsg("This progress belongs to a different tracking result and cannot be loaded.");
        return;
      }

      // 1. Original tracks + the edits (split halves / drawn tracks) saved with this progress.
      const nextTracks = new Map(original);
      for (const [tid, rows] of Object.entries(data.track_edits ?? {})) {
        nextTracks.set(Number(tid), pointsFromRows(headers, rows));
      }

      // 2. Assignments, checked against the tracks that actually exist.
      let missing = 0;
      const keep = (tids) => (tids ?? []).filter((t) => {
        if (nextTracks.has(t)) return true;
        missing++;
        return false;
      });
      const nextAssignments = {};
      for (let t = 1; t <= maxCount; t++) nextAssignments[String(t)] = keep(data.trajectory_assignments?.[String(t)]);
      const nextUnassigned = keep(data.unassigned);
      const nextPending = keep(data.pending_tracks);

      // 3. Any track the save doesn't mention goes to Unassigned
      const seen = new Set([...Object.values(nextAssignments).flat(), ...nextUnassigned, ...nextPending]);
      let unlisted = 0;
      for (const tid of nextTracks.keys()) {
        if (!seen.has(tid)) { nextUnassigned.push(tid); unlisted++; }
      }

      setTracks(nextTracks);
      setAssignments(nextAssignments);
      setUnassigned(nextUnassigned);
      setPending(nextPending);
      setTrackIter(data.track_iterations ?? {});
      setGenerateMsg("");
      setSelectedTid(null);
      setLocked(new Set((data.locked_trajectories ?? []).map(String)));
      setConfirmed(false);
      const notes = [];
      if (missing) notes.push(`${missing} saved track${missing > 1 ? "s" : ""} no longer exist${missing > 1 ? "" : "s"} and ${missing > 1 ? "were" : "was"} dropped`);
      if (unlisted) notes.push(`${unlisted} track${unlisted > 1 ? "s" : ""} not in the save ${unlisted > 1 ? "were" : "was"} added to Unassigned`);
      setSaveMsg(notes.length ? `Progress loaded — ${notes.join("; ")}.` : "Progress loaded.");
    } catch {
      setSaveMsg("Failed to load.");
    }
  }

  const endingMissing = (() => {
    if (!assignments || !tracks || effectiveFrameCount == null) return [];
    const keys = [];
    for (let t = 1; t <= maxCount; t++) {
      const key = String(t);
      if (locked.has(key)) continue;
      const tids = (assignments[key] ?? []).slice().sort((a, b) => (tracks.get(a)?.[0]?.frame ?? 0) - (tracks.get(b)?.[0]?.frame ?? 0));
      const lastPts = tids.length ? (tracks.get(tids[tids.length - 1]) ?? []) : [];
      const lastFrame = lastPts.length ? lastReal(lastPts).frame : -1;
      if ((effectiveFrameCount - 1) - lastFrame >= minMissingFrames) keys.push(key);
    }
    return keys;
  })();

  async function generateNextTracks() {
    if (!detectionsFvId || generating || pending.length > 0 || endingMissing.length === 0 || !tracks) return;
    setGenerating(true);
    setGenerateMsg("");
    try {
      const claimed = [];
      for (const pts of tracks.values()) for (const p of pts) claimed.push([p.frame, p.x, p.y]);
      const result = await api.generateNextTracks({
        detections_file_version_id: detectionsFvId,
        num_tracks: endingMissing.length,
        max_distance: Number(maxDistance) || 20,
        max_missed_frames: Number(maxMissedFrames) || 0,
        claimed,
      });
      if (result.tracks.length === 0) {
        setGenerateMsg("No new tracks found: every detection already belongs to a track.");
        return;
      }
      const frameIdx = headers.indexOf("frame");
      const xIdx = headers.indexOf("x");
      const yIdx = headers.indexOf("y");
      const predIdx = headers.indexOf("is_predicted");
      const iteration = Math.max(1, ...Object.values(trackIter)) + 1;
      let nextId = (tracks.size > 0 ? Math.max(...tracks.keys()) : 0) + 1;
      const added = new Map();
      const ids = [];
      for (const rows of result.tracks) {
        const pts = rows.map(([frame, x, y, isPred]) => {
          const row = Array(headers.length).fill("");
          if (frameIdx >= 0) row[frameIdx] = String(frame);
          if (xIdx >= 0) row[xIdx] = String(x);
          if (yIdx >= 0) row[yIdx] = String(y);
          if (predIdx >= 0) row[predIdx] = isPred ? "true" : "false";
          return { frame, x, y, is_predicted: !!isPred, _row: row };
        });
        added.set(nextId, pts);
        ids.push(nextId);
        nextId++;
      }
      const minLength = parseInt(minFrames, 10);
      const tooShort = minLength > 0 ? ids.filter((id) => added.get(id).length < minLength) : [];
      const kept = ids.filter((id) => !tooShort.includes(id));
      setTracks((prev) => new Map([...prev, ...added]));
      setPending(kept);
      if (tooShort.length > 0) setUnassigned((prev) => [...prev, ...tooShort]);
      setTrackIter((prev) => ({ ...prev, ...Object.fromEntries(ids.map((id) => [id, iteration])) }));
      setSelectedTid(null);
      setConfirmed(false);
      setGenerateMsg(
        `Iteration ${iteration}: ${ids.length} new track${ids.length > 1 ? "s" : ""} found`
        + (tooShort.length > 0 ? `, ${tooShort.length} under ${minLength} frames sent to Unassigned.` : ".")
      );
    } catch (err) {
      setGenerateMsg("Error: " + err.message);
    } finally {
      setGenerating(false);
    }
  }

  function openDrawModal(trajKey, beforeTid, afterTid) {
    let beforeEnd, afterStart;
    if (beforeTid !== null) {
      const beforePts = tracks?.get(beforeTid) ?? [];
      beforeEnd = beforePts.length ? lastReal(beforePts) : undefined;
      if (!beforeEnd) return;
    }
    if (afterTid !== null) {
      const afterPts = tracks?.get(afterTid) ?? [];
      afterStart = afterPts.length ? firstReal(afterPts) : undefined;
      if (!afterStart) return;
    }
    if (!effectiveFrameCount) return;
    if (beforeTid === null && afterTid === null) {
      // Empty trajectory: the whole video is the gap and there are no anchor positions.
      beforeEnd = { frame: -1, x: null, y: null };
      afterStart = { frame: effectiveFrameCount, x: null, y: null };
    } else if (beforeTid === null) {
      beforeEnd = { frame: -1, x: afterStart.x, y: afterStart.y };
    } else if (afterTid === null) {
      afterStart = { frame: effectiveFrameCount, x: beforeEnd.x, y: beforeEnd.y };
    }
    setDrawModal({ trajKey, beforeTid, afterTid, beforeEnd, afterStart });
  }

  function splitTrack(tid, splitFrame) {
    if (locked.has(zoneOf(tid))) return;
    const pts = tracks?.get(tid) ?? [];
    const partA = pts.filter((p) => p.frame < splitFrame);
    const partB = pts.filter((p) => p.frame >= splitFrame);
    if (partA.length === 0 || partB.length === 0) return;

    let resolvedNewTid;
    setTracks((prev) => {
      const prevMax = prev.size > 0 ? Math.max(...prev.keys()) : 0;
      resolvedNewTid = prevMax + 1;
      const next = new Map(prev);
      next.set(tid, partA);
      next.set(resolvedNewTid, partB);
      return next;
    });
    setAssignments((prev) => {
      if (resolvedNewTid == null) return prev;
      const next = { ...prev };
      for (const key of Object.keys(next)) {
        const idx = next[key].indexOf(tid);
        if (idx >= 0) {
          const newTids = [...next[key]];
          newTids.splice(idx + 1, 0, resolvedNewTid);
          next[key] = newTids;
          break;
        }
      }
      return next;
    });
    if (pending.includes(tid)) setPending((prev) => (resolvedNewTid == null ? prev : [...prev, resolvedNewTid]));
    else if (unassigned.includes(tid)) setUnassigned((prev) => (resolvedNewTid == null ? prev : [...prev, resolvedNewTid]));
    if (trackIter[tid] != null) setTrackIter((prev) => ({ ...prev, [resolvedNewTid]: prev[tid] }));
    // Keep the split track selected; the follow-the-subject rule would otherwise hop straight to
    // the new second half (the viewer sits on its first frame), so skip it once.
    skipFollowRef.current = true;
    setConfirmed(false);
  }

  function handleGenerateTrack(newPoints, trajKey, beforeTid, afterTid) {
    let resolvedNewTid;
    setTracks((prev) => {
      const prevMax = prev.size > 0 ? Math.max(...prev.keys()) : 0;
      resolvedNewTid = prevMax + 1;
      const next = new Map(prev);
      next.set(resolvedNewTid, newPoints);
      return next;
    });
    setAssignments((prev) => {
      if (resolvedNewTid == null) return prev;
      const next = { ...prev };
      const tids = [...(next[trajKey] ?? [])];
      const idx = afterTid !== null ? tids.indexOf(afterTid) : -1;
      if (idx >= 0) tids.splice(idx, 0, resolvedNewTid);
      else tids.push(resolvedNewTid);
      next[trajKey] = tids;
      return next;
    });
    setConfirmed(false);
    setDrawModal(null);
  }

  function renderChip(tid, source) {
    const pts = tracks?.get(tid) ?? [];
    const first = pts.length > 0 ? pts[0].frame + 1 : "?";
    const last  = pts.length > 0 ? pts[pts.length - 1].frame + 1 : "?";
    const st = styleMap.get(tid) ?? UNASSIGNED_STYLE;
    const isSel = tid === selectedTid;
    const isNew = source === "new";
    return (
      <div
        key={tid}
        data-uchip=""
        draggable={!locked.has(source)}
        onDragStart={(e) => handleDragStart(e, tid, source)}
        onDragEnd={endDrag}
        onClick={() => {
          if (tid === selectedTid) { setSelectedTid(null); return; }
          setSelectedTid(tid);
          // Selecting a track jumps the viewer to its last frame
          if (pts.length > 0) setFrameIndex(isNew ? pts[0].frame : pts[pts.length - 1].frame);
        }}
        style={{
          display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2, boxSizing: "border-box",
          padding: "4px 8px", borderRadius: 4, cursor: locked.has(source) ? "pointer" : "grab",
          userSelect: "none", fontSize: "9pt", marginBottom: 3,
          background: isSel ? (isNew ? "rgba(242,212,53,0.12)" : "rgba(53,129,242,0.12)") : "rgba(255,255,255,0.04)",
          border: `1px solid ${isSel ? (isNew ? "#F2D435" : "var(--accent)") : "var(--border)"}`,
          outline: isSel && isNew ? "1px solid #F2D435" : undefined,
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <ShapeIcon shape={st.shape} color={st.color} />
          <span style={{ fontWeight: 500 }}>Track #{tid}</span>
          {isNew && trackIter[tid] != null && (
            <span style={{ color: "var(--muted)", fontSize: "7.5pt" }}>it. {trackIter[tid]}</span>
          )}
        </span>
        <span style={{ color: "var(--muted)", fontSize: "8pt", whiteSpace: "nowrap" }}>
          {first}–{last} · {pts.length}f
        </span>
      </div>
    );
  }

  function renderDropZone(dest, label, tids) {
    const isOver = dragOverZone === dest;
    const isTrajectory = dest !== "unassigned";
    const isLocked = locked.has(dest);
    const gapsEnabled = isTrajectory && !isLocked; // no "draw missing track" prompts on a locked trajectory

    const content = [];

    // Empty trajectory: the entire video is missing
    if (gapsEnabled && tids.length === 0 && effectiveFrameCount != null && effectiveFrameCount >= minMissingFrames) {
      content.push(
        <button
          key="gap-all"
          data-uchip=""
          onClick={() => openDrawModal(dest, null, null)}
          style={{
            display: "block", boxSizing: "border-box", textAlign: "left", whiteSpace: "nowrap",
            background: "rgba(242,212,53,0.08)", border: "1px solid #F2D435",
            color: "#000", borderRadius: 4, padding: "3px 8px",
            marginBottom: 3, fontSize: "8.5pt", cursor: "pointer",
          }}
        >
          ⚠ Missing<br />{effectiveFrameCount} frames
        </button>
      );
    }

    if (gapsEnabled && tids.length > 0 && effectiveFrameCount != null) {
      const firstPts = tracks?.get(tids[0]) ?? [];
      const firstFrame = firstPts.length ? firstReal(firstPts).frame : 0;
      if (firstFrame >= minMissingFrames) {
        content.push(
          <button
            key="gap-start"
            data-uchip=""
            onClick={() => openDrawModal(dest, null, tids[0])}
            style={{
              display: "block", boxSizing: "border-box", textAlign: "left", whiteSpace: "nowrap",
              background: "rgba(242,212,53,0.08)", border: "1px solid #F2D435",
              color: "#000", borderRadius: 4, padding: "3px 8px",
              marginBottom: 3, fontSize: "8.5pt", cursor: "pointer",
            }}
          >
            ⚠ Missing<br />{firstFrame} frames
          </button>
        );
      }
    }

    for (let i = 0; i < tids.length; i++) {
      content.push(renderChip(tids[i], dest));
      if (gapsEnabled && i < tids.length - 1) {
        const aPts = tracks?.get(tids[i]) ?? [];
        const bPts = tracks?.get(tids[i + 1]) ?? [];
        const aLast = aPts.length ? lastReal(aPts).frame : 0;
        const bFirst = bPts.length ? firstReal(bPts).frame : Infinity;
        const gap = bFirst - aLast - 1;
        if (gap >= minMissingFrames) {
          const capI = i;
          content.push(
            <button
              key={`gap-${tids[i]}-${tids[i + 1]}`}
              data-uchip=""
              onClick={() => openDrawModal(dest, tids[capI], tids[capI + 1])}
              style={{
                display: "block", boxSizing: "border-box", textAlign: "left", whiteSpace: "nowrap",
                background: "rgba(242,212,53,0.08)",
                border: "1px solid #F2D435",
                color: "#000",
                borderRadius: 4,
                padding: "3px 8px",
                marginBottom: 3,
                fontSize: "8.5pt",
                cursor: "pointer",
              }}
            >
              ⚠ Missing<br />{gap} frames
            </button>
          );
        }
      }
    }

    if (gapsEnabled && tids.length > 0 && effectiveFrameCount != null) {
      const lastPts = tracks?.get(tids[tids.length - 1]) ?? [];
      const lastFrame = lastPts.length ? lastReal(lastPts).frame : 0;
      const framesFromEnd = (effectiveFrameCount - 1) - lastFrame;
      if (framesFromEnd >= minMissingFrames) {
        content.push(
          <button
            key="gap-end"
            data-uchip=""
            onClick={() => openDrawModal(dest, tids[tids.length - 1], null)}
            style={{
              display: "block", boxSizing: "border-box", textAlign: "left", whiteSpace: "nowrap",
              background: "rgba(242,212,53,0.08)", border: "1px solid #F2D435",
              color: "#000", borderRadius: 4, padding: "3px 8px",
              marginBottom: 3, fontSize: "8.5pt", cursor: "pointer",
            }}
          >
            ⚠ Missing<br />{framesFromEnd} frames
          </button>
        );
      }
    }

    return (
      <div
        key={dest}
        onDragOver={(e) => { e.preventDefault(); setDragOverZone(dest); }}
        onDrop={(e) => handleDrop(e, dest)}
        style={{
          border: `1px solid ${isLocked ? "var(--success, #35b858)" : isOver ? "var(--accent)" : "var(--border)"}`,
          borderRadius: 6, padding: "8px 10px", marginBottom: 10,
          background: isLocked ? "rgba(53,184,88,0.16)" : isOver ? "rgba(53,129,242,0.06)" : "rgba(255,255,255,0.02)",
          minHeight: 52, transition: "border-color 0.1s, background 0.1s",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", marginBottom: 5 }}>
          <p className="section-label" style={{ fontSize: "9pt", margin: 0, flex: 1 }}>{label}</p>
          {isTrajectory && (
            <label
              title="Mark this trajectory as correctly finished"
              style={{
                display: "flex", flexDirection: "row", alignItems: "center", gap: 4,
                margin: 0, fontSize: "8.5pt", cursor: "pointer", userSelect: "none",
              }}
            >
              <input
                type="checkbox"
                checked={isLocked}
                onChange={() => toggleLock(dest)}
                style={{ width: 14, height: 14, minHeight: 0, padding: 0, margin: 0, cursor: "pointer" }}
              />
              Lock
            </label>
          )}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", columnGap: 4 }}>
          {content}
        </div>
        {tids.length === 0 && !isLocked && (
          <p className="hint" style={{ fontSize: "8pt", margin: 0, fontStyle: "italic" }}>Drop tracks here</p>
        )}
      </div>
    );
  }


  return (
    <>
      <div ref={panelRef} style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>

        {/* Left: video + controls */}
        <div style={{ flex: "0 0 50%", minWidth: 0 }}>
          {loading && <p className="hint">Loading trajectories…</p>}
          {!loading && (
            <>
              <canvas
                ref={canvasRef}
                style={{ display: "block", width: "100%", maxWidth: 1080, height: "auto", margin: "0 auto", borderRadius: 4, cursor: "crosshair" }}
                onClick={handleCanvasClick}
                onDragOver={handleCanvasDragOver}
                onDragLeave={() => setDragHover(null)}
                onDrop={handleCanvasDrop}
              />
              {meta && frameIndex != null && (
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                  <button onClick={() => jumpTo(0)}>Start</button>
                  <button onClick={() => jump(-100)}>−100</button>
                  <button onClick={() => jump(-10)}>−10</button>
                  <button onClick={() => jump(-1)}>−1</button>
                  <span className="hint" style={{ margin: "0 4px", minWidth: 110, textAlign: "center" }}>
                    Frame {frameIndex + 1} / {effectiveFrameCount ?? "…"}
                  </span>
                  <button onClick={() => jump(1)}>+1</button>
                  <button onClick={() => jump(10)}>+10</button>
                  <button onClick={() => jump(100)}>+100</button>
                  <button onClick={() => jumpTo((effectiveFrameCount ?? 1) - 1)}>End</button>
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 8, alignItems: "flex-start" }}>
                <button onClick={() => setShowLines((v) => !v)}>
                  {showLines ? "Hide Track Lines" : "Show Track Lines"}
                </button>
                <button onClick={() => setShowDots((v) => !v)}>
                  {showDots ? "Hide Dots" : "Show Dots"}
                </button>
              </div>
            </>
          )}
        </div>

        {/* Right: trajectory boxes  */}
        {!loading && assignments && (
          <div style={{
            flex: 1, minWidth: 0, maxHeight: "calc(100vh - 160px)",
            display: "flex", flexDirection: "column",
          }}>

            {/* Action row: pinned above the scroller so it is always visible */}
            {confirmError && <p className="error" style={{ marginBottom: 6, fontSize: "9pt" }}>{confirmError}</p>}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexShrink: 0 }}>
              {saveMsg && <span className="hint" style={{ fontSize: "9pt" }}>{saveMsg}</span>}
              <div style={{ flex: 1 }} />
              <button disabled={saving} onClick={saveProgress}>
                {saving ? "Saving…" : "Save Progress"}
              </button>
              <button
                className="primary"
                disabled={confirming || confirmed}
                onClick={confirmTrajectories}
              >
                {confirmed ? "Trajectories Confirmed" : confirming ? "Confirming…" : "Confirm Trajectories"}
              </button>
            </div>

            {/* Selected-track bar pinned above the scroller*/}
            {selectedTid !== null && (() => {
              const pts = tracks?.get(selectedTid) ?? [];
              const canSplit = frameIndex != null
                && pts.some((p) => p.frame < frameIndex)
                && pts.some((p) => p.frame >= frameIndex);
              const isUnassigned = unassigned.includes(selectedTid);
              const inLocked = locked.has(zoneOf(selectedTid));
              return (
                <div style={{
                  display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
                  padding: "6px 10px", marginBottom: 10,
                  border: "1px solid var(--accent, #3581F2)",
                  borderRadius: 6, fontSize: "9pt",
                  background: "rgba(53,129,242,0.06)",
                }}>
                  <span style={{ color: "var(--muted)" }}>Track #{selectedTid}</span>
                  <div style={{ flex: 1 }} />
                  {inLocked ? (
                    <span className="hint" style={{ fontSize: "8.5pt", margin: 0 }}>
                      Trajectory {zoneOf(selectedTid)} is locked — unlock it to edit this track
                    </span>
                  ) : canSplit ? (
                    <button onClick={() => splitTrack(selectedTid, frameIndex)}>
                      Split at Frame {(frameIndex ?? 0) + 1}
                    </button>
                  ) : (
                    <span className="hint" style={{ fontSize: "8.5pt", margin: 0 }}>
                      Navigate to a frame within this track to split
                    </span>
                  )}
                  <button disabled={isUnassigned || inLocked} onClick={() => moveToUnassigned(selectedTid)}>
                    Move to Unassigned
                  </button>
                </div>
              );
            })()}

          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "row-reverse", gap: 12 }}>
          <div style={{ flex: "0 0 calc(75% - 6px)", minWidth: 0, overflowY: "auto" }}>

            {/* Trajectory drop zones */}
            {Array.from({ length: maxCount }, (_, i) => i + 1).map((t) => {
              const tids = (assignments[String(t)] ?? []).slice().sort((a, b) => {
                const sA = tracks?.get(a)?.[0]?.frame ?? 0;
                const sB = tracks?.get(b)?.[0]?.frame ?? 0;
                return sA - sB;
              });
              return renderDropZone(String(t), `Trajectory ${t}`, tids);
            })}

            {/* Unassigned pool */}
            {renderDropZone("unassigned", "Unassigned", unassigned)}

          </div>

          <div style={{ flex: "0 0 calc(25% - 6px)", minWidth: 0, overflowY: "auto" }}>
            {(() => {
              const n = endingMissing.length;
              const reason = !detectionsFvId ? "Detections for this tracking are not available."
                : pending.length > 0 ? ""
                : n === 0 ? "No trajectory ends with missing frames."
                : `Will generate ${n} new track${n > 1 ? "s" : ""}.`;
              const canGenerate = !!detectionsFvId && pending.length === 0 && n > 0 && !generating;
              return (
                <div style={{
                  border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px", marginBottom: 10,
                  background: "rgba(255,255,255,0.02)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, fontSize: "9pt" }}>
                    <span>Min. Frames:</span>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={minFrames}
                      onChange={(e) => setMinFrames(e.target.value)}
                      style={{ width: 70, minWidth: 0, padding: "2px 6px" }}
                    />
                  </div>
                  <button
                    className="primary"
                    disabled={!canGenerate}
                    onClick={generateNextTracks}
                    style={{ width: "100%" }}
                  >
                    {generating ? "Generating…" : "Generate Next Tracks"}
                  </button>
                  {reason && <p className="hint" style={{ fontSize: "8pt", margin: "4px 0 0" }}>{reason}</p>}
                  {generateMsg && <p className="hint" style={{ fontSize: "8pt", margin: "4px 0 0" }}>{generateMsg}</p>}
                </div>
              );
            })()}

            {pending.length > 0 && (
              <div style={{
                border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px",
                background: "rgba(255,255,255,0.02)",
              }}>
                <div style={{ display: "flex", alignItems: "center", marginBottom: 5 }}>
                  <p className="section-label" style={{ fontSize: "9pt", margin: 0, flex: 1 }}>
                    New tracks ({pending.length})
                  </p>
                  <button onClick={discardAllPending} style={{ fontSize: "8pt", padding: "1px 6px" }}>
                    Discard all
                  </button>
                </div>
                <p className="hint" style={{ fontSize: "8pt", margin: "0 0 6px" }}>
                  Click a track to see where it starts, then drag it into its trajectory, or into Unassigned to discard it.
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", columnGap: 4 }}>
                  {pending
                    .slice()
                    .sort((a, b) => (tracks?.get(a)?.[0]?.frame ?? 0) - (tracks?.get(b)?.[0]?.frame ?? 0))
                    .map((tid) => renderChip(tid, "new"))}
                </div>
              </div>
            )}
          </div>
          </div>
          </div>
        )}
      </div>

      {drawModal && createPortal(
        <DrawTrackModal
          modal={drawModal}
          tracks={tracks}
          unassigned={unassigned}
          headers={headers}
          styleMap={styleMap}
          videoVersionId={videoVersionId}
          frameStep={frameStep}
          effectiveFrameCount={effectiveFrameCount}
          onGenerate={handleGenerateTrack}
          onClose={() => setDrawModal(null)}
        />,
        document.body
      )}
    </>
  );
}
