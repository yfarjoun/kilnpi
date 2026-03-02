interface TempGaugeProps {
  value: number;
  label: string;
  alarm?: boolean;
  unit?: string;
}

export function TempGauge({ value, label, alarm = false, unit = '°C' }: TempGaugeProps) {
  const color = alarm ? 'text-red-500' : 'text-green-400';
  return (
    <div className="text-center">
      <div className="text-sm text-gray-400 uppercase tracking-wide">{label}</div>
      <div className={`text-5xl font-bold ${color} tabular-nums`}>
        {value.toFixed(1)}
        <span className="text-2xl text-gray-400">{unit}</span>
      </div>
    </div>
  );
}
