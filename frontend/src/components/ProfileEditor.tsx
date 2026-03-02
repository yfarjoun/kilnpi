import { useCallback, useRef, useState } from 'react';
import type { Segment } from '../types';
import { SegmentTable } from './SegmentTable';

interface ProfileEditorProps {
  segments: Segment[];
  onChange: (segments: Segment[]) => void;
}

interface ProfilePoint {
  time: number;
  temp: number;
  segIndex: number; // -1 for the initial room-temp point
  isRampEnd: boolean; // true = ramp endpoint, false = soak endpoint
}

function buildProfilePoints(segments: Segment[]): ProfilePoint[] {
  const points: ProfilePoint[] = [{ time: 0, temp: 25, segIndex: -1, isRampEnd: false }];
  let time = 0;
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    time += seg.ramp_min;
    points.push({ time, temp: seg.target_temp, segIndex: i, isRampEnd: true });
    time += seg.soak_min;
    points.push({ time, temp: seg.target_temp, segIndex: i, isRampEnd: false });
  }
  return points;
}

const MARGIN = { top: 16, right: 16, bottom: 32, left: 48 };
const CHART_HEIGHT = 220;
const DOT_RADIUS = 6;
const MAX_TEMP_DISPLAY = 1350; // fixed Y scale ceiling for kiln temps

export function ProfileEditor({ segments, onChange }: ProfileEditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [svgWidth, setSvgWidth] = useState(600);
  const containerRef = useRef<HTMLDivElement>(null);
  // Store the drag start pixel offset to prevent jumps
  const dragStartRef = useRef<{ offsetY: number; offsetX: number; startTemp: number; startTime: number } | null>(null);

  const measuredRef = useCallback((node: HTMLDivElement | null) => {
    if (node) {
      containerRef.current = node;
      const observer = new ResizeObserver((entries) => {
        for (const entry of entries) {
          setSvgWidth(entry.contentRect.width);
        }
      });
      observer.observe(node);
      setSvgWidth(node.clientWidth);
    }
  }, []);

  const points = buildProfilePoints(segments);

  const maxTime = Math.max(1, ...points.map((p) => p.time));
  const displayMaxTemp = Math.min(MAX_TEMP_DISPLAY, Math.max(200, ...points.map((p) => p.temp)) * 1.15);
  const displayMaxTime = maxTime * 1.1;

  const activeMaxTemp = displayMaxTemp;
  const activeMaxTime = displayMaxTime;

  const plotW = svgWidth - MARGIN.left - MARGIN.right;
  const plotH = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;

  const toX = (time: number) => MARGIN.left + (time / activeMaxTime) * plotW;
  const toY = (temp: number) => MARGIN.top + plotH - (temp / activeMaxTemp) * plotH;
  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(p.time)} ${toY(p.temp)}`)
    .join(' ');

  // All points except the origin are draggable
  const draggablePoints = points
    .map((p, i) => ({ ...p, pointIndex: i }))
    .filter((p) => p.segIndex >= 0);

  const handleMouseDown = (pointIndex: number) => (e: React.MouseEvent) => {
    e.preventDefault();
    const point = points[pointIndex];
    dragStartRef.current = {
      offsetY: e.clientY,
      offsetX: e.clientX,
      startTemp: point.temp,
      startTime: point.time,
    };
    setDragging(pointIndex);
  };

  // Pixels per degree C and per minute — based on current scale
  const pxPerDeg = plotH / activeMaxTemp;
  const pxPerMin = plotW / activeMaxTime;

  const handleMouseMove = (e: React.MouseEvent) => {
    if (dragging === null || !dragStartRef.current) return;
    const { offsetY, offsetX, startTemp, startTime } = dragStartRef.current;

    // Delta in pixels
    const dy = offsetY - e.clientY; // up = positive = hotter
    const dx = e.clientX - offsetX; // right = positive = later

    // Convert to value deltas using current scale
    const deltaDeg = Math.round((dy / pxPerDeg) / 5) * 5;
    const deltaMin = Math.round(dx / pxPerMin);

    const newTemp = Math.max(0, Math.min(1300, startTemp + deltaDeg));
    const newTime = Math.max(0, startTime + deltaMin);

    const point = points[dragging];
    if (point.segIndex < 0) return;

    const updated = [...segments];
    const seg = { ...updated[point.segIndex] };

    const prevPointTime = dragging > 0 ? points[dragging - 1].time : 0;

    if (point.isRampEnd) {
      seg.target_temp = newTemp;
      seg.ramp_min = Math.max(1, newTime - prevPointTime);
    } else {
      seg.target_temp = newTemp;
      seg.soak_min = Math.max(0, newTime - prevPointTime);
    }

    updated[point.segIndex] = seg;
    onChange(updated);
  };

  const handleMouseUp = () => {
    setDragging(null);
    dragStartRef.current = null;
  };

  const yTicks = 5;
  const xTicks = 5;

  return (
    <div className="space-y-4">
      <div className="bg-gray-800 rounded-lg p-4" ref={measuredRef}>
        <svg
          ref={svgRef}
          width={svgWidth}
          height={CHART_HEIGHT}
          className="select-none"
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {/* Grid */}
          {Array.from({ length: yTicks + 1 }, (_, i) => {
            const y = MARGIN.top + (i / yTicks) * plotH;
            const temp = Math.round(activeMaxTemp * (1 - i / yTicks));
            return (
              <g key={`yg-${i}`}>
                <line x1={MARGIN.left} y1={y} x2={MARGIN.left + plotW} y2={y} stroke="#374151" strokeDasharray="3 3" />
                <text x={MARGIN.left - 8} y={y + 4} fill="#9CA3AF" fontSize={10} textAnchor="end">{temp}</text>
              </g>
            );
          })}
          {Array.from({ length: xTicks + 1 }, (_, i) => {
            const x = MARGIN.left + (i / xTicks) * plotW;
            const time = Math.round(activeMaxTime * (i / xTicks));
            return (
              <g key={`xg-${i}`}>
                <line x1={x} y1={MARGIN.top} x2={x} y2={MARGIN.top + plotH} stroke="#374151" strokeDasharray="3 3" />
                <text x={x} y={CHART_HEIGHT - 8} fill="#9CA3AF" fontSize={10} textAnchor="middle">{time}m</text>
              </g>
            );
          })}

          {/* Axis labels */}
          <text x={svgWidth / 2} y={CHART_HEIGHT} fill="#9CA3AF" fontSize={11} textAnchor="middle">Minutes</text>
          <text x={12} y={CHART_HEIGHT / 2} fill="#9CA3AF" fontSize={11} textAnchor="middle" transform={`rotate(-90, 12, ${CHART_HEIGHT / 2})`}>°C</text>

          {/* Profile line */}
          <path d={pathD} fill="none" stroke="#F59E0B" strokeWidth={2} />

          {/* All points as small dots */}
          {points.map((p, i) => (
            <circle key={`pt-${i}`} cx={toX(p.time)} cy={toY(p.temp)} r={3} fill="#F59E0B" />
          ))}

          {/* Draggable dots */}
          {draggablePoints.map(({ pointIndex, time, temp, segIndex, isRampEnd }) => (
            <g key={`drag-${pointIndex}`}>
              <circle
                cx={toX(time)}
                cy={toY(temp)}
                r={DOT_RADIUS}
                fill={dragging === pointIndex ? '#FBBF24' : isRampEnd ? '#F59E0B' : '#6B7280'}
                stroke="#fff"
                strokeWidth={2}
                className="cursor-grab active:cursor-grabbing"
                onMouseDown={handleMouseDown(pointIndex)}
              />
              {isRampEnd && (
                <text
                  x={toX(time)}
                  y={toY(temp) - 12}
                  fill="#FBBF24"
                  fontSize={11}
                  fontWeight="bold"
                  textAnchor="middle"
                >
                  {Math.round(temp)}°
                </text>
              )}
              <text
                x={toX(time)}
                y={toY(temp) + 18}
                fill="#9CA3AF"
                fontSize={9}
                textAnchor="middle"
              >
                {isRampEnd ? `S${segIndex + 1}` : 'soak'}
              </text>
            </g>
          ))}
        </svg>
        <div className="text-xs text-gray-500 mt-1">
          Drag points to adjust: up/down for temperature, left/right for timing
        </div>
      </div>
      <SegmentTable segments={segments} onChange={onChange} />
    </div>
  );
}
