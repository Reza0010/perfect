import React, { useState, useEffect } from 'react';
import { LANGUAGES } from '../constants';
import { SettingsData, Subscription, ProxyConfig, SmartGroup, Rule, RuleField, RuleOperator } from '../types';
import { v4 as uuidv4 } from 'uuid';
import { PlusIcon, TrashIcon, DownloadIcon, UploadIcon, MagicWandIcon } from './Icons';
import Modal from './Modal';


interface SettingsProps {
  t: (key: string) => string;
  settings: SettingsData;
  onSave: (newSettings: SettingsData) => void;
  // For data import/export
  configs: ProxyConfig[];
  onImport: (settings: SettingsData, configs: ProxyConfig[]) => void;
}

const Settings: React.FC<SettingsProps> = ({ t, settings, onSave, configs, onImport }) => {
  const [localSettings, setLocalSettings] = useState<SettingsData>(settings);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [isSubModalOpen, setIsSubModalOpen] = useState(false);
  const [isSmartGroupModalOpen, setIsSmartGroupModalOpen] = useState(false);
  const [editingSub, setEditingSub] = useState<Subscription | null>(null);
  const [editingSmartGroup, setEditingSmartGroup] = useState<SmartGroup | null>(null);

  const importFileInputRef = React.useRef<HTMLInputElement>(null);


  useEffect(() => {
    setLocalSettings(settings);
  }, [settings]);

  const handleSave = () => {
    onSave(localSettings);
    setShowConfirmation(true);
    setTimeout(() => setShowConfirmation(false), 2000);
  };
  
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
        const { checked } = e.target as HTMLInputElement;
        setLocalSettings(prev => ({ ...prev, [name]: checked }));
    } else {
        const isNumeric = ['timeout', 'concurrentTests', 'autoTestInterval'].includes(name);
        setLocalSettings(prev => ({...prev, [name]: isNumeric ? Number(value) : value}));
    }
  };

  const handleExport = () => {
    const dataToExport = JSON.stringify({ settings, configs }, null, 2);
    const blob = new Blob([dataToExport], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const today = new Date().toISOString().slice(0, 10);
    link.download = `proxy-tester-backup-${today}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleImportClick = () => {
    importFileInputRef.current?.click();
  };
  
  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
        if (!window.confirm(t('import_confirmation'))) return;
        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const data = JSON.parse(event.target?.result as string);
                if (data.settings && Array.isArray(data.configs)) {
                    onImport(data.settings, data.configs);
                    alert(t('import_success'));
                } else {
                    throw new Error('Invalid file structure');
                }
            } catch (error) {
                alert(t('import_error'));
                console.error("Import failed:", error);
            }
        };
        reader.readAsText(file);
    }
    // Reset file input
    if(importFileInputRef.current) importFileInputRef.current.value = "";
  };
  
  const handleOpenSubModal = (sub: Subscription | null) => {
    setEditingSub(sub || { id: uuidv4(), name: '', url: '', enabled: true });
    setIsSubModalOpen(true);
  };
  
  const handleSaveSubscription = () => {
    if (!editingSub || !editingSub.name || !editingSub.url) return;
    const subs = localSettings.subscriptions || [];
    const existingIndex = subs.findIndex(s => s.id === editingSub.id);
    if (existingIndex > -1) {
        subs[existingIndex] = editingSub;
    } else {
        subs.push(editingSub);
    }
    setLocalSettings(prev => ({...prev, subscriptions: subs}));
    setIsSubModalOpen(false);
  };
  
  const handleDeleteSubscription = (id: string) => {
    setLocalSettings(prev => ({
        ...prev,
        subscriptions: (prev.subscriptions || []).filter(s => s.id !== id)
    }));
  };
  
  const handleOpenSmartGroupModal = (group: SmartGroup | null) => {
    setEditingSmartGroup(group || { id: uuidv4(), name: '', color: '#4f46e5', rules: [] });
    setIsSmartGroupModalOpen(true);
  };
  
  const handleSaveSmartGroup = () => {
      if (!editingSmartGroup || !editingSmartGroup.name) return;
      const groups = localSettings.smartGroups || [];
      const existingIndex = groups.findIndex(g => g.id === editingSmartGroup.id);
      if (existingIndex > -1) {
          groups[existingIndex] = editingSmartGroup;
      } else {
          groups.push(editingSmartGroup);
      }
      setLocalSettings(prev => ({ ...prev, smartGroups: groups }));
      setIsSmartGroupModalOpen(false);
  };
  
  const handleDeleteSmartGroup = (id: string) => {
      setLocalSettings(prev => ({
          ...prev,
          smartGroups: (prev.smartGroups || []).filter(g => g.id !== id)
      }));
  };
  
  const handleRuleChange = (ruleId: string, field: keyof Rule, value: any) => {
      if (!editingSmartGroup) return;
      setEditingSmartGroup({
          ...editingSmartGroup,
          rules: editingSmartGroup.rules.map(r => r.id === ruleId ? { ...r, [field]: value } : r)
      });
  };
  
  const handleAddRule = () => {
      if (!editingSmartGroup) return;
      const newRule: Rule = { id: uuidv4(), field: 'latency', operator: 'less_than', value: 300 };
      setEditingSmartGroup({
          ...editingSmartGroup,
          rules: [...editingSmartGroup.rules, newRule]
      });
  };

  const handleDeleteRule = (ruleId: string) => {
    if (!editingSmartGroup) return;
    setEditingSmartGroup({
      ...editingSmartGroup,
      rules: editingSmartGroup.rules.filter(r => r.id !== ruleId)
    });
  };
  
  const ruleFields: RuleField[] = ['name', 'protocol', 'host', 'country', 'latency', 'score', 'speed', 'group', 'rawConfig'];
  const ruleOperators: RuleOperator[] = ['contains', 'not_contains', 'equals', 'not_equals', 'greater_than', 'less_than'];


  return (
    <div className="p-4 md:p-6">
      <h1 className="text-3xl font-bold mb-6 text-text-primary-light dark:text-text-primary-dark">{t('settings_title')}</h1>
      <div className="max-w-xl mx-auto bg-gradient-to-br from-surface-light to-background-light dark:from-surface-dark dark:to-background-dark p-8 rounded-lg shadow-md border border-border-light dark:border-border-dark space-y-6">
        
        <div>
          <label htmlFor="language" className="block text-sm font-medium text-text-primary-light dark:text-text-primary-dark">{t('language')}</label>
          <select id="language" name="language" value={localSettings.language} onChange={handleInputChange} className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-light dark:border-border-dark focus:outline-none focus:ring-primary-light focus:border-primary-light sm:text-sm rounded-md bg-background-light dark:bg-gray-800 text-text-primary-light dark:text-text-primary-dark">
            {Object.entries(LANGUAGES).map(([code, name]) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
        </div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div>
              <label htmlFor="timeout" className="block text-sm font-medium text-text-primary-light dark:text-text-primary-dark">{t('test_timeout')}</label>
              <input type="number" name="timeout" id="timeout" value={localSettings.timeout} onChange={handleInputChange} className="mt-1 block w-full pl-3 pr-3 py-2 border border-border-light dark:border-border-dark rounded-md shadow-sm focus:outline-none focus:ring-primary-light focus:border-primary-light sm:text-sm bg-background-light dark:bg-gray-800 text-text-primary-light dark:text-text-primary-dark"/>
            </div>

            <div>
              <label htmlFor="concurrentTests" className="block text-sm font-medium text-text-primary-light dark:text-text-primary-dark">{t('concurrent_tests')}</label>
              <input type="number" name="concurrentTests" id="concurrentTests" min="1" max="20" value={localSettings.concurrentTests} onChange={handleInputChange} className="mt-1 block w-full pl-3 pr-3 py-2 border border-border-light dark:border-border-dark rounded-md shadow-sm focus:outline-none focus:ring-primary-light focus:border-primary-light sm:text-sm bg-background-light dark:bg-gray-800 text-text-primary-light dark:text-text-primary-dark"/>
            </div>
        </div>

        <div>
          <label htmlFor="endpoint" className="block text-sm font-medium text-text-primary-light dark:text-text-primary-dark">{t('test_endpoint')}</label>
          <input type="text" name="endpoint" id="endpoint" value={localSettings.endpoint} onChange={handleInputChange} className="mt-1 block w-full pl-3 pr-3 py-2 border border-border-light dark:border-border-dark rounded-md shadow-sm focus:outline-none focus:ring-primary-light focus:border-primary-light sm:text-sm bg-background-light dark:bg-gray-800 text-text-primary-light dark:text-text-primary-dark"/>
        </div>

        <div className="border-t border-border-light dark:border-border-dark pt-6">
          <h3 className="text-md font-semibold text-text-primary-light dark:text-text-primary-dark mb-4">{t('auto_test_settings')}</h3>
          <div>
            <label htmlFor="autoTestInterval" className="block text-sm font-medium text-text-primary-light dark:text-text-primary-dark">{t('auto_test_interval')}</label>
            <select id="autoTestInterval" name="autoTestInterval" value={localSettings.autoTestInterval} onChange={handleInputChange} className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-border-light dark:border-border-dark focus:outline-none focus:ring-primary-light focus:border-primary-light sm:text-sm rounded-md bg-background-light dark:bg-gray-800 text-text-primary-light dark:text-text-primary-dark">
              <option value="0">{t('disabled')}</option>
              <option value="5">5 {t('minutes')}</option>
              <option value="15">15 {t('minutes')}</option>
              <option value="30">30 {t('minutes')}</option>
              <option value="60">60 {t('minutes')}</option>
            </select>
          </div>
          <div className="flex items-center mt-4">
            <input
              id="autoTestOnlyInactive"
              name="autoTestOnlyInactive"
              type="checkbox"
              checked={localSettings.autoTestOnlyInactive}
              onChange={handleInputChange}
              className="h-4 w-4 rounded border-gray-300 text-primary-light focus:ring-primary-light dark:bg-gray-800 dark:border-border-dark"
            />
            <label htmlFor="autoTestOnlyInactive" className="ml-2 rtl:mr-2 block text-sm text-text-primary-light dark:text-text-primary-dark">
              {t('auto_test_only_inactive')}
            </label>
          </div>
        </div>
        
        {/* Smart Groups */}
        <div className="border-t border-border-light dark:border-border-dark pt-6">
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-md font-semibold text-text-primary-light dark:text-text-primary-dark flex items-center"><MagicWandIcon /> <span className="ml-2 rtl:mr-2">{t('smart_groups')}</span></h3>
                <button onClick={() => handleOpenSmartGroupModal(null)} className="flex items-center text-sm text-primary-light dark:text-primary-dark font-semibold"><PlusIcon /> {t('add_smart_group')}</button>
            </div>
            <div className="space-y-2">
                {(localSettings.smartGroups || []).map(group => (
                    <div key={group.id} className="flex items-center justify-between p-2 bg-background-light dark:bg-gray-800 rounded-md">
                         <span className="font-medium truncate flex items-center cursor-pointer" onClick={() => handleOpenSmartGroupModal(group)}>
                            <span className="w-3 h-3 rounded-full mr-2 rtl:ml-2" style={{ backgroundColor: group.color }}></span>
                            {group.name}
                         </span>
                        <button onClick={() => handleDeleteSmartGroup(group.id)} className="p-1 text-red-500 hover:bg-red-500/10 rounded-full"><TrashIcon className="h-5 w-5" /></button>
                    </div>
                ))}
            </div>
        </div>

        {/* Subscriptions */}
        <div className="border-t border-border-light dark:border-border-dark pt-6">
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-md font-semibold text-text-primary-light dark:text-text-primary-dark">{t('subscriptions')}</h3>
                <button onClick={() => handleOpenSubModal(null)} className="flex items-center text-sm text-primary-light dark:text-primary-dark font-semibold"><PlusIcon /> {t('add_subscription')}</button>
            </div>
            <div className="space-y-2">
                {(localSettings.subscriptions || []).map(sub => (
                    <div key={sub.id} className="flex items-center justify-between p-2 bg-background-light dark:bg-gray-800 rounded-md">
                        <span className="font-medium truncate cursor-pointer" onClick={() => handleOpenSubModal(sub)}>{sub.name}</span>
                        <button onClick={() => handleDeleteSubscription(sub.id)} className="p-1 text-red-500 hover:bg-red-500/10 rounded-full"><TrashIcon className="h-5 w-5" /></button>
                    </div>
                ))}
            </div>
        </div>

        {/* Data Management */}
        <div className="border-t border-border-light dark:border-border-dark pt-6">
            <h3 className="text-md font-semibold text-text-primary-light dark:text-text-primary-dark mb-4">{t('data_management')}</h3>
            <div className="flex space-x-2 rtl:space-x-reverse">
                <button onClick={handleExport} className="flex-1 flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">
                    <DownloadIcon /> {t('export_data')}
                </button>
                <input type="file" ref={importFileInputRef} onChange={handleImportFile} accept=".json" className="hidden"/>
                <button onClick={handleImportClick} className="flex-1 flex items-center justify-center px-4 py-2 border border-border-light dark:border-border-dark rounded-md shadow-sm text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700">
                    <UploadIcon /> {t('import_data')}
                </button>
            </div>
        </div>
        
        <div className="relative pt-4">
          <button onClick={handleSave} className="w-full bg-primary-light dark:bg-primary-dark text-white font-bold py-2 px-4 rounded hover:opacity-90 transition-opacity">
            {t('save_settings')}
          </button>
          {showConfirmation && (
            <div className="absolute -bottom-8 left-0 right-0 text-center text-sm text-green-600 dark:text-green-400">
                {t('settings_saved')}
            </div>
          )}
        </div>
      </div>

       <Modal isOpen={isSubModalOpen} onClose={() => setIsSubModalOpen(false)} title={editingSub?.id && (localSettings.subscriptions || []).some(s => s.id === editingSub.id) ? t('edit_subscription') : t('add_subscription')}>
         {editingSub && (
            <div className="space-y-4">
                <div>
                    <label htmlFor="subName" className="block text-sm font-medium">{t('subscription_name')}</label>
                    <input type="text" id="subName" value={editingSub.name} onChange={e => setEditingSub({...editingSub, name: e.target.value})} className="mt-1 w-full p-2 border rounded-md bg-background-light dark:bg-gray-800" />
                </div>
                <div>
                    <label htmlFor="subUrl" className="block text-sm font-medium">{t('subscription_url')}</label>
                    <input type="text" id="subUrl" value={editingSub.url} onChange={e => setEditingSub({...editingSub, url: e.target.value})} className="mt-1 w-full p-2 border rounded-md bg-background-light dark:bg-gray-800" />
                </div>
                 <div className="flex items-center">
                    <input id="subEnabled" type="checkbox" checked={editingSub.enabled} onChange={e => setEditingSub({...editingSub, enabled: e.target.checked})} className="h-4 w-4 rounded" />
                    <label htmlFor="subEnabled" className="ml-2 rtl:mr-2 text-sm">{t('enabled')}</label>
                 </div>
                <button onClick={handleSaveSubscription} className="w-full bg-primary-light dark:bg-primary-dark text-white py-2 rounded-md">{t('save')}</button>
            </div>
         )}
       </Modal>
       
       <Modal isOpen={isSmartGroupModalOpen} onClose={() => setIsSmartGroupModalOpen(false)} title={editingSmartGroup?.id && (localSettings.smartGroups || []).some(g => g.id === editingSmartGroup.id) ? t('edit_smart_group') : t('add_smart_group')}>
         {editingSmartGroup && (
            <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                    <div className="col-span-2">
                        <label htmlFor="sgName" className="block text-sm font-medium">{t('group_name')}</label>
                        <input type="text" id="sgName" value={editingSmartGroup.name} onChange={e => setEditingSmartGroup({...editingSmartGroup, name: e.target.value})} className="mt-1 w-full p-2 border rounded-md bg-background-light dark:bg-gray-800" />
                    </div>
                    <div>
                        <label htmlFor="sgColor" className="block text-sm font-medium">{t('group_color')}</label>
                        <input type="color" id="sgColor" value={editingSmartGroup.color} onChange={e => setEditingSmartGroup({...editingSmartGroup, color: e.target.value})} className="mt-1 w-full p-1 h-10 border rounded-md bg-background-light dark:bg-gray-800" />
                    </div>
                </div>
                <div>
                    <div className="flex justify-between items-center mb-2">
                        <label className="block text-sm font-medium">{t('rules')}</label>
                        <button onClick={handleAddRule} className="text-sm text-primary-light dark:text-primary-dark font-semibold">{t('add_rule')}</button>
                    </div>
                    <p className="text-xs text-text-secondary-light dark:text-text-secondary-dark mb-2">{t('all_rules_must_match')}</p>
                    <div className="space-y-2 max-h-60 overflow-y-auto p-2 border rounded-md bg-background-light dark:bg-gray-800">
                      {editingSmartGroup.rules.map(rule => (
                        <div key={rule.id} className="grid grid-cols-1 md:grid-cols-4 gap-2 items-center">
                          <select value={rule.field} onChange={e => handleRuleChange(rule.id, 'field', e.target.value)} className="w-full p-1.5 border rounded-md text-sm bg-surface-light dark:bg-gray-700">
                            {ruleFields.map(f => <option key={f} value={f}>{t(f) || f}</option>)}
                          </select>
                          <select value={rule.operator} onChange={e => handleRuleChange(rule.id, 'operator', e.target.value)} className="w-full p-1.5 border rounded-md text-sm bg-surface-light dark:bg-gray-700">
                            {ruleOperators.map(o => <option key={o} value={o}>{t(o)}</option>)}
                          </select>
                          <input type={['latency', 'score', 'speed'].includes(rule.field) ? 'number' : 'text'} value={rule.value} onChange={e => handleRuleChange(rule.id, 'value', e.target.value)} className="w-full p-1.5 border rounded-md text-sm col-span-2 md:col-span-1 bg-surface-light dark:bg-gray-700" />
                          <button onClick={() => handleDeleteRule(rule.id)} className="p-1 text-red-500 hover:bg-red-500/10 rounded-full justify-self-end">
                            <TrashIcon className="h-5 w-5" />
                          </button>
                        </div>
                      ))}
                    </div>
                </div>
                <button onClick={handleSaveSmartGroup} className="w-full bg-primary-light dark:bg-primary-dark text-white py-2 rounded-md">{t('save')}</button>
            </div>
         )}
       </Modal>
    </div>
  );
};

export default Settings;