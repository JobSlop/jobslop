"""OCR for CVs whose text is drawn as shapes or scanned (Windows' own offline OCR engine)."""

import json
import subprocess
import sys

from jobslop.config import DATA_DIR

# ---- OCR for CVs whose text is drawn as shapes or scanned (Windows' own offline OCR engine)

OCR_PS1 = r'''param([string]$path)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(); $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US")) }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
    $words = @($line.Words)
    $r = $words[0].BoundingRect
    $h = 0; foreach ($w in $words) { if ($w.BoundingRect.Height -gt $h) { $h = $w.BoundingRect.Height } }
    [Console]::Out.WriteLine(([pscustomobject]@{ t = $line.Text; x = [int]$r.X; y = [int]$r.Y; h = [int]$h } | ConvertTo-Json -Compress))
}
$stream.Dispose()
'''


def _write_bmp(bitmap, out):
    """pypdfium2 bitmap -> 24-bit BMP file (no imaging library needed)."""
    import struct
    w, h, stride = bitmap.width, bitmap.height, bitmap.stride
    data = bytes(bitmap.buffer)
    bpp = 3 if stride // max(w, 1) == 3 else 4
    row = (w * 3 + 3) & ~3
    pad = b"\0" * (row - w * 3)
    with open(out, "wb") as f:
        f.write(b"BM" + struct.pack("<IHHI", 54 + row * h, 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 24, 0, row * h, 2835, 2835, 0, 0))
        for y in range(h):
            line = data[y * stride: y * stride + w * bpp]
            if bpp == 4:
                line = b"".join(line[i:i + 3] for i in range(0, len(line), 4))
            f.write(line + pad)


def ocr_pdf(path, pages=2):
    """Read the first pages of a PDF as images with Windows OCR. [] when not on Windows or anything fails."""
    if sys.platform != "win32":
        return []
    try:
        import pypdfium2 as pdfium
    except Exception:
        return []
    work = DATA_DIR / "ocr"
    work.mkdir(exist_ok=True)
    script = work / "ocr.ps1"
    if not script.exists() or script.read_text(encoding="utf-8") != OCR_PS1:
        script.write_text(OCR_PS1, encoding="utf-8")
    lines = []
    try:
        pdf = pdfium.PdfDocument(str(path))
        for n in range(min(pages, len(pdf))):
            img = work / f"page{n}.bmp"
            bitmap = pdf[n].render(scale=3)
            _write_bmp(bitmap, img)
            width = bitmap.width
            run = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                  "-File", str(script), str(img)], capture_output=True, timeout=60,
                                 creationflags=0x08000000)               # no console window
            for raw in run.stdout.decode("utf-8", "replace").splitlines():
                try:
                    d = json.loads(raw)
                    d.update(page=n, w=width)
                    lines.append(d)
                except ValueError:
                    pass
            img.unlink(missing_ok=True)
        pdf.close()
    except Exception:
        return lines
    return lines
