// FIX: Import React to make the JSX namespace available for type definitions.
import React from 'react';

export enum Protocol {
  Vmess = 'Vmess',
  Vless = 'Vless',
  Shadowsocks = 'Shadowsocks',
  Trojan = 'Trojan',
  Hidify = 'Hidify',
  Unknown = 'Unknown',
}

export enum Status {
  Active = 'Active',
  Slow = 'Slow',
  Inactive = 'Inactive',
  Testing = 'Testing',
  Untested = 'Untested',
}

export interface ProxyConfig {
  id: string;
  name: string;
  protocol: Protocol;
  host: string;
  port: number;
  ip: string;
  country: string;
  countryCode: string;
  latency: number; // in ms
  status: Status;
  score: number;
  lastTested: string;
  rawConfig: string;
  latencyHistory: number[];
  group?: string;
  speed: number; // in KB/s
}

export interface Subscription {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
}

export type RuleField = 'name' | 'protocol' | 'host' | 'country' | 'latency' | 'score' | 'speed' | 'group' | 'rawConfig';
export type RuleOperator = 'contains' | 'not_contains' | 'equals' | 'not_equals' | 'greater_than' | 'less_than';

export interface Rule {
  id: string;
  field: RuleField;
  operator: RuleOperator;
  value: string | number;
}

export interface SmartGroup {
  id: string;
  name: string;
  color: string;
  rules: Rule[]; // All rules must match (AND logic)
}

export interface SettingsData {
  timeout: number;
  concurrentTests: number;
  endpoint: string;
  language: 'en' | 'fa';
  theme: 'light' | 'dark';
  autoTestInterval: number; // in minutes, 0 for disabled
  autoTestOnlyInactive: boolean;
  subscriptions: Subscription[];
  smartGroups: SmartGroup[];
}

// FIX: Add 'name' to allow sorting by config name. This resolves the error in ConfigManager.tsx.
export type SortKey = 'name' | 'latency' | 'country' | 'score' | 'lastTested' | 'speed' | 'group';
export type SortDirection = 'asc' | 'desc';

export interface Page {
  id: 'dashboard' | 'configs' | 'settings';
  name: string;
  // FIX: Changed JSX.Element to React.ReactElement to avoid issues with the JSX namespace in .ts files.
  icon: React.ReactElement;
}
