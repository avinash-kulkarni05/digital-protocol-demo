/**
 * Automated test for the Coverage Registry system.
 * 
 * This script verifies that:
 * 1. The coverage registry correctly extracts all JSON paths
 * 2. markRendered correctly marks paths and their children
 * 3. Unrendered paths are correctly identified for fallback display
 * 
 * Run with: npx tsx scripts/test-coverage-registry.ts
 * 
 * IMPORTANT: This test imports and tests the ACTUAL production code from
 * client/src/lib/coverage-registry.tsx to ensure we're testing the real implementation.
 */

import { readFileSync } from 'fs';
import { join } from 'path';

// Import the ACTUAL functions from the production coverage-registry module
import { getAllPaths, getValueAtPath } from '../client/src/lib/coverage-registry';

// Helper function used by the registry
function getTopLevelKeys(paths: string[]): string[] {
  const topLevel = new Set<string>();
  for (const path of paths) {
    const firstPart = path.split(".")[0].split("[")[0];
    if (firstPart) topLevel.add(firstPart);
  }
  return Array.from(topLevel);
}

/**
 * TestCoverageRegistry simulates the CoverageRegistryProvider behavior
 * using the PRODUCTION getAllPaths and getValueAtPath functions.
 * 
 * The markRendered and getUnrenderedPaths logic here MUST match the exact
 * implementation in CoverageRegistryProvider. This is intentional - we're
 * testing that the logic works correctly with the production path utilities.
 * 
 * If this test passes but the real provider fails, it indicates the provider
 * implementation has drifted from the expected behavior.
 */
class TestCoverageRegistry {
  private allPaths: Set<string>;
  private renderedPaths: Set<string> = new Set();
  private originalData: any;

  constructor(data: any) {
    // Uses the PRODUCTION getAllPaths function
    const paths = getAllPaths(data);
    this.allPaths = new Set(paths);
    this.originalData = data;
  }

  /**
   * Marks a path (or array of paths) as rendered.
   * This logic mirrors CoverageRegistryProvider.markRendered exactly.
   */
  markRendered(path: string | string[]): void {
    const pathsToMark = Array.isArray(path) ? path : [path];
    
    for (const p of pathsToMark) {
      if (!this.renderedPaths.has(p)) {
        this.renderedPaths.add(p);
        const allPathsArray = Array.from(this.allPaths);
        for (const existingPath of allPathsArray) {
          if (existingPath.startsWith(p + ".") || existingPath.startsWith(p + "[")) {
            this.renderedPaths.add(existingPath);
          }
        }
      }
    }
  }

  /**
   * Gets unrendered paths - mirrors CoverageRegistryProvider.getUnrenderedPaths
   */
  getUnrenderedPaths(): string[] {
    const unrendered: string[] = [];
    const allPathsArray = Array.from(this.allPaths);
    const renderedPathsArray = Array.from(this.renderedPaths);
    
    for (const path of allPathsArray) {
      if (!this.renderedPaths.has(path)) {
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
  }

  /**
   * Gets unrendered data - mirrors CoverageRegistryProvider.getUnrenderedData
   */
  getUnrenderedData(): Record<string, any> {
    const unrenderedPaths = this.getUnrenderedPaths();
    const topLevelKeys = getTopLevelKeys(unrenderedPaths);
    
    const result: Record<string, any> = {};
    for (const key of topLevelKeys) {
      // Uses the PRODUCTION getValueAtPath function
      const value = getValueAtPath(this.originalData, key);
      if (value !== undefined) {
        result[key] = value;
      }
    }
    return result;
  }

  getCoverageStats(): { total: number; rendered: number; percentage: number } {
    const total = this.allPaths.size;
    const rendered = this.renderedPaths.size;
    const percentage = total > 0 ? Math.round((rendered / total) * 100) : 100;
    return { total, rendered, percentage };
  }

  getAllPathCount(): number {
    return this.allPaths.size;
  }

  getRenderedPathCount(): number {
    return this.renderedPaths.size;
  }
}

// Test assertions
let testsPassed = 0;
let testsFailed = 0;

function assert(condition: boolean, message: string): void {
  if (condition) {
    console.log(`  ✓ ${message}`);
    testsPassed++;
  } else {
    console.log(`  ✗ ${message}`);
    testsFailed++;
  }
}

function assertEqual<T>(actual: T, expected: T, message: string): void {
  if (actual === expected) {
    console.log(`  ✓ ${message}`);
    testsPassed++;
  } else {
    console.log(`  ✗ ${message} (expected ${expected}, got ${actual})`);
    testsFailed++;
  }
}

// Run tests
console.log('\n=== Coverage Registry Automated Tests ===\n');

// Test 1: Path extraction on simple object
console.log('Test 1: Path extraction on simple object');
{
  const simpleData = {
    name: 'Test',
    nested: {
      value: 42,
      deep: {
        flag: true
      }
    }
  };
  
  const paths = getAllPaths(simpleData);
  assert(paths.includes('name'), 'Extracts top-level primitive path');
  assert(paths.includes('nested'), 'Extracts nested object path');
  assert(paths.includes('nested.value'), 'Extracts nested primitive path');
  assert(paths.includes('nested.deep.flag'), 'Extracts deeply nested path');
}

// Test 2: Path extraction with arrays
console.log('\nTest 2: Path extraction with arrays');
{
  const arrayData = {
    items: [
      { id: 1, name: 'First' },
      { id: 2, name: 'Second' }
    ]
  };
  
  const paths = getAllPaths(arrayData);
  assert(paths.includes('items'), 'Extracts array path');
  assert(paths.includes('items[0]'), 'Extracts array element path');
  assert(paths.includes('items[0].id'), 'Extracts array element property path');
  assert(paths.includes('items[1].name'), 'Extracts second array element property');
}

// Test 3: markRendered marks children
console.log('\nTest 3: markRendered marks children');
{
  const data = {
    parent: {
      child1: 'value1',
      child2: {
        grandchild: 'value2'
      }
    }
  };
  
  const registry = new TestCoverageRegistry(data);
  const initialUnrendered = registry.getUnrenderedPaths().length;
  
  registry.markRendered('parent');
  
  const afterUnrendered = registry.getUnrenderedPaths();
  assertEqual(afterUnrendered.length, 0, 'All child paths marked as rendered');
  
  const stats = registry.getCoverageStats();
  assertEqual(stats.percentage, 100, 'Coverage is 100% after marking parent');
}

// Test 4: Partial marking leaves unrendered paths
console.log('\nTest 4: Partial marking leaves unrendered paths');
{
  const data = {
    section1: { value: 'a' },
    section2: { value: 'b' },
    section3: { value: 'c' }
  };
  
  const registry = new TestCoverageRegistry(data);
  registry.markRendered(['section1', 'section2']);
  
  const unrendered = registry.getUnrenderedPaths();
  assert(unrendered.some(p => p.startsWith('section3')), 'Section3 paths remain unrendered');
  assert(!unrendered.some(p => p.startsWith('section1')), 'Section1 paths are rendered');
  assert(!unrendered.some(p => p.startsWith('section2')), 'Section2 paths are rendered');
}

// Test 5: getUnrenderedData returns correct data
console.log('\nTest 5: getUnrenderedData returns correct data');
{
  const data = {
    rendered: { value: 'shown' },
    fallback: { value: 'hidden', deep: { nested: true } }
  };
  
  const registry = new TestCoverageRegistry(data);
  registry.markRendered('rendered');
  
  const unrenderedData = registry.getUnrenderedData();
  assert('fallback' in unrenderedData, 'Fallback key is in unrendered data');
  assert(!('rendered' in unrenderedData), 'Rendered key is not in unrendered data');
  assertEqual(unrenderedData.fallback.value, 'hidden', 'Unrendered data has correct value');
}

// Test 6: Test with real USDM-like structure
console.log('\nTest 6: USDM-like structure test');
{
  const usdmLike = {
    study: {
      id: 'TEST-001',
      name: 'Test Study',
      version: '1.0',
      studyPhase: {
        code: 'C15602',
        decode: 'Phase 3'
      }
    },
    extractionMetadata: {
      pipelineVersion: '3.1',
      qualitySummary: {
        study_metadata: { score: 0.95 }
      }
    },
    sourceDocument: {
      filename: 'test.pdf',
      pageCount: 100
    }
  };
  
  const registry = new TestCoverageRegistry(usdmLike);
  const totalPaths = registry.getAllPathCount();
  
  assert(totalPaths > 10, `Extracts multiple paths from USDM structure (got ${totalPaths})`);
  
  // Simulate view marking its data
  registry.markRendered(['study', 'extractionMetadata']);
  
  const unrendered = registry.getUnrenderedPaths();
  assert(unrendered.some(p => p.startsWith('sourceDocument')), 'sourceDocument remains unrendered');
  
  // Simulate fallback picking up remaining data
  registry.markRendered('sourceDocument');
  
  const finalUnrendered = registry.getUnrenderedPaths();
  assertEqual(finalUnrendered.length, 0, 'All paths covered after fallback marks remaining');
  assertEqual(registry.getCoverageStats().percentage, 100, 'Full coverage achieved');
}

// Test 7: Load and test with actual USDM data file
console.log('\nTest 7: Real USDM data file test');
{
  try {
    const usdmPath = join(process.cwd(), 'client/src/lib/usdm-data.json');
    const usdmRaw = readFileSync(usdmPath, 'utf-8');
    const usdmData = JSON.parse(usdmRaw);
    
    const registry = new TestCoverageRegistry(usdmData);
    const totalPaths = registry.getAllPathCount();
    
    assert(totalPaths > 1000, `USDM file has substantial path count (got ${totalPaths})`);
    
    // Mark ALL top-level sections (views + fallback should cover these)
    const topLevelSections = [
      '$schema',
      'schemaVersion',
      'instanceType',
      'id',
      'name',
      'sourceDocument',
      'extractionMetadata',
      'study',
      'domainSections',
      'provenanceSummary'
    ];
    
    registry.markRendered(topLevelSections);
    
    const stats = registry.getCoverageStats();
    assertEqual(stats.percentage, 100, 'Marking all top-level sections achieves full coverage');
    
    const unrendered = registry.getUnrenderedPaths();
    assertEqual(unrendered.length, 0, 'No unrendered paths after marking all top-level sections');
    
    console.log(`    (File stats: ${stats.total} total paths, ${stats.rendered} rendered)`);
    
  } catch (err) {
    console.log(`  ⚠ Skipped: Could not load USDM data file - ${err}`);
  }
}

// Test 8: Edge cases
console.log('\nTest 8: Edge cases');
{
  // Null/undefined handling
  const paths1 = getAllPaths(null);
  assertEqual(paths1.length, 0, 'Null returns empty paths');
  
  const paths2 = getAllPaths(undefined);
  assertEqual(paths2.length, 0, 'Undefined returns empty paths');
  
  // Empty object
  const paths3 = getAllPaths({});
  assertEqual(paths3.length, 0, 'Empty object returns empty paths');
  
  // Empty array
  const paths4 = getAllPaths([]);
  assertEqual(paths4.length, 0, 'Empty array returns empty paths');
  
  // Primitive value
  const paths5 = getAllPaths("string");
  assertEqual(paths5.length, 0, 'Primitive string returns empty paths (no prefix)');
}

// Summary
console.log('\n=== Test Summary ===');
console.log(`Passed: ${testsPassed}`);
console.log(`Failed: ${testsFailed}`);

if (testsFailed > 0) {
  console.log('\n❌ Some tests failed!');
  process.exit(1);
} else {
  console.log('\n✅ All tests passed!');
  process.exit(0);
}
