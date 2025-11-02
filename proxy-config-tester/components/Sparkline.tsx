import React from 'react';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
  className?: string;
}

const Sparkline: React.FC<SparklineProps> = ({ data, width = 100, height = 20, strokeWidth = 1.5, className = 'stroke-primary-light dark:stroke-primary-dark' }) => {
  if (data.length < 2) return null;

  const validData = data.filter(d => d >= 0);
  if (validData.length < 2) return null;

  const maxVal = Math.max(...validData);
  const minVal = Math.min(...validData);
  const range = maxVal - minVal === 0 ? 1 : maxVal - minVal;

  const points = validData
    .map((val, index) => {
      const x = (index / (validData.length - 1)) * width;
      const y = height - ((val - minVal) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <polyline
        fill="none"
        strokeWidth={strokeWidth}
        points={points}
        className={className}
      />
    </svg>
  );
};

export default Sparkline;