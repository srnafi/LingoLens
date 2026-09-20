"""LingoLens Pipeline Benchmark

Measures the time for each stage of the OCR→translate→overlay pipeline.
Run this to verify parallelism is working and identify bottlenecks.

Usage:
    .venv/Scripts/python.exe python/benchmark.py

Prerequisites:
    - Flask OCR server running (python/ocr_server.py)
    - OpenVINO model in models/
"""
import sys
import time
import logging
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup path
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from overlay import (
    _wait_for_flask, _run_ocr, _parse_ocr_results,
    _group_words_into_lines, _group_lines_into_paragraphs,
    _estimate_font_size, _paragraph_text,
)
from translator import translate_text

logging.basicConfig(level=logging.INFO,
                    format='[%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('benchmark')

FLASK_URL = "http://localhost:5000"


def benchmark_stage(name, func, *args, **kwargs):
    """Run a function and report its timing."""
    start = time.time()
    result = func(*args, **kwargs)
    elapsed = time.time() - start
    logger.info(f"  {name}: {elapsed*1000:.0f}ms")
    return result, elapsed


def run_benchmark():
    logger.info("=" * 60)
    logger.info("LingoLens Pipeline Benchmark")
    logger.info("=" * 60)

    timings = {}

    # Stage 1: Flask health check
    _, t = benchmark_stage("Flask health check", _wait_for_flask, timeout=10)
    timings['flask_health'] = t

    if not _wait_for_flask(timeout=5):
        logger.error("Flask server not running! Start it first:")
        logger.error("  .venv/Scripts/python.exe python/ocr_server.py")
        return

    # Stage 2: OCR
    crops_folder = str(_this_dir / "crops")
    ocr_results, t = benchmark_stage("OCR (HTTP POST)", _run_ocr, crops_folder)
    timings['ocr'] = t

    if not ocr_results:
        logger.warning("No OCR results. Run a snip first to populate crops/.")
        logger.info("Creating dummy OCR results for grouping/translation benchmark...")
        # Create synthetic OCR results for benchmarking grouping + translation
        ocr_results = {
            "10,100,5,30": "Hello",
            "110,200,5,30": "world",
            "10,80,40,65": "This",
            "90,180,40,65": "is",
            "190,350,40,65": "a",
            "360,500,40,65": "test",
        }
        logger.info(f"  Using {len(ocr_results)} synthetic words")

    # Stage 3: Parse OCR results
    words, t = benchmark_stage("Parse OCR results", _parse_ocr_results, ocr_results)
    timings['parse'] = t

    # Stage 4: Group into lines
    lines, t = benchmark_stage("Group into lines", _group_words_into_lines, words)
    timings['group_lines'] = t

    # Stage 5: Group into paragraphs
    paragraphs, t = benchmark_stage("Group into paragraphs",
                                     _group_lines_into_paragraphs, lines)
    timings['group_paras'] = t

    # Stage 6: Estimate font size
    est_font, t = benchmark_stage("Estimate font size", _estimate_font_size, words)
    timings['font_estimate'] = t
    logger.info(f"  Estimated font size: {est_font}px")

    # Stage 7: Translation — sequential vs parallel comparison
    logger.info("")
    logger.info("--- Translation: SEQUENTIAL ---")
    start = time.time()
    seq_results = {}
    for i, para in enumerate(paragraphs):
        text = _paragraph_text(para)
        seq_results[i] = translate_text(text, 'es')
    seq_time = time.time() - start
    logger.info(f"  Sequential translation: {seq_time*1000:.0f}ms "
                f"({len(paragraphs)} paragraphs)")

    logger.info("")
    logger.info("--- Translation: PARALLEL ---")
    start = time.time()
    par_results = {}
    n_workers = min(8, len(paragraphs) + 1)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {}
        for i, para in enumerate(paragraphs):
            text = _paragraph_text(para)
            futures[pool.submit(translate_text, text, 'es')] = i
        for f in as_completed(futures):
            idx = futures[f]
            par_results[idx] = f.result()
    par_time = time.time() - start
    logger.info(f"  Parallel translation: {par_time*1000:.0f}ms "
                f"({len(paragraphs)} paragraphs, {n_workers} workers)")

    if seq_time > 0:
        speedup = seq_time / par_time if par_time > 0 else float('inf')
        logger.info(f"  Speedup: {speedup:.1f}x")

    timings['translate_seq'] = seq_time
    timings['translate_par'] = par_time

    # Verify results match
    for i in range(len(paragraphs)):
        if i in seq_results and i in par_results:
            if seq_results[i] != par_results[i]:
                logger.warning(f"  Mismatch at para {i}: "
                             f"seq='{seq_results[i][:30]}' "
                             f"par='{par_results[i][:30]}'")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    total_seq = sum(v for k, v in timings.items() if k != 'translate_par')
    total_par = sum(v for k, v in timings.items() if k != 'translate_seq')
    logger.info(f"  Total (sequential translate): {total_seq*1000:.0f}ms")
    logger.info(f"  Total (parallel translate):   {total_par*1000:.0f}ms")
    logger.info(f"  Translation parallel speedup: "
                f"{timings['translate_seq']/max(timings['translate_par'],0.001):.1f}x")
    logger.info("")
    logger.info(f"  Words: {len(words)}")
    logger.info(f"  Lines: {len(lines)}")
    logger.info(f"  Paragraphs: {len(paragraphs)}")
    logger.info(f"  Estimated font: {est_font}px")

    logger.info("")
    logger.info("Stage breakdown (parallel):")
    for name, t in timings.items():
        if name not in ('translate_seq',):
            logger.info(f"  {name:20s}: {t*1000:7.0f}ms")


if __name__ == "__main__":
    run_benchmark()
