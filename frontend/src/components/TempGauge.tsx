interface TempGaugeProps {
  value: number;
  label: string;
  alarm?: boolean;
  unit?: string;
  /** When true, dim the number to indicate it's stale / being updated. */
  pending?: boolean;
}

export function TempGauge({
  value,
  label,
  alarm = false,
  unit = '\u00B0C',
  pending = false,
}: TempGaugeProps) {
  const baseColor = alarm ? 'text-red-500' : 'text-green-600 dark:text-green-400';
  const valueClass = pending
    ? 'text-gray-400 dark:text-gray-500 transition-colors duration-300'
    : `${baseColor} transition-colors duration-300`;
  return (
    <div className="text-center">
      <div className="text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</div>
      <div className={`text-5xl font-bold ${valueClass} tabular-nums`}>
        {Math.round(value)}
        <span className="text-2xl text-gray-400">{unit}</span>
      </div>
    </div>
  );
}
