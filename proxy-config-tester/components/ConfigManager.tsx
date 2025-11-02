import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  ProxyConfig,
  Status,
  Protocol,
  SortKey,
  SortDirection,
  SettingsData,
  Rule,
} from '../types';
import { COUNTRIES } from '../constants';
import { ChevronUpIcon, ChevronDownIcon, ShareIcon, TrashIcon, TagIcon, ExportIcon, QrCodeIcon, CopyIcon, LinkIcon } from './Icons';
import Sparkline from './Sparkline';
import Modal from './Modal';
import { v4 as uuidv4 } from 'uuid';
import QRCode from 'qrcode.react';

interface ConfigManagerProps {
  t: (key: string) => string;
  configs: ProxyConfig[];
  setConfigs: React.Dispatch<React.SetStateAction<ProxyConfig[]>>;
  settings: SettingsData;
}

// Mocked parser and tester
const parseConfig = (raw: string): Partial<ProxyConfig> | null => {
    try {
        if (raw.startsWith('vmess://')) {
            const decoded = atob(raw.replace('vmess://', ''));
            const data = JSON.parse(decoded);
            return {
                protocol: Protocol.Vmess,
                name: data.ps || 'Vmess Config',
                host: data.add,
                port: Number(data.port),
            };
        } else if (raw.startsWith('vless://') || raw.startsWith('ss://') || raw.startsWith('trojan://')) {
            const url = new URL(raw);
            const protocolStr = url.protocol.replace(':', '');
            let protocol: Protocol = Protocol.Unknown;
            if (protocolStr === 'vless') protocol = Protocol.Vless;
            else if (protocolStr === 'ss') protocol = Protocol.Shadowsocks;
            else if (protocolStr === 'trojan') protocol = Protocol.Trojan;

            return {
                protocol,
                name: decodeURIComponent(url.hash.substring(1)) || `${protocol} Config`,
                host: url.hostname,
                port: Number(url.port),
            };
        }
    } catch (error) {
        console.error("Failed to parse config:", raw, error);
    }
    return { name: "Unnamed Config", host: "unknown.host", port: 0, protocol: Protocol.Unknown };
};

const testConfig = async (config: ProxyConfig, timeout: number): Promise<Partial<ProxyConfig>> => {
    return new Promise(resolve => {
        const testLatency = 50 + Math.floor(Math.random() * 2000);
        setTimeout(async () => {
            const newHistory = [testLatency, ...config.latencyHistory].slice(0, 10);
            if (testLatency > timeout || Math.random() > 0.8) {
                resolve({ 
                    status: Status.Inactive, 
                    latency: -1, 
                    score: 0, 
                    speed: 0, 
                    latencyHistory: [-1, ...config.latencyHistory].slice(0, 10) 
                });
            } else {
                const status = testLatency > 1000 ? Status.Slow : Status.Active;
                const score = Math.max(0, Math.round(100 - testLatency / 20));
                const baseSpeed = Math.max(50, 2000 - testLatency); // KB/s
                const speed = Math.round(baseSpeed + (Math.random() * baseSpeed * 0.2 - baseSpeed * 0.1));

                const updatedInfo: Partial<ProxyConfig> = {
                    status,
                    latency: testLatency,
                    score,
                    latencyHistory: newHistory,
                    speed,
                };
                
                try {
                    // Use a more reliable geolocation API that supports domain lookups
                    const response = await fetch(`https://ipinfo.io/${config.host}/json`);
                    if (response.ok) {
                        const geoData = await response.json();
                        if (geoData && !geoData.bogon) { // bogon check for private/reserved IPs
                            updatedInfo.ip = geoData.ip;
                            const countryCode = Object.keys(COUNTRIES).find(c => c === geoData.country) || 'UNKNOWN';
                            updatedInfo.countryCode = countryCode;
                            updatedInfo.country = COUNTRIES[countryCode]?.name || 'Unknown';
                        }
                    }
                } catch (e) {
                    console.error('Geolocation fetch failed for', config.host, e);
                }

                resolve(updatedInfo);
            }
        }, 50 + Math.random() * 500);
    });
};


const ConfigManager: React.FC<ConfigManagerProps> = ({ t, configs, setConfigs, settings }) => {
    const [isTesting, setIsTesting] = useState(false);
    const [statusFilter, setStatusFilter] = useState<Status | 'All'>('All');
    const [protocolFilter, setProtocolFilter] = useState<Protocol | 'All'>('All');
    const [groupFilter, setGroupFilter] = useState<string>('All');
    const [searchTerm, setSearchTerm] = useState('');
    const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: SortDirection }>({ key: 'latency', direction: 'asc' });
    const [inputConfigs, setInputConfigs] = useState('');
    const [activeTab, setActiveTab] = useState<'paste' | 'file' | 'sub'>('paste');
    const testingStopFlag = useRef(false);
    const autoTestIntervalRef = useRef<number | null>(null);
    const [counters, setCounters] = useState({ success: 0, fail: 0 });
    const [testProgress, setTestProgress] = useState(0);
    const [selectedConfigIds, setSelectedConfigIds] = useState(new Set<string>());
    const [copyButtonText, setCopyButtonText] = useState(t('share_selected'));
    const [copyBestButtonText, setCopyBestButtonText] = useState(t('copy_best'));
    const selectAllCheckboxRef = useRef<HTMLInputElement>(null);
    const [qrModalConfig, setQrModalConfig] = useState<ProxyConfig | null>(null);
    const [isFetchingSubs, setIsFetchingSubs] = useState(false);
    const [isGroupDropdownOpen, setIsGroupDropdownOpen] = useState(false);
    const groupDropdownRef = useRef<HTMLDivElement>(null);

    const evaluateRule = (config: ProxyConfig, rule: Rule): boolean => {
      const configValue = config[rule.field];
      const ruleValue = rule.value;

      if (configValue === undefined || configValue === null) return false;

      const numFields = ['latency', 'score', 'speed'];
      const strFields = ['name', 'protocol', 'host', 'country', 'group', 'rawConfig'];

      let valA = configValue;
      let valB = ruleValue;

      if(numFields.includes(rule.field)) {
        valA = Number(valA);
        valB = Number(valB);
        if (isNaN(valA) || isNaN(valB)) return false;

        switch (rule.operator) {
            case 'equals': return valA === valB;
            case 'not_equals': return valA !== valB;
            case 'greater_than': return valA > valB;
            case 'less_than': return valA < valB;
            default: return false;
        }
      } else if (strFields.includes(rule.field)) {
          valA = String(valA).toLowerCase();
          valB = String(valB).toLowerCase();

          switch(rule.operator) {
            case 'contains': return valA.includes(valB);
            case 'not_contains': return !valA.includes(valB);
            case 'equals': return valA === valB;
            case 'not_equals': return valA !== valB;
            default: return false;
          }
      }
      return false;
    }

    const configsWithSmartGroups = useMemo(() => {
        return configs.map(c => {
            const matchedGroups = settings.smartGroups
                .filter(sg => sg.rules.every(rule => evaluateRule(c, rule)))
                .map(sg => sg.name);
            return { ...c, smartGroups: matchedGroups };
        });
    }, [configs, settings.smartGroups]);

    const uniqueGroups = useMemo(() => {
        const manualGroups = new Set(configs.map(c => c.group).filter(Boolean));
        const smartGroupNames = new Set(settings.smartGroups.map(sg => sg.name));
        return {
          manual: Array.from(manualGroups) as string[],
          smart: Array.from(smartGroupNames) as string[]
        };
    }, [configs, settings.smartGroups]);

    const filteredAndSortedConfigs = useMemo(() => {
        return configsWithSmartGroups
            .filter(c => statusFilter === 'All' || c.status === statusFilter)
            .filter(c => protocolFilter === 'All' || c.protocol === protocolFilter)
            .filter(c => {
                if (groupFilter === 'All') return true;
                if (groupFilter === 'none') return !c.group;
                return c.group === groupFilter || c.smartGroups.includes(groupFilter);
            })
            .filter(c =>
                c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                c.host.toLowerCase().includes(searchTerm.toLowerCase())
            )
            .sort((a, b) => {
                const key = sortConfig.key;
                let aVal: any = a[key];
                let bVal: any = b[key];

                if (key === 'latency') {
                    aVal = a.latency === -1 ? Infinity : a.latency;
                    bVal = b.latency === -1 ? Infinity : b.latency;
                } else if (key === 'group') {
                    aVal = a.group || '';
                    bVal = b.group || '';
                }

                if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
    }, [configsWithSmartGroups, statusFilter, protocolFilter, groupFilter, searchTerm, sortConfig]);

    useEffect(() => {
        if (selectAllCheckboxRef.current) {
            const allVisibleIds = filteredAndSortedConfigs.map(c => c.id);
            const selectedVisibleCount = allVisibleIds.filter(id => selectedConfigIds.has(id)).length;
            const allVisibleSelected = selectedVisibleCount === allVisibleIds.length && allVisibleIds.length > 0;
            
            selectAllCheckboxRef.current.checked = allVisibleSelected;
            selectAllCheckboxRef.current.indeterminate = !allVisibleSelected && selectedVisibleCount > 0;
        }
    }, [selectedConfigIds, filteredAndSortedConfigs]);

    useEffect(() => {
        setCopyButtonText(t('share_selected'));
        setCopyBestButtonText(t('copy_best'));
    }, [t]);

    useEffect(() => {
        setSelectedConfigIds(new Set());
    }, [statusFilter, protocolFilter, searchTerm, groupFilter]);

    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (groupDropdownRef.current && !groupDropdownRef.current.contains(event.target as Node)) {
          setIsGroupDropdownOpen(false);
        }
      };
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Auto-testing logic
    useEffect(() => {
        if (autoTestIntervalRef.current) {
            clearInterval(autoTestIntervalRef.current);
        }

        if (settings.autoTestInterval > 0 && !isTesting) {
            const startAutoTest = async () => {
                if (document.hidden) return; // Don't run if tab is not active

                const configsToTest = settings.autoTestOnlyInactive
                    ? configs.filter(c => c.status === Status.Inactive || c.status === Status.Untested)
                    : [...configs];

                if (configsToTest.length === 0) return;

                // Use a silent test run without full UI feedback
                for (const config of configsToTest) {
                     const result = await testConfig(config, settings.timeout);
                     setConfigs(prev => prev.map(c =>
                        c.id === config.id ? { ...c, ...result, lastTested: new Date().toLocaleTimeString() } : c
                     ));
                }
            };

            autoTestIntervalRef.current = window.setInterval(startAutoTest, settings.autoTestInterval * 60 * 1000);

            return () => {
                if (autoTestIntervalRef.current) {
                    clearInterval(autoTestIntervalRef.current);
                }
            };
        }
    }, [settings.autoTestInterval, settings.autoTestOnlyInactive, configs, isTesting, setConfigs, settings.timeout]);


    const handleSort = (key: SortKey) => {
        let direction: SortDirection = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };
    
    const addProcessedConfigs = (rawConfigs: string[]) => {
      const existingConfigs = new Set(configs.map(c => c.rawConfig));
      const newConfigs: ProxyConfig[] = rawConfigs
        .filter(raw => raw.trim() !== '' && !existingConfigs.has(raw))
        .map(raw => {
            const parsed = parseConfig(raw) || {};
            return {
                id: uuidv4(),
                name: 'New Config',
                protocol: Protocol.Unknown,
                host: 'N/A',
                port: 0,
                ip: 'N/A',
                country: 'Unknown',
                countryCode: 'UNKNOWN',
                latency: -1,
                status: Status.Untested,
                score: 0,
                lastTested: 'Never',
                rawConfig: raw,
                latencyHistory: [],
                speed: 0,
                group: undefined,
                ...parsed,
            };
        });
        if (newConfigs.length > 0) {
            setConfigs(prev => [...prev, ...newConfigs]);
        }
        return newConfigs.length;
    }

    const processInputs = () => {
        const raw = inputConfigs.split('\n');
        addProcessedConfigs(raw);
        setInputConfigs('');
    };

    const handleFetchSubscription = async (url: string) => {
        const fakeResponse = `vmess://ew0KICAidiI6ICIyIiwNCiAgInBzIjogIkV4YW1wbGUgVk1FU1MiLA0KICAiYWRkIjogImV4YW1wbGUuY29tIiwNCiAgInBvcnQiOiAiNDQzIiwNCiAgImlkIjogIjEyMzRhYmNkLWY1NjctNDg4OS05ZWExLTc4OWVmMjFjYmFkMSIsDQogICJhaWQiOiAiMCIsDQogICJuZXQiOiAidGNwIiwNCiAgInR5cGUiOiAibm9uZSIsDQogICJob3N0IjogIiIsDQogICJwYXRoIjogIiIsDQogICJ0bHMiOiAibm9uZSIKfQ==
vless://f9a0c085-1cc4-46d3-943b-5c8a394ddc57@23.128.34.43:443?encryption=none&type=ws&security=tls&sni=test.mysite.com#NewFromSub
ss://aes-256-gcm:myVoice@192.168.1.1:12345#Shadowsocks%20Example
trojan://password@192.168.1.2:443#Trojan%20Example`;
        
        let newConfigsCount = 0;
        try {
            // In a real app, you would fetch(url).then(res => res.text())
            // For now, we simulate a response
            const content = fakeResponse; // await (await fetch(url)).text();
            let configsToAdd: string[] = [];
            try {
                // Try decoding from base64 first
                const decodedContent = atob(content);
                configsToAdd = decodedContent.split('\n');
            } catch (e) {
                // If not base64, assume plain text
                configsToAdd = content.split('\n');
            }
            newConfigsCount = addProcessedConfigs(configsToAdd);
        } catch (error) {
            console.error("Failed to fetch subscription:", url, error);
            alert(`Failed to fetch from ${url}`);
        }
        return newConfigsCount;
    };

    const handleFetchAllSubscriptions = async () => {
        setIsFetchingSubs(true);
        let totalNewConfigs = 0;
        const enabledSubs = settings.subscriptions.filter(s => s.enabled);
        for (const sub of enabledSubs) {
            totalNewConfigs += await handleFetchSubscription(sub.url);
        }
        setIsFetchingSubs(false);
        alert(t('fetched_n_configs', { count: totalNewConfigs }));
    };

    const startTesting = useCallback(async () => {
        setIsTesting(true);
        testingStopFlag.current = false;
        setCounters({ success: 0, fail: 0 });
        setTestProgress(0);

        const configsToTest = filteredAndSortedConfigs.filter(c => c.status === Status.Untested || c.status === Status.Inactive);
        let testedCount = 0;
        
        setConfigs(prev => prev.map(c => 
            configsToTest.some(ct => ct.id === c.id) ? {...c, status: Status.Testing} : c
        ));

        const queue = [...configsToTest];
        let running = 0;

        const runNext = async () => {
            if (testingStopFlag.current) {
                if (running === 0) {
                    setIsTesting(false);
                    setConfigs(prev => prev.map(c => c.status === Status.Testing ? {...c, status: Status.Untested} : c));
                }
                return;
            }

            if (queue.length === 0) {
                if (running === 0) setIsTesting(false);
                return;
            }

            running++;
            const config = queue.shift()!;
            
            const result = await testConfig(config, settings.timeout);
            
            if (!testingStopFlag.current) {
                setCounters(prev => ({
                    success: result.status === Status.Active || result.status === Status.Slow ? prev.success + 1 : prev.success,
                    fail: result.status === Status.Inactive ? prev.fail + 1 : prev.fail,
                }));
                setConfigs(prev => prev.map(c =>
                    c.id === config.id ? { ...c, ...result, lastTested: new Date().toLocaleTimeString() } : c
                ));
            }
            
            testedCount++;
            setTestProgress(Math.round((testedCount / configsToTest.length) * 100));
            running--;
            runNext();
        };

        for (let i = 0; i < Math.min(settings.concurrentTests, queue.length); i++) {
            runNext();
        }
    }, [filteredAndSortedConfigs, settings.concurrentTests, settings.timeout, setConfigs]);

    const stopTesting = () => {
        testingStopFlag.current = true;
    };

    const clearAllConfigs = useCallback(() => {
        if (window.confirm(t('confirm_clear_all'))) {
            setConfigs([]);
        }
    }, [t, setConfigs]);
    
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                const content = event.target?.result as string;
                addProcessedConfigs(content.split('\n'));
            };
            reader.readAsText(file);
        }
    };

    const handleSelectConfig = (id: string, checked: boolean) => {
        setSelectedConfigIds(prev => {
            const newSet = new Set(prev);
            if (checked) {
                newSet.add(id);
            } else {
                newSet.delete(id);
            }
            return newSet;
        });
    };

    const handleSelectAll = (checked: boolean) => {
        const allVisibleIds = filteredAndSortedConfigs.map(c => c.id);
        if (checked) {
            setSelectedConfigIds(prev => new Set([...prev, ...allVisibleIds]));
        } else {
            setSelectedConfigIds(prev => {
                const newSet = new Set(prev);
                allVisibleIds.forEach(id => newSet.delete(id));
                return newSet;
            });
        }
    };

    const handleShareSelected = () => {
        const selectedRawConfigs = configs
            .filter(c => selectedConfigIds.has(c.id))
            .map(c => c.rawConfig)
            .join('\n');
        
        if(selectedRawConfigs) {
            navigator.clipboard.writeText(selectedRawConfigs).then(() => {
                setCopyButtonText(t('copied_to_clipboard'));
                setTimeout(() => setCopyButtonText(t('share_selected')), 2000);
            });
        }
    };

    const handleDeleteSelected = useCallback(() => {
        if(window.confirm(t('confirm_delete_selected'))) {
            setConfigs(prev => prev.filter(c => !selectedConfigIds.has(c.id)));
            setSelectedConfigIds(new Set());
        }
    }, [t, setConfigs, selectedConfigIds]);

    const handleSetGroup = () => {
        const groupName = prompt(t('enter_group_name'));
        if (groupName !== null) { // Allow empty string to remove group
            setConfigs(prev => prev.map(c => 
                selectedConfigIds.has(c.id) ? { ...c, group: groupName || undefined } : c
            ));
        }
    };

    const handleExportForHiddify = () => {
        const selectedConfigsToExport = configs
          .filter(c => selectedConfigIds.has(c.id))
          .filter(c => c.status === Status.Active || c.status === Status.Slow);

        if (selectedConfigsToExport.length === 0) {
            alert(t('no_active_configs_to_export'));
            return;
        }

        const title = btoa('Proxy Config Tester Export');
        const hiddifyHeaders = [
            `#profile-title: base64:${title}`,
            '#profile-update-interval: 1',
            '#subscription-userinfo: upload=0; download=0; total=1099511627776; expire=0',
            '#support-url: https://github.com',
            '#profile-web-page-url: https://github.com'
        ].join('\n');

        const content = hiddifyHeaders + '\n\n' + selectedConfigsToExport.map(c => c.rawConfig).join('\n');
        
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        const today = new Date().toISOString().slice(0, 10);
        link.download = `hiddify_export_${today}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const handleCopyBest = () => {
        const activeConfigs = configs.filter(c => (c.status === Status.Active || c.status === Status.Slow) && c.latency > -1);
        if(activeConfigs.length === 0) {
            alert(t('no_active_config_found'));
            return;
        }
        const bestConfig = activeConfigs.reduce((best, current) => current.latency < best.latency ? current : best);
        navigator.clipboard.writeText(bestConfig.rawConfig).then(() => {
            setCopyBestButtonText(t('best_config_copied'));
            setTimeout(() => setCopyBestButtonText(t('copy_best')), 2000);
        });
    };

    const handleShareGroup = (groupName: string, isSmart: boolean) => {
        const configsToShare = configsWithSmartGroups.filter(c => {
          if (groupName === 'All') return true;
          if (groupName === 'none') return !c.group;
          return c.group === groupName || (isSmart && c.smartGroups.includes(groupName));
        }).map(c => c.rawConfig);

        const encoded = btoa(JSON.stringify(configsToShare));
        const url = `${window.location.origin}${window.location.pathname}#import=${encoded}`;
        navigator.clipboard.writeText(url).then(() => {
            alert(t('share_link_copied'));
        });
    };

    const getStatusClass = (status: Status) => {
        switch (status) {
            case Status.Active: return 'bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-300';
            case Status.Slow: return 'bg-yellow-100 dark:bg-yellow-900/50 text-yellow-800 dark:text-yellow-300';
            case Status.Inactive: return 'bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-300';
            case Status.Testing: return 'bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-300 animate-pulse';
            default: return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300';
        }
    };
    
    const renderSortIcon = (key: SortKey) => {
      if (sortConfig.key !== key) return null;
      return sortConfig.direction === 'asc' ? <ChevronUpIcon /> : <ChevronDownIcon />;
    };

    return (
        <div className="flex flex-col h-full p-4 md:p-6 space-y-4">
            <Modal isOpen={!!qrModalConfig} onClose={() => setQrModalConfig(null)} title={t('qr_code')}>
                {qrModalConfig && (
                    <div className="flex flex-col items-center space-y-4">
                        <QRCode value={qrModalConfig.rawConfig} size={256} className="p-2 bg-white" />
                        <p className="font-mono text-xs break-all">{qrModalConfig.rawConfig}</p>
                    </div>
                )}
            </Modal>

            {/* Add Configs Section */}
            <div className="bg-surface-light dark:bg-surface-dark p-4 rounded-lg shadow">
                <h2 className="text-lg font-semibold mb-3">{t('add_configs')}</h2>
                <div className="flex border-b border-border-light dark:border-border-dark mb-3">
                    <button onClick={() => setActiveTab('paste')} className={`px-4 py-2 text-sm ${activeTab === 'paste' ? 'border-b-2 border-primary-light dark:border-primary-dark font-medium' : 'text-text-secondary-light dark:text-text-secondary-dark'}`}>{t('paste_links')}</button>
                    <button onClick={() => setActiveTab('file')} className={`px-4 py-2 text-sm ${activeTab === 'file' ? 'border-b-2 border-primary-light dark:border-primary-dark font-medium' : 'text-text-secondary-light dark:text-text-secondary-dark'}`}>{t('from_file')}</button>
                    <button onClick={() => setActiveTab('sub')} className={`px-4 py-2 text-sm ${activeTab === 'sub' ? 'border-b-2 border-primary-light dark:border-primary-dark font-medium' : 'text-text-secondary-light dark:text-text-secondary-dark'}`}>{t('subscription_url')}</button>
                </div>
                {activeTab === 'paste' && (
                    <div className="space-y-2">
                        <textarea value={inputConfigs} onChange={(e) => setInputConfigs(e.target.value)} rows={4} className="w-full p-2 border border-border-light dark:border-border-dark rounded-md bg-background-light dark:bg-gray-800 focus:ring-1 focus:ring-primary-light dark:focus:ring-primary-dark" placeholder="ss://...&#10;vmess://...&#10;vless://..."></textarea>
                        <button onClick={processInputs} className="w-full sm:w-auto px-4 py-2 bg-primary-light dark:bg-primary-dark text-white rounded-md hover:opacity-90">{t('process_configs')}</button>
                    </div>
                )}
                {activeTab === 'file' && (
                     <div className="border-2 border-dashed border-border-light dark:border-border-dark rounded-md p-6 text-center">
                        <input type="file" id="file-upload" accept=".txt,.json" onChange={handleFileChange} className="hidden" />
                        <label htmlFor="file-upload" className="cursor-pointer">
                            <p>{t('drop_files_here')}</p>
                            <p className="text-sm text-text-secondary-light dark:text-text-secondary-dark">{t('or_click_to_upload')}</p>
                        </label>
                    </div>
                )}
                {activeTab === 'sub' && (
                    <div className="space-y-2">
                        <button onClick={handleFetchAllSubscriptions} disabled={isFetchingSubs} className="w-full sm:w-auto px-4 py-2 bg-primary-light dark:bg-primary-dark text-white rounded-md hover:opacity-90 disabled:opacity-50">
                            {isFetchingSubs ? t('fetching_subs') : t('fetch') + ' ' + t('all')}
                        </button>
                        <p className="text-sm text-text-secondary-light dark:text-text-secondary-dark">{t('subscriptions')} {t('can be managed in settings')}.</p>
                    </div>
                )}
            </div>
            
            {/* Configs Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-surface-light dark:bg-surface-dark rounded-lg shadow">
                <div className="flex items-center space-x-4 rtl:space-x-reverse">
                    <button onClick={isTesting ? stopTesting : startTesting} className={`px-4 py-2 text-white rounded-md ${isTesting ? 'bg-red-500 hover:bg-red-600' : 'bg-secondary-light dark:bg-secondary-dark hover:opacity-90'}`}>
                        {isTesting ? t('stop_testing') : t('start_testing')}
                    </button>
                    <button onClick={handleCopyBest} className="flex items-center px-4 py-2 text-white bg-amber-500 hover:bg-amber-600 rounded-md">
                        <CopyIcon /> {copyBestButtonText}
                    </button>
                    <button onClick={clearAllConfigs} className="px-4 py-2 text-white bg-gray-500 hover:bg-gray-600 rounded-md">{t('clear_all')}</button>
                </div>
                {selectedConfigIds.size > 0 && (
                    <div className="flex items-center space-x-2 rtl:space-x-reverse">
                        <span className="text-sm text-text-secondary-light dark:text-text-secondary-dark">{t('n_selected', { count: selectedConfigIds.size })}</span>
                        <button onClick={handleShareSelected} className="flex items-center px-3 py-1.5 border border-border-light dark:border-border-dark rounded-md text-sm hover:bg-gray-100 dark:hover:bg-gray-700">
                            <ShareIcon />
                            {copyButtonText}
                        </button>
                        <button onClick={handleExportForHiddify} className="flex items-center px-3 py-1.5 border border-border-light dark:border-border-dark rounded-md text-sm hover:bg-gray-100 dark:hover:bg-gray-700">
                            <ExportIcon />
                            {t('export_for_hiddify')}
                        </button>
                        <button onClick={handleSetGroup} className="flex items-center px-3 py-1.5 border border-border-light dark:border-border-dark rounded-md text-sm hover:bg-gray-100 dark:hover:bg-gray-700">
                            <TagIcon />
                            {t('set_group')}
                        </button>
                        <button onClick={handleDeleteSelected} className="flex items-center px-3 py-1.5 border border-red-500/50 text-red-500 bg-red-500/10 rounded-md text-sm hover:bg-red-500/20">
                            <TrashIcon className="h-5 w-5 mr-2" />
                            {t('delete_selected')}
                        </button>
                    </div>
                )}
            </div>

             {/* Testing Progress Bar */}
             {isTesting && (
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 relative overflow-hidden">
                    <div className="bg-primary-light dark:bg-primary-dark h-4 rounded-full" style={{ width: `${testProgress}%`, transition: 'width 0.2s' }}></div>
                    <div className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white mix-blend-difference">
                        {t('testing_in_progress')} {testProgress}% ({counters.success} / {counters.fail})
                    </div>
                </div>
            )}
            
            {/* Filters and Search */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as any)} className="w-full p-2 border border-border-light dark:border-border-dark rounded-md bg-surface-light dark:bg-surface-dark focus:ring-1 focus:ring-primary-light dark:focus:ring-primary-dark">
                    <option value="All">{t('all')} {t('filter_by_status')}</option>
                    <option value={Status.Active}>{t('active')}</option>
                    <option value={Status.Slow}>{t('slow')}</option>
                    <option value={Status.Inactive}>{t('inactive')}</option>
                    <option value={Status.Untested}>{t('untested')}</option>
                </select>
                <select value={protocolFilter} onChange={(e) => setProtocolFilter(e.target.value as any)} className="w-full p-2 border border-border-light dark:border-border-dark rounded-md bg-surface-light dark:bg-surface-dark focus:ring-1 focus:ring-primary-light dark:focus:ring-primary-dark">
                    <option value="All">{t('all')} {t('filter_by_protocol')}</option>
                    {Object.values(Protocol).map(p => <option key={p} value={p}>{p}</option>)}
                </select>
                <div className="relative" ref={groupDropdownRef}>
                    <button onClick={() => setIsGroupDropdownOpen(prev => !prev)} className="w-full p-2 border border-border-light dark:border-border-dark rounded-md bg-surface-light dark:bg-surface-dark focus:ring-1 focus:ring-primary-light dark:focus:ring-primary-dark flex justify-between items-center">
                        <span>{groupFilter === 'All' ? t('all') + ' ' + t('filter_by_group') : groupFilter === 'none' ? t('no_group') : groupFilter}</span>
                        <ChevronDownIcon />
                    </button>
                    {isGroupDropdownOpen && (
                        <div className="absolute z-10 top-full left-0 mt-1 w-full bg-surface-light dark:bg-surface-dark border border-border-light dark:border-border-dark rounded-md shadow-lg max-h-60 overflow-y-auto">
                           <div className="p-1">
                                {['All', 'none', ...uniqueGroups.manual, ...uniqueGroups.smart].map((group, index) => {
                                    const isSmart = uniqueGroups.smart.includes(group);
                                    return (
                                        <div key={group + index} className="flex items-center justify-between px-3 py-2 text-sm rounded-md hover:bg-background-light dark:hover:bg-gray-800 cursor-pointer" >
                                           <span className="flex-grow" onClick={() => { setGroupFilter(group); setIsGroupDropdownOpen(false); }}>
                                               {group === 'All' ? t('all') : group === 'none' ? t('no_group') : group}
                                            </span>
                                            <button onClick={() => handleShareGroup(group, isSmart)} className="ml-2 p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 text-text-secondary-light dark:text-text-secondary-dark" title={t('share_group')}>
                                                <LinkIcon />
                                            </button>
                                        </div>
                                    )
                                })}
                           </div>
                        </div>
                    )}
                </div>
                <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder={t('search_by_name_host')} className="w-full p-2 border border-border-light dark:border-border-dark rounded-md bg-surface-light dark:bg-surface-dark focus:ring-1 focus:ring-primary-light dark:focus:ring-primary-dark" />
            </div>
            
            {/* Configs Table */}
            <div className="flex-1 overflow-auto bg-surface-light dark:bg-surface-dark rounded-lg shadow">
                 <table className="w-full text-sm text-left rtl:text-right text-text-secondary-light dark:text-text-secondary-dark">
                    <thead className="text-xs uppercase bg-background-light dark:bg-gray-800 sticky top-0">
                        <tr>
                            <th scope="col" className="p-4">
                                <div className="flex items-center">
                                    <input ref={selectAllCheckboxRef} onChange={(e) => handleSelectAll(e.target.checked)} id="checkbox-all" type="checkbox" className="w-4 h-4 text-primary-light bg-gray-100 border-gray-300 rounded focus:ring-primary-light dark:focus:ring-primary-dark dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600" />
                                    <label htmlFor="checkbox-all" className="sr-only">checkbox</label>
                                </div>
                            </th>
                            <th scope="col" className="px-6 py-3"></th>
                            <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('name')}>{t('col_name')} {renderSortIcon('name')}</th>
                            <th scope="col" className="px-6 py-3">{t('col_protocol')}</th>
                            <th scope="col" className="px-6 py-3">{t('col_host')}</th>
                            <th scope="col" className="px-6 py-3">{t('col_ip')}</th>
                            <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('country')}>{t('col_country')} {renderSortIcon('country')}</th>
                            <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('latency')}>{t('col_latency')} {renderSortIcon('latency')}</th>
                            <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('speed')}>{t('col_speed')} {renderSortIcon('speed')}</th>
                            <th scope="col" className="px-6 py-3">{t('col_status')}</th>
                            <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('score')}>{t('col_score')} {renderSortIcon('score')}</th>
                             <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('group')}>{t('col_group')} {renderSortIcon('group')}</th>
                            <th scope="col" className="px-6 py-3 cursor-pointer" onClick={() => handleSort('lastTested')}>{t('col_last_tested')} {renderSortIcon('lastTested')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredAndSortedConfigs.length === 0 ? (
                            <tr><td colSpan={13} className="text-center py-8">{t('no_configs_to_display')}</td></tr>
                        ) : filteredAndSortedConfigs.map((config) => (
                            <tr key={config.id} className="border-b border-border-light dark:border-border-dark hover:bg-background-light dark:hover:bg-gray-800">
                                <td className="w-4 p-4">
                                    <div className="flex items-center">
                                        <input id={`checkbox-${config.id}`} type="checkbox" checked={selectedConfigIds.has(config.id)} onChange={(e) => handleSelectConfig(config.id, e.target.checked)} className="w-4 h-4 text-primary-light bg-gray-100 border-gray-300 rounded focus:ring-primary-light dark:focus:ring-primary-dark dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600" />
                                        <label htmlFor={`checkbox-${config.id}`} className="sr-only">checkbox</label>
                                    </div>
                                </td>
                                <td className="px-2 py-4">
                                    <button onClick={() => setQrModalConfig(config)} title={t('show_qr_code')} className="p-1 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700">
                                        <QrCodeIcon />
                                    </button>
                                </td>
                                <td className="px-6 py-4 font-medium text-text-primary-light dark:text-text-primary-dark whitespace-nowrap truncate max-w-xs">{config.name}</td>
                                <td className="px-6 py-4">{config.protocol}</td>
                                <td className="px-6 py-4 truncate max-w-xs">{config.host}:{config.port}</td>
                                <td className="px-6 py-4">{config.ip}</td>
                                <td className="px-6 py-4">{COUNTRIES[config.countryCode]?.flag || '🏳️'} {config.country}</td>
                                <td className="px-6 py-4 flex items-center space-x-2 rtl:space-x-reverse">
                                    <span>{config.latency > -1 ? `${config.latency}ms` : 'N/A'}</span>
                                    <Sparkline data={config.latencyHistory} />
                                </td>
                                <td className="px-6 py-4">{config.speed > 0 ? `${config.speed.toFixed(1)} KB/s` : 'N/A'}</td>
                                <td className="px-6 py-4">
                                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusClass(config.status)}`}>
                                        {config.status === Status.Testing ? t('testing') : t(config.status.toLowerCase())}
                                    </span>
                                </td>
                                <td className="px-6 py-4">{config.score}</td>
                                <td className="px-6 py-4">
                                    <div className="flex flex-wrap gap-1">
                                      {config.group && <span className="px-2 py-1 text-xs rounded-full bg-gray-200 dark:bg-gray-700">{config.group}</span>}
                                      {(config as any).smartGroups?.map((sgName: string) => {
                                        const sg = settings.smartGroups.find(g => g.name === sgName);
                                        return sg ? <span key={sg.id} style={{backgroundColor: sg.color + '33', color: sg.color, borderColor: sg.color}} className="px-2 py-1 text-xs rounded-full border">{sg.name}</span> : null
                                      })}
                                    </div>
                                </td>
                                <td className="px-6 py-4">{config.lastTested}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default ConfigManager;