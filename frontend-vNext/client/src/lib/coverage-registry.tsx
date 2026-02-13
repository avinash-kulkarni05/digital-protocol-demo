import React, { createContext, useContext, useCallback, useRef, useMemo, useState, useEffect } from "react";

interface CoverageRegistryContextType {
  allPaths: Set<string>;
  renderedPaths: Set<string>;
  markRendered: (path: string | string[]) => void;
  getUnrenderedPaths: () => string[];
  getUnrenderedData: () => Record<string, any>;
  getCoverageStats: () => { total: number; rendered: number; percentage: number };
  originalData: any;
}

const CoverageRegistryContext = createContext<CoverageRegistryContextType | null>(null);

function getAllPaths(obj: any, prefix: string = ""): string[] {
  const paths: string[] = [];
  
  if (obj === null || obj === undefined) {
    return paths;
  }
  
  if (typeof obj !== "object") {
    return [prefix].filter(Boolean);
  }
  
  if (Array.isArray(obj)) {
    if (prefix) paths.push(prefix);
    obj.forEach((item, index) => {
      const itemPaths = getAllPaths(item, `${prefix}[${index}]`);
      paths.push(...itemPaths);
    });
  } else {
    if (prefix) paths.push(prefix);
    for (const key of Object.keys(obj)) {
      const newPath = prefix ? `${prefix}.${key}` : key;
      const childPaths = getAllPaths(obj[key], newPath);
      paths.push(...childPaths);
    }
  }
  
  return paths;
}

function getValueAtPath(obj: any, path: string): any {
  if (!path) return obj;
  
  const parts = path.split(/\.|\[|\]/).filter(Boolean);
  let current = obj;
  
  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    current = current[part];
  }
  
  return current;
}

function getTopLevelKeys(paths: string[]): string[] {
  const topLevel = new Set<string>();
  for (const path of paths) {
    const firstPart = path.split(".")[0].split("[")[0];
    if (firstPart) topLevel.add(firstPart);
  }
  return Array.from(topLevel);
}

interface CoverageRegistryProviderProps {
  data: any;
  children: React.ReactNode;
}

export function CoverageRegistryProvider({ data, children }: CoverageRegistryProviderProps) {
  const allPathsRef = useRef<Set<string>>(new Set());
  const renderedPathsRef = useRef<Set<string>>(new Set());
  const [, forceUpdate] = useState(0);
  
  useEffect(() => {
    const paths = getAllPaths(data);
    allPathsRef.current = new Set(paths);
    renderedPathsRef.current = new Set();
    forceUpdate(n => n + 1);
  }, [data]);

  const markRendered = useCallback((path: string | string[]) => {
    const pathsToMark = Array.isArray(path) ? path : [path];
    let changed = false;
    
    for (const p of pathsToMark) {
      if (!renderedPathsRef.current.has(p)) {
        renderedPathsRef.current.add(p);
        const allPathsArray = Array.from(allPathsRef.current);
        for (const existingPath of allPathsArray) {
          if (existingPath.startsWith(p + ".") || existingPath.startsWith(p + "[")) {
            renderedPathsRef.current.add(existingPath);
          }
        }
        changed = true;
      }
    }
    
    if (changed) {
      forceUpdate(n => n + 1);
    }
  }, []);

  const getUnrenderedPaths = useCallback(() => {
    const unrendered: string[] = [];
    const allPathsArray = Array.from(allPathsRef.current);
    const renderedPathsArray = Array.from(renderedPathsRef.current);
    
    for (const path of allPathsArray) {
      if (!renderedPathsRef.current.has(path)) {
        let isChildOfRendered = false;
        for (const rendered of renderedPathsArray) {
          if (path.startsWith(rendered + ".") || path.startsWith(rendered + "[")) {
            isChildOfRendered = true;
            break;
          }
        }
        if (!isChildOfRendered) {
          unrendered.push(path);
        }
      }
    }
    return unrendered;
  }, []);

  const getUnrenderedData = useCallback(() => {
    const unrenderedPaths = getUnrenderedPaths();
    const topLevelKeys = getTopLevelKeys(unrenderedPaths);
    
    const result: Record<string, any> = {};
    for (const key of topLevelKeys) {
      const value = getValueAtPath(data, key);
      if (value !== undefined) {
        result[key] = value;
      }
    }
    return result;
  }, [data, getUnrenderedPaths]);

  const getCoverageStats = useCallback(() => {
    const total = allPathsRef.current.size;
    const rendered = renderedPathsRef.current.size;
    const percentage = total > 0 ? Math.round((rendered / total) * 100) : 100;
    return { total, rendered, percentage };
  }, []);

  const value = useMemo(() => ({
    allPaths: allPathsRef.current,
    renderedPaths: renderedPathsRef.current,
    markRendered,
    getUnrenderedPaths,
    getUnrenderedData,
    getCoverageStats,
    originalData: data,
  }), [markRendered, getUnrenderedPaths, getUnrenderedData, getCoverageStats, data]);

  return (
    <CoverageRegistryContext.Provider value={value}>
      {children}
    </CoverageRegistryContext.Provider>
  );
}

export function useCoverageRegistry() {
  const context = useContext(CoverageRegistryContext);
  return context;
}

export function useMarkRendered(paths: string | string[]) {
  const registry = useCoverageRegistry();
  
  useEffect(() => {
    if (registry) {
      registry.markRendered(paths);
    }
  }, [registry, paths]);
}

export { getAllPaths, getValueAtPath };
