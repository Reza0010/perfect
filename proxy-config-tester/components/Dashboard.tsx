import React from 'react';
import { ProxyConfig, Status, Protocol } from '../types';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';

ChartJS.register(ArcElement, Tooltip, Legend);

interface DashboardProps {
  configs: ProxyConfig[];
  t: (key: string) => string;
}

const Dashboard: React.FC<DashboardProps> = ({ configs, t }) => {
  const stats = React.useMemo(() => {
    const total = configs.length;
    const active = configs.filter(c => c.status === Status.Active).length;
    const slow = configs.filter(c => c.status === Status.Slow).length;
    const inactive = configs.filter(c => c.status === Status.Inactive).length;
    const untested = configs.filter(c => c.status === Status.Untested || c.status === Status.Testing).length;
    const averageLatency = total > 0 
      ? configs.filter(c => c.latency > 0).reduce((acc, c) => acc + c.latency, 0) / configs.filter(c => c.latency > 0).length
      : 0;

    return { total, active, slow, inactive, untested, averageLatency: Math.round(averageLatency) };
  }, [configs]);
  
  const isDarkMode = document.documentElement.classList.contains('dark');
  const chartTextColor = isDarkMode ? '#f9fafb' : '#111827';
  const chartBorderColor = isDarkMode ? '#1f2937' : '#ffffff';

  const statusData = {
    labels: [t('active'), t('slow'), t('inactive'), t('untested')],
    datasets: [{
        data: [stats.active, stats.slow, stats.inactive, stats.untested],
        backgroundColor: ['#22c55e', '#f97316', '#ef4444', '#6b7280'],
        borderColor: chartBorderColor,
        borderWidth: 2,
    }],
  };
  
  const protocolCounts = Object.values(Protocol).reduce((acc, p) => {
    const count = configs.filter(c => c.protocol === p).length;
    if (count > 0) acc[p] = count;
    return acc;
}, {} as Record<string, number>);

  const protocolData = {
      labels: Object.keys(protocolCounts),
      datasets: [{
          data: Object.values(protocolCounts),
          backgroundColor: ['#3b82f6', '#8b5cf6', '#ec4899', '#10b981', '#f59e0b', '#d946ef', '#78716c'],
          borderColor: chartBorderColor,
          borderWidth: 2,
      }],
  };
  
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            position: 'bottom' as const,
            labels: { color: chartTextColor, padding: 20, font: { size: 14 } }
        },
        tooltip: {
            bodyFont: { size: 14 },
            titleFont: { size: 16 }
        }
    },
    cutout: '60%',
  };


  const StatCard: React.FC<{ title: string; value: string | number; color: string }> = ({ title, value, color }) => (
    <div className="bg-gradient-to-br from-surface-light to-background-light dark:from-surface-dark dark:to-background-dark p-6 rounded-lg shadow-md border-l-4" style={{borderColor: color}}>
      <h3 className="text-sm font-medium text-text-secondary-light dark:text-text-secondary-dark">{title}</h3>
      <p className="mt-1 text-3xl font-semibold text-text-primary-light dark:text-text-primary-dark">{value}</p>
    </div>
  );

  return (
    <div className="p-4 md:p-6 space-y-6">
      <h1 className="text-3xl font-bold text-text-primary-light dark:text-text-primary-dark">{t('welcome_dashboard')}</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title={t('total_configs')} value={stats.total} color="#3b82f6" />
        <StatCard title={t('active')} value={stats.active} color="#22c55e" />
        <StatCard title={t('inactive')} value={stats.inactive} color="#ef4444" />
        <StatCard title={`${t('col_latency')} (Avg)`} value={stats.averageLatency > 0 ? `${stats.averageLatency} ms` : 'N/A'} color="#f97316" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-gradient-to-br from-surface-light to-background-light dark:from-surface-dark dark:to-background-dark p-6 rounded-lg shadow-md">
            <h2 className="text-lg font-semibold mb-4 text-center">{t('status_chart_title')}</h2>
            <div className="relative h-64 md:h-80">
              <Doughnut data={statusData} options={chartOptions} />
            </div>
        </div>

        <div className="bg-gradient-to-br from-surface-light to-background-light dark:from-surface-dark dark:to-background-dark p-6 rounded-lg shadow-md">
            <h2 className="text-lg font-semibold mb-4 text-center">{t('protocol_chart_title')}</h2>
             <div className="relative h-64 md:h-80">
              <Doughnut data={protocolData} options={chartOptions} />
            </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;