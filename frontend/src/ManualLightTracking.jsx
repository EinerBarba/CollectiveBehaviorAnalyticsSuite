import { useEffect, useRef, useState } from "react";
import * as api from "./api.js";

const CANVAS_WIDTH = 720; // Display width
const DOT_RADIUS = 5;

// atan2(dy, dx) in image coordinates (0=right, 90=down)
function predictedPoint(circle, first, rotation, direction, frame) {
  if (!circle || !first || !rotation) return null;
  const phase = Math.atan2(first.y - circle.cy, first.x - circle.cx);
  const framesPerRotation = (rotation.endFrame - first.frame) / rotation.count;
  if (!(framesPerRotation > 0)) return null;
  const angularVelocity = (direction * 2 * Math.PI) / framesPerRotation;
  const angle = phase + angularVelocity * (frame - first.frame);
  return { x: circle.cx + circle.r * Math.cos(angle), y: circle.cy + circle.r * Math.sin(angle), framesPerRotation };
}

// Calibrate the arena circle, click the light's first position, 
// advance frames until it completes one or more rotations, then submit.
export default function ManualLightTracking({ experimentId, videoVersionId, experimentFps, onComplete, run, busy }) {
  const [stage, setStage] = useState("circle"); // Circle -> First point -> Rotation -> Confirm
  const [meta, setMeta] = useState(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [image, setImage] = useState(null);
  const [error, setError] = useState("");

  const [circle, setCircle] = useState(null); // { cx, cy, r } in pixels
  const [firstPoint, setFirstPoint] = useState(null); // { frame, x, y } format
  const [rotation, setRotation] = useState(null); // { endFrame, count }
  const [rotationCount, setRotationCount] = useState(1);
  const [direction, setDirection] = useState(1);

  const canvasRef = useRef(null);
  const dragRef = useRef(null);

  const frameStep = (experimentFps && meta?.fps && experimentFps < meta.fps)
    ? Math.max(1, Math.round(meta.fps / experimentFps))
    : 1;
  const effectiveFrameCount = meta ? Math.ceil(meta.frame_count / frameStep) : null;

  useEffect(() => {
    api.getVideoMetadata(videoVersionId).then(setMeta).catch((e) => setError(e.message));
  }, [videoVersionId]);

  // Load the current frame as an <img>
  useEffect(() => {
    let cancelled = false;
    let url = null;
    setError("");
    api
      .getVideoFrame(videoVersionId, frameIndex * frameStep)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => !cancelled && setImage(img);
        img.src = url;
      })
      .catch((e) => setError(e.message));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [videoVersionId, frameIndex, frameStep]);

  useEffect(() => draw(), [image, stage, circle, firstPoint, rotation, direction, frameIndex]);

  function scale() {
    return image ? CANVAS_WIDTH / image.naturalWidth : 1;
  }

  function toSource(canvasX, canvasY) {
    const s = scale();
    return { x: canvasX / s, y: canvasY / s };
  }

  // In canvas pixel coordinates 
  function canvasPos(event) {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) * canvas.width) / rect.width,
      y: ((event.clientY - rect.top) * canvas.height) / rect.height,
    };
  }

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas || !image) return;
    const s = scale();
    canvas.width = CANVAS_WIDTH;
    canvas.height = image.naturalHeight * s;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    const dot = (x, y, color, hollow = false) => {
      ctx.beginPath();
      ctx.arc(x * s, y * s, DOT_RADIUS, 0, 2 * Math.PI);
      if (hollow) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
      } else {
        ctx.fillStyle = color;
        ctx.fill();
      }
    };

    if (stage === "circle" && circle) {
      ctx.beginPath();
      ctx.arc(circle.cx * s, circle.cy * s, circle.r * s, 0, 2 * Math.PI);
      ctx.strokeStyle = "#35f254";
      ctx.lineWidth = 3;
      ctx.stroke();
      dot(circle.cx, circle.cy, "#35f254");
    }

    if (stage === "first_point" && firstPoint) dot(firstPoint.x, firstPoint.y, "#3581f2");

    if (stage === "rotation" && firstPoint) dot(firstPoint.x, firstPoint.y, "#3581f2");

    if (stage === "confirm") {
      const predicted = predictedPoint(circle, firstPoint, rotation, direction, frameIndex);
      if (predicted) dot(predicted.x, predicted.y, "#f235eb", true);
    }
  }

  function handlePointerDown(event) {
    const canvasP = canvasPos(event);
    const source = toSource(canvasP.x, canvasP.y);

    if (stage === "circle") {
      if (!circle) {
        setCircle({ cx: source.x, cy: source.y, r: (image?.naturalWidth ?? 200) * 0.15 });
        return;
      }
      const distance = Math.hypot(source.x - circle.cx, source.y - circle.cy);
      dragRef.current = distance <= circle.r * 0.5 ? "move" : "resize";
      return;
    }

    if (stage === "first_point") {
      setFirstPoint({ frame: frameIndex, x: source.x, y: source.y });
    }
  }

  function handlePointerMove(event) {
    if (stage !== "circle" || !dragRef.current || !circle) return;
    const canvasP = canvasPos(event);
    const source = toSource(canvasP.x, canvasP.y);
    if (dragRef.current === "move") {
      setCircle({ ...circle, cx: source.x, cy: source.y });
    } else {
      setCircle({ ...circle, r: Math.max(5, Math.hypot(source.x - circle.cx, source.y - circle.cy)) });
    }
  }

  function handleWheel(event) {
    if (stage !== "circle" || !circle) return;
    event.preventDefault();
    setCircle({ ...circle, r: Math.max(5, circle.r + (event.deltaY < 0 ? 5 : -5)) });
  }

  function jump(delta) {
    if (!effectiveFrameCount) return;
    setFrameIndex((f) => Math.max(0, Math.min(effectiveFrameCount - 1, f + delta)));
  }

  // Saves current frame
  function goToStage(target) {
    if (target === "first_point" && firstPoint) setFrameIndex(firstPoint.frame);
    if (target === "rotation") setFrameIndex(rotation ? rotation.endFrame : (firstPoint?.frame ?? frameIndex));
    setStage(target);
  }

  async function submit() {
    setError("");
    try {
      const framesPerRotation = (rotation.endFrame - firstPoint.frame) / rotationCount;
      const started = await api.startRun("manual-tracking", {
        experiment_id: experimentId,
        file_version_id: videoVersionId,
        center_x: circle.cx,
        center_y: circle.cy,
        radius_px: circle.r,
        first_frame: firstPoint.frame,
        first_x: firstPoint.x,
        first_y: firstPoint.y,
        frames_per_rotation: framesPerRotation,
        direction,
      });
      const finished = await api.waitForRun(started.id);
      const fileVersionId = await api.runOutputFileVersionId(finished.id);
      onComplete(fileVersionId, finished.id);
    } catch (e) {
      setError(e.message);
    }
  }

  async function submitNoStimulus() {
    setError("");
    try {
      const started = await api.startRun("manual-tracking", {
        experiment_id: experimentId,
        file_version_id: videoVersionId,
        center_x: circle.cx,
        center_y: circle.cy,
        radius_px: circle.r,
        // No light fields: this marks the video as having no stimulus.
      });
      const finished = await api.waitForRun(started.id);
      const fileVersionId = await api.runOutputFileVersionId(finished.id);
      onComplete(fileVersionId, finished.id);
    } catch (e) {
      setError(e.message);
    }
  }

  if (error && !meta) return <p className="error">{error}</p>;
  if (!meta || !image) return <p className="hint">Loading video...</p>;

  const predicted = stage === "confirm" ? predictedPoint(circle, firstPoint, rotation, direction, frameIndex) : null;

  return (
    <div className="wizard">
      <canvas
        ref={canvasRef}
        className="wizard-canvas"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={() => (dragRef.current = null)}
        onPointerLeave={() => (dragRef.current = null)}
        onWheel={handleWheel}
      />

      <div className="row">
        <button onClick={() => jump(-10)}>-10</button>
        <button onClick={() => jump(-1)}>-1</button>
        <input
          type="range"
          min={0}
          max={(effectiveFrameCount ?? 1) - 1}
          value={frameIndex}
          onChange={(e) => setFrameIndex(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <button onClick={() => jump(1)}>+1</button>
        <button onClick={() => jump(10)}>+10</button>
        <span className="small">
          Frame {frameIndex + 1} / {effectiveFrameCount ?? "…"}
        </span>
      </div>

      {stage === "circle" && (
        <>
          <p className="hint">Click the arena's center, drag near it to move, drag the edge (or scroll) to resize.</p>
          <div className="row">
            <button className="primary" disabled={!circle} onClick={() => goToStage("first_point")}>
              Confirm circle
            </button>
          </div>
        </>
      )}

      {stage === "first_point" && (
        <>
          <p className="hint">Scrub to the first frame where the light is visible, then click it.</p>
          <div className="row">
            <button onClick={() => setStage("circle")}>Back</button>
            <button className="primary" disabled={!firstPoint} onClick={() => goToStage("rotation")}>
              Confirm point
            </button>
            <button
              style={{ marginLeft: "auto", color: "#888" }}
              disabled={busy}
              onClick={() => run(submitNoStimulus)}
            >
              No stimulus present
            </button>
          </div>
        </>
      )}

      {stage === "rotation" && (
        <>
          <p className="hint">
            Advance until the light lines up with the blue marker again (one or more full rotations), then enter how
            many rotations that was.
          </p>
          <div className="row">
            <label>
              Rotations advanced
              <input
                type="number"
                min="1"
                value={rotationCount}
                onChange={(e) => setRotationCount(Math.max(1, Number(e.target.value)))}
              />
            </label>
            <button onClick={() => goToStage("first_point")}>Back</button>
            <button
              className="primary"
              disabled={frameIndex <= firstPoint.frame}
              onClick={() => {
                setRotation({ endFrame: frameIndex, count: rotationCount });
                setStage("confirm");
              }}
            >
              Confirm rotation
            </button>
          </div>
          {frameIndex <= firstPoint.frame && <p className="error">Advance past the first frame before confirming.</p>}
        </>
      )}

      {stage === "confirm" && (
        <>
          <p className="hint">
            The magenta ring is the predicted position. Check it at the halfway point and the end: if it lags behind
            or runs ahead of the real light, hit Back to re-measure using a later, more precise end frame (more
            rotations averaged reduces error). If it moves opposite the real light, flip the direction. Frames per
            rotation: {predicted?.framesPerRotation.toFixed(3) ?? "n/a"}
          </p>
          <div className="row">
            <span className="small">Jump to:</span>
            <button onClick={() => setFrameIndex(firstPoint.frame)}>First point</button>
            <button onClick={() => setFrameIndex(rotation.endFrame)}>Measured rotation</button>
            <button onClick={() => setFrameIndex(Math.floor((effectiveFrameCount ?? 1) / 2))}>Halfway</button>
            <button onClick={() => setFrameIndex((effectiveFrameCount ?? 1) - 1)}>End</button>
          </div>
          <div className="row">
            <label>
              Direction
              <select value={direction} onChange={(e) => setDirection(Number(e.target.value))}>
                <option value={1}>Clockwise</option>
                <option value={-1}>Counter-clockwise</option>
              </select>
            </label>
            <button onClick={() => goToStage("rotation")}>Back (re-measure)</button>
            <button className="primary" disabled={busy} onClick={() => run(submit)}>
              Submit light tracking
            </button>
          </div>
        </>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  );
}
