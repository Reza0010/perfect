import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { LOCALES } from './constants';
import { Page, Status, ProxyConfig, SettingsData, Protocol } from './types';
import ConfigManager from './components/ConfigManager';
import Dashboard from './components/Dashboard';
import Settings from './components/Settings';
import { DashboardIcon, ConfigsIcon, SettingsIcon, SunIcon, MoonIcon } from './components/Icons';
import { v4 as uuidv4 } from 'uuid';

const APP_SETTINGS_KEY = 'proxy-tester-settings';
const APP_CONFIGS_KEY = 'proxy-tester-configs';

const defaultSettings: SettingsData = {
  theme: 'dark',
  language: 'en',
  timeout: 3000,
  concurrentTests: 5,
  endpoint: 'https://ifconfig.me',
  autoTestInterval: 0,
  autoTestOnlyInactive: true,
  subscriptions: [],
  smartGroups: [],
};

const App: React.FC = () => {
  const [settings, setSettings] = useState<SettingsData>(() => {
    try {
      const storedSettings = localStorage.getItem(APP_SETTINGS_KEY);
      // Merge stored settings with defaults to ensure new settings are applied
      return storedSettings ? { ...defaultSettings, ...JSON.parse(storedSettings) } : defaultSettings;
    } catch (error) {
      return defaultSettings;
    }
  });

  const [configs, setConfigs] = useState<ProxyConfig[]>(() => {
    try {
      const storedConfigs = localStorage.getItem(APP_CONFIGS_KEY);
      return storedConfigs ? JSON.parse(storedConfigs) : [];
    } catch (error) {
      return [];
    }
  });

  const [activePageId, setActivePageId] = useState<'dashboard' | 'configs' | 'settings'>('configs');
  
  const t = useCallback((key: string, replacements?: Record<string, string | number>): string => {
    let translation = LOCALES[settings.language]?.[key] || key;
    if (replacements) {
        Object.entries(replacements).forEach(([key, value]) => {
            translation = translation.replace(`{${key}}`, String(value));
        });
    }
    return translation;
  }, [settings.language]);

  const addProcessedConfigs = useCallback((rawConfigs: string[]): number => {
    const existingConfigs = new Set(configs.map(c => c.rawConfig));
    const parseConfig = (raw: string): Partial<ProxyConfig> | null => {
        // This is a simplified parser. It should be consistent with the one in ConfigManager.
        try {
            if (raw.startsWith('vmess://')) return { protocol: Protocol.Vmess };
            if (raw.startsWith('vless://')) return { protocol: Protocol.Vless };
            if (raw.startsWith('ss://')) return { protocol: Protocol.Shadowsocks };
            if (raw.startsWith('trojan://')) return { protocol: Protocol.Trojan };
        } catch {}
        return { protocol: Protocol.Unknown };
    };

    const newConfigs: ProxyConfig[] = rawConfigs
      .filter(raw => raw.trim() !== '' && !existingConfigs.has(raw))
      .map(raw => {
          const parsed = parseConfig(raw) || {};
           const url = new URL(raw.replace(/^ss:\/\//, 'http://')); // Handle SS parsing
           const name = decodeURIComponent(url.hash.substring(1));
          return {
              id: uuidv4(), name: name || 'New Config', protocol: Protocol.Unknown, host: 'N/A', port: 0, ip: 'N/A',
              country: 'Unknown', countryCode: 'UNKNOWN', latency: -1, status: Status.Untested, score: 0,
              lastTested: 'Never', rawConfig: raw, latencyHistory: [], speed: 0, group: undefined, ...parsed,
          };
      });
      
    if (newConfigs.length > 0) {
        setConfigs(prev => [...prev, ...newConfigs]);
        alert(t('imported_n_configs', { count: newConfigs.length }));
    }
    return newConfigs.length;
  }, [configs, t]);


  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove(settings.theme === 'dark' ? 'light' : 'dark');
    root.classList.add(settings.theme);
    document.documentElement.lang = settings.language;
    document.documentElement.dir = settings.language === 'fa' ? 'rtl' : 'ltr';
    localStorage.setItem(APP_SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);
  
  useEffect(() => {
    localStorage.setItem(APP_CONFIGS_KEY, JSON.stringify(configs));
  }, [configs]);

  // Handle importing from share link
  useEffect(() => {
    const hash = window.location.hash;
    if (hash.startsWith('#import=')) {
        try {
            const encodedData = hash.substring('#import='.length);
            const decodedJson = atob(encodedData);
            const sharedRawConfigs = JSON.parse(decodedJson);
            if (Array.isArray(sharedRawConfigs)) {
                addProcessedConfigs(sharedRawConfigs);
            }
        } catch (e) {
            console.error("Failed to import from share link", e);
        } finally {
            // Clean the URL
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
    }
  }, [addProcessedConfigs]);

  const handleSaveSettings = (newSettings: SettingsData) => {
    setSettings(newSettings);
  };

  const handleImportData = (newSettings: SettingsData, newConfigs: ProxyConfig[]) => {
    setSettings(newSettings);
    setConfigs(newConfigs);
  };

  const toggleTheme = () => {
    setSettings(prev => ({...prev, theme: prev.theme === 'light' ? 'dark' : 'light'}));
  };

  const pages: Page[] = useMemo(() => [
    { id: 'dashboard', name: t('dashboard'), icon: <DashboardIcon /> },
    { id: 'configs', name: t('configs'), icon: <ConfigsIcon /> },
    { id: 'settings', name: t('settings'), icon: <SettingsIcon /> },
  ], [t]);
  
  const footerStats = useMemo(() => {
      const total = configs.length;
      const active = configs.filter(c => c.status === Status.Active || c.status === Status.Slow).length;
      const inactive = configs.filter(c => c.status === Status.Inactive).length;
      return { total, active, inactive };
  }, [configs]);

  const renderPage = () => {
    switch(activePageId) {
      case 'dashboard':
        return <Dashboard configs={configs} t={t} />;
      case 'configs':
        return <ConfigManager t={t} configs={configs} setConfigs={setConfigs} settings={settings} />;
      case 'settings':
        return <Settings t={t} settings={settings} onSave={handleSaveSettings} configs={configs} onImport={handleImportData} />;
      default:
        return <ConfigManager t={t} configs={configs} setConfigs={setConfigs} settings={settings} />;
    }
  }

  return (
    <div className="flex h-screen bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark font-sans">
      {/* Sidebar */}
      <aside className="w-64 bg-surface-light dark:bg-surface-dark border-r border-border-light dark:border-border-dark flex flex-col">
        <div className="h-16 flex items-center justify-center border-b border-border-light dark:border-border-dark px-4">
          <h1 className="text-xl font-bold text-primary-light dark:text-primary-dark whitespace-nowrap">{t('app_title')}</h1>
        </div>
        <nav className="flex-grow p-4 space-y-2">
          {pages.map(page => (
            <button
              key={page.id}
              onClick={() => setActivePageId(page.id)}
              className={`w-full flex items-center space-x-3 rtl:space-x-reverse px-4 py-2 rounded-lg transition-colors relative ${
                activePageId === page.id
                  ? 'bg-primary-light/10 dark:bg-primary-dark/20 text-primary-light dark:text-primary-dark font-semibold'
                  : 'text-text-secondary-light dark:text-text-secondary-dark hover:bg-background-light dark:hover:bg-gray-800 hover:text-text-primary-light dark:hover:text-text-primary-dark'
              }`}
            >
              {activePageId === page.id && (
                <span className="absolute left-0 rtl:left-auto rtl:right-0 top-2 bottom-2 w-1 bg-primary-light dark:bg-primary-dark rounded-r-full rtl:rounded-r-none rtl:rounded-l-full"></span>
              )}
              {page.icon}
              <span>{page.name}</span>
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-border-light dark:border-border-dark">
            <button onClick={toggleTheme} className="w-full flex items-center justify-center space-x-3 rtl:space-x-reverse px-4 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
                {settings.theme === 'light' ? <MoonIcon /> : <SunIcon />}
                <span>{settings.theme === 'light' ? t('dark_mode') : t('light_mode')}</span>
            </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {renderPage()}
        </div>
        
        {/* Status Bar */}
        {activePageId === 'configs' && (
          <footer className="h-10 bg-surface-light dark:bg-surface-dark border-t border-border-light dark:border-border-dark flex items-center px-4 text-sm text-text-secondary-light dark:text-text-secondary-dark">
             <span>{t('total_configs')}: {footerStats.total}</span>
             <span className="mx-2">|</span>
             <span className="text-green-500">{t('active_configs')}: {footerStats.active}</span>
             <span className="mx-2">|</span>
             <span className="text-red-500">{t('inactive_configs')}: {footerStats.inactive}</span>
          </footer>
        )}
      </main>
    </div>
  );
};

export default App;
