import { getAllPaths, getValueAtPath } from './coverage-registry';

export interface VerificationResult {
  success: boolean;
  totalPaths: number;
  testedPaths: number;
  errors: string[];
  warnings: string[];
}

export function verifyPathExtraction(data: any): VerificationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  
  const paths = getAllPaths(data);
  
  if (paths.length === 0) {
    errors.push('No paths extracted from data');
    return { success: false, totalPaths: 0, testedPaths: 0, errors, warnings };
  }
  
  let testedPaths = 0;
  
  for (const path of paths) {
    const value = getValueAtPath(data, path);
    testedPaths++;
    
    if (value === undefined && path.includes('.')) {
      warnings.push(`Path "${path}" resolved to undefined`);
    }
  }
  
  const samplePaths = [
    'study',
    'study.name',
    'extractionMetadata',
    'sourceDocument',
  ];
  
  for (const samplePath of samplePaths) {
    const value = getValueAtPath(data, samplePath);
    if (value === undefined) {
      warnings.push(`Expected path "${samplePath}" not found in data`);
    }
  }
  
  return {
    success: errors.length === 0,
    totalPaths: paths.length,
    testedPaths,
    errors,
    warnings
  };
}

export function simulateCoverageTracking(data: any, renderedPaths: string[]): {
  allPaths: Set<string>;
  renderedPaths: Set<string>;
  unrenderedPaths: string[];
  coveragePercentage: number;
} {
  const allPathsArray = getAllPaths(data);
  const allPathsSet = new Set(allPathsArray);
  const renderedSet = new Set<string>();
  
  for (const rendered of renderedPaths) {
    renderedSet.add(rendered);
    for (const existingPath of allPathsArray) {
      if (existingPath.startsWith(rendered + '.') || existingPath.startsWith(rendered + '[')) {
        renderedSet.add(existingPath);
      }
    }
  }
  
  const unrendered: string[] = [];
  for (const path of allPathsArray) {
    if (!renderedSet.has(path)) {
      let isChildOfRendered = false;
      for (const rp of Array.from(renderedSet)) {
        if (path.startsWith(rp + '.') || path.startsWith(rp + '[')) {
          isChildOfRendered = true;
          break;
        }
      }
      if (!isChildOfRendered) {
        unrendered.push(path);
      }
    }
  }
  
  const percentage = allPathsSet.size > 0 
    ? Math.round((renderedSet.size / allPathsSet.size) * 100) 
    : 100;
  
  return {
    allPaths: allPathsSet,
    renderedPaths: renderedSet,
    unrenderedPaths: unrendered,
    coveragePercentage: percentage
  };
}

export function runCoverageVerification(usdmData: any): void {
  console.log('=== Coverage Registry Verification ===\n');
  
  const extractionResult = verifyPathExtraction(usdmData);
  console.log(`Path Extraction: ${extractionResult.success ? 'PASSED' : 'FAILED'}`);
  console.log(`  Total paths found: ${extractionResult.totalPaths}`);
  console.log(`  Paths tested: ${extractionResult.testedPaths}`);
  
  if (extractionResult.errors.length > 0) {
    console.log(`  Errors:`);
    extractionResult.errors.forEach(e => console.log(`    - ${e}`));
  }
  
  if (extractionResult.warnings.length > 0 && extractionResult.warnings.length <= 5) {
    console.log(`  Warnings:`);
    extractionResult.warnings.forEach(w => console.log(`    - ${w}`));
  } else if (extractionResult.warnings.length > 5) {
    console.log(`  Warnings: ${extractionResult.warnings.length} total (showing first 5)`);
    extractionResult.warnings.slice(0, 5).forEach(w => console.log(`    - ${w}`));
  }
  
  console.log('\n--- Simulating Coverage Scenarios ---\n');
  
  const topLevelPaths = ['study', 'extractionMetadata', 'sourceDocument', '$schema', 'schemaVersion', 'instanceType', 'id', 'name'];
  const simulationResult = simulateCoverageTracking(usdmData, topLevelPaths);
  
  console.log(`Simulation with top-level paths marked:`);
  console.log(`  All paths: ${simulationResult.allPaths.size}`);
  console.log(`  Rendered paths: ${simulationResult.renderedPaths.size}`);
  console.log(`  Unrendered paths: ${simulationResult.unrenderedPaths.length}`);
  console.log(`  Coverage: ${simulationResult.coveragePercentage}%`);
  
  if (simulationResult.unrenderedPaths.length > 0 && simulationResult.unrenderedPaths.length <= 10) {
    console.log(`  Unrendered:`);
    simulationResult.unrenderedPaths.forEach(p => console.log(`    - ${p}`));
  } else if (simulationResult.unrenderedPaths.length > 10) {
    console.log(`  Unrendered: ${simulationResult.unrenderedPaths.length} total (showing first 10)`);
    simulationResult.unrenderedPaths.slice(0, 10).forEach(p => console.log(`    - ${p}`));
  }
  
  const fullCoverageResult = simulateCoverageTracking(usdmData, Array.from(simulationResult.allPaths));
  console.log(`\nFull coverage simulation:`);
  console.log(`  Coverage: ${fullCoverageResult.coveragePercentage}%`);
  console.log(`  Unrendered: ${fullCoverageResult.unrenderedPaths.length}`);
  
  console.log('\n=== Verification Complete ===');
}
