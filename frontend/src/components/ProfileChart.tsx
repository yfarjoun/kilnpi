import { useCallback, useRef, useState } from 'react';
import type { Segment } from '../types';

const MARGIN = { top: 16, right: 16, bottom: 32, left: 48 };
const CHART_HEIGHT = 180;
const MAX_TEMP_DISPLAY = 1350;

interface ProfileChartProps {
  segments: Segment[];
}

interface ProfilePoint {
  time: number;
  temp: number;
  segIndex: number;
  isRampEnd: boolean;
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

export function ProfileChart({ segments }: ProfileChartProps) {
  const [svgWidth, setSvgWidth] = useState(600);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const plotW = svgWidth - MARGIN.left - MARGIN.right;
  const plotH = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;

  const toX = (time: number) => MARGIN.left + (time / displayMaxTime) * plotW;
  const toY = (temp: number) => MARGIN.top + plotH - (temp / displayMaxTemp) * plotH;
  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(p.time)} ${toY(p.temp)}`)
    .join(' ');

  const yTicks = 5;
  const timeTicks: { time: number; major: boolean; label: string }[] = [];
  for (let t = 0; t <= displayMaxTime; t += 30) {
    const hours = Math.floor(t / 60);
    const mins = t % 60;
    const major = t % 60 === 0;
    let label: string;
    if (t === 0) label = '0';
    else if (hours === 0) label = `${mins}m`;
    else if (mins === 0) label = `${hours}h`;
    else label = `${hours}h${mins}m`;
    timeTicks.push({ time: t, major, label });
  }

  return (
    <div ref={measuredRef}>
      <svg width={svgWidth} height={CHART_HEIGHT} className="select-none">
        {/* Y grid + labels */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const y = MARGIN.top + (i / yTicks) * plotH;
          const temp = Math.round(displayMaxTemp * (1 - i / yTicks));
          return (
            <g key={`yg-${i}`}>
              <line x1={MARGIN.left} y1={y} x2={MARGIN.left + plotW} y2={y} stroke="var(--chart-grid)" strokeDasharray="3 3" />
              <text x={MARGIN.left - 8} y={y + 4} fill="var(--chart-text)" fontSize={10} textAnchor="end">{temp}</text>
            </g>
          );
        })}
        {/* X grid + labels */}
        {timeTicks.map(({ time, major, label }) => {
          const x = toX(time);
          return (
            <g key={`xg-${time}`}>
              <line x1={x} y1={MARGIN.top} x2={x} y2={MARGIN.top + plotH} stroke="var(--chart-grid)" strokeDasharray={major ? 'none' : '3 3'} opacity={major ? 0.6 : 0.3} />
              <text x={x} y={CHART_HEIGHT - 8} fill="var(--chart-text)" fontSize={10} textAnchor="middle">{label}</text>
            </g>
          );
        })}
        {/* Axis labels */}
        <text x={svgWidth / 2} y={CHART_HEIGHT} fill="var(--chart-text)" fontSize={11} textAnchor="middle">Minutes</text>
        <text x={12} y={CHART_HEIGHT / 2} fill="var(--chart-text)" fontSize={11} textAnchor="middle" transform={`rotate(-90, 12, ${CHART_HEIGHT / 2})`}>°C</text>
        {/* Profile line */}
        <path d={pathD} fill="none" stroke="#F59E0B" strokeWidth={2} />
        {/* Points with labels */}
        {points.map((p, i) => (
          <g key={`pt-${i}`}>
            <circle cx={toX(p.time)} cy={toY(p.temp)} r={3} fill="#F59E0B" />
            {p.isRampEnd && (
              <text x={toX(p.time)} y={toY(p.temp) - 8} fill="#FBBF24" fontSize={10} fontWeight="bold" textAnchor="middle">
                {Math.round(p.temp)}°
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}
