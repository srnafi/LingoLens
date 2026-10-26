# PP-OCRv6 models (optional engine)

These files back the `ppocr` engine in `python/ppocr.py` (Settings → Text
recognition → PP-OCRv6). They are **not** committed: the recogniser alone is
~21 MB.

## Files

| Path             | Role                                              | Size    |
|------------------|---------------------------------------------------|---------|
| `shared/det.onnx` | PP-OCRv6_det_tiny detector                       | 1.8 MB  |
| `shared/cls.onnx` | text-line orientation classifier (unused: the reference pipeline disables angle correction) | 1.0 MB |
| `cjk/rec.onnx`    | PP-OCRv6_small_rec recogniser (Latin + CJK)      | 21.2 MB |
| `cjk/dict.txt`    | 18,708 character dictionary for the recogniser   | 75 KB   |

These are the PaddleOCR PP-OCRv6 releases (Apache-2.0). The exact files, and
the thresholds/preprocessing used in `ppocr.py`, were taken from OverTranslate
(MIT, https://github.com/Hon-Lu/OverTranslate), which ships them under
`src/OverTranslate/ocrmodels/onnx/`:

```
shared/det.onnx  -> shared/det.onnx
shared/cls.onnx  -> shared/cls.onnx
cjk/rec.onnx     -> cjk/rec.onnx
cjk/dict.txt     -> cjk/dict.txt
```

Base URL:
`https://raw.githubusercontent.com/Hon-Lu/OverTranslate/main/src/OverTranslate/ocrmodels/onnx/`

## Notes

- OverTranslate's *manga* OCR model is a different, CC BY-NC-SA 4.0 model; it
  is not used by LingoLens.
- Coverage: Latin (source option 1), Chinese (2), Japanese (3). Korean (6)
  needs `korean/rec.onnx` + `korean/dict.txt`; until those exist the snip falls
  back to EasyOCR, as it does for Russian (4) and Bengali (5).
- The runtime is OpenVINO (already a dependency). OpenVINO reads `.onnx`
  directly, so no onnxruntime install is required.
