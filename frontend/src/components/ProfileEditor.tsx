import type { Segment } from '../types';
import { SegmentTable } from './SegmentTable';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
} from 'recharts';

interface ProfileEditorProps {
  segments: Segment[];
  onChange: (segments: Segment[]) => void;
}

function buildProfilePoints(segments: Segment[]): { time: number; temp: number }[] {
  const points: { time: number; temp: number }[] = [{ time: 0, temp: 25 }];
  let time = 0;
  for (const seg of segments) {
    time += seg.ramp_min;
    points.push({ time, temp: seg.target_temp });
    time += seg.soak_min;
    points.push({ time, temp: seg.target_temp });
  }
  return points;
}

export function ProfileEditor({ segments, onChange }: ProfileEditorProps) {
  const profileData = buildProfilePoints(segments);

  return (
    <div className="space-y-4">
      <div className="bg-gray-800 rounded-lg p-4">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={profileData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" stroke="#9CA3AF" label={{ value: 'Minutes', position: 'bottom', fill: '#9CA3AF' }} />
            <YAxis stroke="#9CA3AF" label={{ value: '°C', angle: -90, position: 'insideLeft', fill: '#9CA3AF' }} />
            <Line type="linear" dataKey="temp" stroke="#F59E0B" dot strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <SegmentTable segments={segments} onChange={onChange} />
    </div>
  );
}
