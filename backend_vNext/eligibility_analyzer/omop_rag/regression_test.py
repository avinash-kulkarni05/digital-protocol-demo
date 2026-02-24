"""
Regression Test for OMOP RAG Mapping

Compares RAG-based mappings against known problematic mappings from
previous protocol extractions to verify bugs are fixed.

Test Cases:
1. NCT02203851 - "Patient is female" should map to FEMALE (8532), not "Baby female" (4015271)
2. NCT04983589 - "Sex is female" -> FEMALE (8532), "Sex is male" -> MALE (8507)

Usage:
    # Standalone CLI runner (with colored output and JSON report)
    python -m eligibility_analyzer.omop_rag.regression_test

    # Save JSON report
    python -m eligibility_analyzer.omop_rag.regression_test --report

    # Pytest runner (preferred for CI/CD)
    python -m pytest eligibility_analyzer/omop_rag/tests/test_rag_regression.py -v
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Known problematic mappings from previous extractions
KNOWN_BUGS = {
    "NCT02203851": [
        {
            "term": "Patient is female",
            "wrong_concept_id": 4015271,
            "wrong_concept_name": "Baby female",
            "correct_concept_id": 8532,
            "correct_concept_name": "FEMALE",
            "domain": "Gender",
        },
    ],
    "NCT04983589": [
        {
            "term": "Sex is female",
            "wrong_concept_id": 4015271,
            "wrong_concept_name": "Baby female",
            "correct_concept_id": 8532,
            "correct_concept_name": "FEMALE",
            "domain": "Gender",
        },
        {
            "term": "Sex is male",
            "wrong_concept_id": 4139950,  # Maleo (bird)
            "wrong_concept_name": "Maleo",
            "correct_concept_id": 8507,
            "correct_concept_name": "MALE",
            "domain": "Gender",
        },
    ],
}

# Additional demographic test cases
DEMOGRAPHIC_TESTS = [
    {"term": "female", "expected_id": 8532, "expected_name": "FEMALE"},
    {"term": "male", "expected_id": 8507, "expected_name": "MALE"},
    {"term": "woman", "expected_id": 8532, "expected_name": "FEMALE"},
    {"term": "men", "expected_id": 8507, "expected_name": "MALE"},
    {"term": "Patient is a male", "expected_id": 8507, "expected_name": "MALE"},
    {"term": "Female patient", "expected_id": 8532, "expected_name": "FEMALE"},
    {"term": "White", "expected_id": 8527, "expected_name": "White"},
    {"term": "Black or African American", "expected_id": 8516, "expected_name": "Black or African American"},
    {"term": "Asian", "expected_id": 8515, "expected_name": "Asian"},
    {"term": "Hispanic", "expected_id": 38003563, "expected_name": "Hispanic or Latino"},
    {"term": "Non-Hispanic", "expected_id": 38003564, "expected_name": "Not Hispanic or Latino"},
]

# Clinical term tests
CLINICAL_TESTS = [
    {"term": "diabetes mellitus", "expected_id": 201820, "expected_name": "Diabetes mellitus"},
    {"term": "type 2 diabetes", "expected_id": 201826, "expected_name": "Type 2 diabetes mellitus"},
    {"term": "hypertension", "expected_id": 316866, "expected_name": "Hypertensive disorder"},
    {"term": "breast cancer", "expected_id": 4112853, "expected_name": "Malignant tumor of breast"},
]

# Edge case tests
EDGE_CASE_TESTS = [
    {"term": "", "should_map": False, "description": "empty string"},
    {"term": "   ", "should_map": False, "description": "whitespace only"},
    {"term": "xyzzy_nonexistent_12345", "should_map": False, "description": "nonsense term"},
    {"term": "FEMALE", "expected_id": 8532, "should_map": True, "description": "uppercase FEMALE"},
    {"term": "Female", "expected_id": 8532, "should_map": True, "description": "title case Female"},
]


async def run_known_bugs_test(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test that known bugs are fixed."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 1: Known Bug Fixes")
    print("=" * 70)

    for protocol_id, bugs in KNOWN_BUGS.items():
        print(f"\n  Protocol: {protocol_id}")
        print("-" * 50)

        for bug in bugs:
            term = bug["term"]
            start = time.time()
            result = await mapper.map_term(term, bug.get("domain"))
            elapsed_ms = (time.time() - start) * 1000

            test_passed = result.is_mapped and result.concept_id == bug["correct_concept_id"]
            detail = {
                "test": "known_bug",
                "protocol": protocol_id,
                "term": term,
                "expected_id": bug["correct_concept_id"],
                "expected_name": bug["correct_concept_name"],
                "actual_id": result.concept_id,
                "actual_name": result.concept_name,
                "source": result.source,
                "confidence": result.confidence,
                "elapsed_ms": round(elapsed_ms, 1),
                "passed": test_passed,
            }
            details.append(detail)

            if test_passed:
                passed += 1
                print(f"  [PASS] '{term}'")
                print(f"         -> {result.concept_name} (ID: {result.concept_id})")
                print(f"         Previously was: {bug['wrong_concept_name']} (ID: {bug['wrong_concept_id']})")
            else:
                failed += 1
                actual = f"{result.concept_name} ({result.concept_id})" if result.is_mapped else "UNMAPPED"
                print(f"  [FAIL] '{term}'")
                print(f"         Expected: {bug['correct_concept_name']} (ID: {bug['correct_concept_id']})")
                print(f"         Got: {actual}")

    return passed, failed, details


async def run_demographic_tests(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test demographic term mappings."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 2: Demographic Terms")
    print("=" * 70)

    for test in DEMOGRAPHIC_TESTS:
        term = test["term"]
        start = time.time()
        result = await mapper.map_term(term)
        elapsed_ms = (time.time() - start) * 1000

        test_passed = result.is_mapped and result.concept_id == test["expected_id"]
        detail = {
            "test": "demographic",
            "term": term,
            "expected_id": test["expected_id"],
            "expected_name": test["expected_name"],
            "actual_id": result.concept_id,
            "actual_name": result.concept_name,
            "source": result.source,
            "confidence": result.confidence,
            "elapsed_ms": round(elapsed_ms, 1),
            "passed": test_passed,
        }
        details.append(detail)

        if test_passed:
            passed += 1
            print(f"  [PASS] '{term}' -> {result.concept_name} (ID: {result.concept_id}) [{result.source}]")
        else:
            failed += 1
            actual = f"{result.concept_name} ({result.concept_id})" if result.is_mapped else "UNMAPPED"
            print(f"  [FAIL] '{term}'")
            print(f"         Expected: {test['expected_name']} (ID: {test['expected_id']})")
            print(f"         Got: {actual}")

    return passed, failed, details


async def run_clinical_tests(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test clinical term mappings."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 3: Clinical Terms")
    print("=" * 70)

    for test in CLINICAL_TESTS:
        term = test["term"]
        start = time.time()
        result = await mapper.map_term(term, "Condition")
        elapsed_ms = (time.time() - start) * 1000

        test_passed = result.is_mapped and result.concept_id == test["expected_id"]
        detail = {
            "test": "clinical",
            "term": term,
            "expected_id": test["expected_id"],
            "expected_name": test["expected_name"],
            "actual_id": result.concept_id,
            "actual_name": result.concept_name,
            "source": result.source,
            "confidence": result.confidence,
            "elapsed_ms": round(elapsed_ms, 1),
            "passed": test_passed,
        }
        details.append(detail)

        if test_passed:
            passed += 1
            print(f"  [PASS] '{term}' -> {result.concept_name} (ID: {result.concept_id}) [{result.source}]")
        else:
            failed += 1
            actual = f"{result.concept_name} ({result.concept_id})" if result.is_mapped else "UNMAPPED"
            print(f"  [FAIL] '{term}'")
            print(f"         Expected: {test['expected_name']} (ID: {test['expected_id']})")
            print(f"         Got: {actual}")

    return passed, failed, details


async def run_cache_test(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test that caching works correctly."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 4: Caching")
    print("=" * 70)

    # Map same term twice
    term = "Patient is female"
    result1 = await mapper.map_term(term)
    result2 = await mapper.map_term(term)

    # Second call should return same result (cached)
    test_passed = result1.concept_id == result2.concept_id
    details.append({
        "test": "cache_consistency",
        "term": term,
        "first_id": result1.concept_id,
        "second_id": result2.concept_id,
        "first_ms": round(result1.processing_time_ms, 1),
        "second_ms": round(result2.processing_time_ms, 1),
        "passed": test_passed,
    })

    if test_passed:
        passed += 1
        print(f"  [PASS] Cache returns same result")
        print(f"         First call: {result1.processing_time_ms:.1f}ms")
        print(f"         Second call: {result2.processing_time_ms:.1f}ms")
    else:
        failed += 1
        print(f"  [FAIL] Cache returned different results")

    # Check cache stats
    stats = mapper.get_stats()
    test_passed = stats.get("cache_hits", 0) > 0
    details.append({
        "test": "cache_hits",
        "cache_hits": stats.get("cache_hits", 0),
        "passed": test_passed,
    })

    if test_passed:
        passed += 1
        print(f"  [PASS] Cache hit registered: {stats['cache_hits']} hits")
    else:
        failed += 1
        print(f"  [FAIL] No cache hits registered")

    return passed, failed, details


async def run_batch_test(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test batch processing."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 5: Batch Processing")
    print("=" * 70)

    terms = [
        {"term": "female", "domain_hint": "Gender"},
        {"term": "male", "domain_hint": "Gender"},
        {"term": "diabetes mellitus", "domain_hint": "Condition"},
        {"term": "hypertension", "domain_hint": "Condition"},
        {"term": "breast cancer", "domain_hint": "Condition"},
    ]

    start = time.time()
    results = await mapper.map_terms_batch(terms, max_concurrent=5)
    elapsed = time.time() - start

    # Check count
    count_passed = len(results) == len(terms)
    details.append({
        "test": "batch_count",
        "expected": len(terms),
        "actual": len(results),
        "elapsed_s": round(elapsed, 2),
        "passed": count_passed,
    })

    if count_passed:
        passed += 1
        print(f"  [PASS] Batch returned {len(results)} results for {len(terms)} terms ({elapsed:.2f}s)")
    else:
        failed += 1
        print(f"  [FAIL] Expected {len(terms)} results, got {len(results)}")

    # Check order preserved
    order_passed = (
        len(results) >= 2
        and results[0].term == "female"
        and results[1].term == "male"
    )
    details.append({
        "test": "batch_order",
        "first_term": results[0].term if results else None,
        "second_term": results[1].term if len(results) > 1 else None,
        "passed": order_passed,
    })

    if order_passed:
        passed += 1
        print(f"  [PASS] Batch preserves input order")
    else:
        failed += 1
        print(f"  [FAIL] Batch order not preserved")

    # Check mapped count
    mapped = sum(1 for r in results if r.is_mapped)
    map_passed = mapped == len(terms)
    details.append({
        "test": "batch_mapped",
        "mapped": mapped,
        "total": len(terms),
        "passed": map_passed,
    })

    if map_passed:
        passed += 1
        print(f"  [PASS] All {mapped}/{len(terms)} terms mapped in batch")
    else:
        failed += 1
        unmapped_terms = [r.term for r in results if not r.is_mapped]
        print(f"  [FAIL] Only {mapped}/{len(terms)} mapped. Unmapped: {unmapped_terms}")

    return passed, failed, details


async def run_edge_case_tests(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test edge cases."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 6: Edge Cases")
    print("=" * 70)

    for test in EDGE_CASE_TESTS:
        term = test["term"]
        description = test["description"]
        should_map = test.get("should_map", True)

        try:
            result = await mapper.map_term(term)
            no_error = True
        except Exception as e:
            no_error = False
            result = None

        if not should_map:
            test_passed = no_error and (result is None or not result.is_mapped)
            detail_msg = "correctly unmapped" if test_passed else "unexpected mapping"
        else:
            expected_id = test.get("expected_id")
            test_passed = no_error and result is not None and result.is_mapped
            if expected_id:
                test_passed = test_passed and result.concept_id == expected_id
            detail_msg = f"mapped to {result.concept_id}" if result and result.is_mapped else "unmapped"

        details.append({
            "test": "edge_case",
            "description": description,
            "term": repr(term),
            "should_map": should_map,
            "passed": test_passed,
            "no_error": no_error,
            "detail": detail_msg,
        })

        status = "PASS" if test_passed else "FAIL"
        if test_passed:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {description}: {detail_msg}")

    return passed, failed, details


async def run_performance_test(mapper) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Test performance benchmarks."""
    passed = 0
    failed = 0
    details = []

    print("\n" + "=" * 70)
    print(" TEST 7: Performance Benchmarks")
    print("=" * 70)

    # Benchmark curated mapping (should be fast)
    timings = []
    for _ in range(20):
        start = time.time()
        await mapper.map_term("female", "Gender")
        timings.append((time.time() - start) * 1000)

    avg_ms = sum(timings) / len(timings)
    # Skip first call (cold cache), measure warm cache average
    warm_avg = sum(timings[1:]) / len(timings[1:])
    p95 = sorted(timings)[int(len(timings) * 0.95)]

    curated_passed = warm_avg < 50  # 50ms threshold for curated + cache
    details.append({
        "test": "perf_curated",
        "avg_ms": round(avg_ms, 1),
        "warm_avg_ms": round(warm_avg, 1),
        "p95_ms": round(p95, 1),
        "threshold_ms": 50,
        "passed": curated_passed,
    })

    if curated_passed:
        passed += 1
        print(f"  [PASS] Curated mapping: avg={warm_avg:.1f}ms, p95={p95:.1f}ms (< 50ms)")
    else:
        failed += 1
        print(f"  [FAIL] Curated mapping too slow: avg={warm_avg:.1f}ms (> 50ms)")

    # Benchmark batch throughput
    batch_terms = [
        {"term": "female", "domain_hint": "Gender"},
        {"term": "male", "domain_hint": "Gender"},
        {"term": "diabetes", "domain_hint": "Condition"},
    ] * 10  # 30 terms

    start = time.time()
    batch_results = await mapper.map_terms_batch(batch_terms, max_concurrent=10)
    batch_elapsed = time.time() - start
    throughput = len(batch_terms) / batch_elapsed if batch_elapsed > 0 else 0

    batch_passed = batch_elapsed < 30  # 30s threshold for 30 terms
    details.append({
        "test": "perf_batch",
        "term_count": len(batch_terms),
        "elapsed_s": round(batch_elapsed, 2),
        "throughput_per_s": round(throughput, 1),
        "threshold_s": 30,
        "passed": batch_passed,
    })

    if batch_passed:
        passed += 1
        print(f"  [PASS] Batch 30 terms: {batch_elapsed:.2f}s ({throughput:.1f} terms/s)")
    else:
        failed += 1
        print(f"  [FAIL] Batch too slow: {batch_elapsed:.2f}s for 30 terms (> 30s)")

    return passed, failed, details


def generate_json_report(
    all_details: List[Dict[str, Any]],
    total_passed: int,
    total_failed: int,
    mapper_stats: Dict[str, Any],
    total_duration: float,
) -> Dict[str, Any]:
    """Generate a structured JSON report of all test results."""
    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": total_passed + total_failed,
            "passed": total_passed,
            "failed": total_failed,
            "success_rate": round(total_passed / (total_passed + total_failed) * 100, 1)
            if (total_passed + total_failed) > 0
            else 0,
            "total_duration_s": round(total_duration, 2),
        },
        "mapper_stats": mapper_stats,
        "test_details": all_details,
    }


async def main():
    """Run all regression tests."""
    suite_start = time.time()
    save_report = "--report" in sys.argv

    # Load environment
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    print("\n" + "=" * 70)
    print(" OMOP RAG Mapping - Regression Test Suite")
    print("=" * 70)

    # Initialize mapper
    try:
        from eligibility_analyzer.omop_rag import RAGMapper
        mapper = RAGMapper()
    except Exception as e:
        print(f"\n  [ERROR] Failed to initialize RAGMapper: {e}")
        print("  Ensure ATHENA_DB_PATH and Azure OpenAI credentials are configured.")
        return 1

    all_passed = 0
    all_failed = 0
    all_details = []

    # Test 1: Known bugs
    p, f, d = await run_known_bugs_test(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    # Test 2: Demographics
    p, f, d = await run_demographic_tests(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    # Test 3: Clinical terms
    p, f, d = await run_clinical_tests(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    # Test 4: Caching
    p, f, d = await run_cache_test(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    # Test 5: Batch processing
    p, f, d = await run_batch_test(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    # Test 6: Edge cases
    p, f, d = await run_edge_case_tests(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    # Test 7: Performance
    p, f, d = await run_performance_test(mapper)
    all_passed += p
    all_failed += f
    all_details.extend(d)

    total_duration = time.time() - suite_start

    # Summary
    total = all_passed + all_failed
    success_rate = all_passed / total * 100 if total > 0 else 0

    print("\n" + "=" * 70)
    print(" SUMMARY")
    print("=" * 70)
    print(f"  Total Passed: {all_passed}")
    print(f"  Total Failed: {all_failed}")
    print(f"  Success Rate: {success_rate:.1f}%")
    print(f"  Duration: {total_duration:.2f}s")

    if all_failed > 0:
        print("\n  Failed Tests:")
        for d in all_details:
            if not d.get("passed", True):
                print(f"    - [{d.get('test', '?')}] {d.get('term', d.get('description', '?'))}")

    # Mapper stats
    stats = mapper.get_stats()
    print("\n  RAG Mapper Statistics:")
    for key, value in stats.items():
        if not key.endswith("_rate"):
            print(f"    {key}: {value}")

    print("=" * 70)

    # Save JSON report
    if save_report:
        report = generate_json_report(all_details, all_passed, all_failed, stats, total_duration)
        report_dir = Path(__file__).parent.parent.parent / "tmp"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"omop_rag_regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n  Report saved: {report_path}")

    return 0 if all_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
