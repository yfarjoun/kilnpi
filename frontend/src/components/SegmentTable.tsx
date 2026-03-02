import type { Segment } from '../types';

interface SegmentTableProps {
  segments: Segment[];
  onChange: (segments: Segment[]) => void;
  readOnly?: boolean;
}

export function SegmentTable({ segments, onChange, readOnly = false }: SegmentTableProps) {
  const updateSegment = (index: number, field: keyof Segment, value: number) => {
    const updated = segments.map((s, i) =>
      i === index ? { ...s, [field]: value } : s
    );
    onChange(updated);
  };

  const addSegment = () => {
    onChange([...segments, { ramp_min: 30, soak_min: 60, target_temp: 500 }]);
  };

  const removeSegment = (index: number) => {
    onChange(segments.filter((_, i) => i !== index));
  };

  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
            <th className="py-2 text-left">#</th>
            <th className="py-2 text-left">Ramp (min)</th>
            <th className="py-2 text-left">Soak (min)</th>
            <th className="py-2 text-left">Target (&deg;C)</th>
            {!readOnly && <th className="py-2" />}
          </tr>
        </thead>
        <tbody>
          {segments.map((seg, i) => (
            <tr key={i} className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-2 text-gray-500 dark:text-gray-400">{i + 1}</td>
              <td className="py-2">
                {readOnly ? seg.ramp_min : (
                  <input
                    type="number"
                    value={seg.ramp_min}
                    onChange={(e) => updateSegment(i, 'ramp_min', Number(e.target.value))}
                    className="w-20 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-gray-900 dark:text-white"
                  />
                )}
              </td>
              <td className="py-2">
                {readOnly ? seg.soak_min : (
                  <input
                    type="number"
                    value={seg.soak_min}
                    onChange={(e) => updateSegment(i, 'soak_min', Number(e.target.value))}
                    className="w-20 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-gray-900 dark:text-white"
                  />
                )}
              </td>
              <td className="py-2">
                {readOnly ? seg.target_temp : (
                  <input
                    type="number"
                    value={seg.target_temp}
                    onChange={(e) => updateSegment(i, 'target_temp', Number(e.target.value))}
                    className="w-24 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-gray-900 dark:text-white"
                  />
                )}
              </td>
              {!readOnly && (
                <td className="py-2">
                  <button
                    onClick={() => removeSegment(i)}
                    className="text-red-500 hover:text-red-400 text-xs"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!readOnly && (
        <button
          onClick={addSegment}
          className="mt-2 px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-sm rounded text-gray-700 dark:text-white"
        >
          + Add Segment
        </button>
      )}
    </div>
  );
}
