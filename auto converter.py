"""
MarkItDown Auto-Converter
=========================
Watches an input folder. Any file dropped in is auto-converted to Markdown.
Output saved to /outputs folder with the same filename + .md extension.

Supported:
  - PDF, DOCX, PPTX, XLSX, XLS
  - MP3, WAV, M4A, FLAC, OGG, MP4, MKV, AVI, MOV, WEBM (via OpenAI Whisper - full content)
  - HTML, TXT, CSV, JSON
  - youtube_links.txt (one YouTube URL per line)

Usage:
  python "auto converter.py"
  python "auto converter.py" --input ./my-folder --output ./my-output
  python "auto converter.py" --once   (process existing + exit)

Author: Built for Vinay's RAG pipeline
"""

import io
import os
import sys
import time
import argparse
import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime


# ── FFmpeg path configuration ─────────────────────────────────────
def configure_ffmpeg():
    downloads_dir = Path.home() / "Downloads"
    default_ffmpeg_dir = downloads_dir / "ffmpeg-master-latest-win64-gpl" / "bin"
    ffmpeg_bin = os.environ.get("FFMPEG_BIN")
    if ffmpeg_bin and Path(ffmpeg_bin).exists():
        default_ffmpeg_dir = Path(ffmpeg_bin)
    if default_ffmpeg_dir.exists():
        os.environ["PATH"] = str(default_ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
        os.environ["FFMPEG_BINARY"] = str(default_ffmpeg_dir / "ffmpeg.exe")
        os.environ["FFPROBE_BINARY"] = str(default_ffmpeg_dir / "ffprobe.exe")
        return str(default_ffmpeg_dir / "ffmpeg.exe"), str(default_ffmpeg_dir / "ffprobe.exe")
    return None, None


ffmpeg_path, ffprobe_path = configure_ffmpeg()

# ── Optional pydub (used only for audio extraction from video) ─────
try:
    from pydub import AudioSegment
    if ffmpeg_path:
        AudioSegment.converter = ffmpeg_path
    if ffprobe_path:
        AudioSegment.ffprobe = ffprobe_path
except ImportError:
    AudioSegment = None

# ── Watchdog ───────────────────────────────────────────────────────
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── MarkItDown ─────────────────────────────────────────────────────
from markitdown import MarkItDown

# ── Logging setup ──────────────────────────────────────────────────
try:
    console_stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
except Exception:
    console_stream = sys.stdout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(console_stream),
        logging.FileHandler("converter.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("MarkItDownAuto")

# ── Supported extensions ────────────────────────────────────────────
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4", ".mkv", ".avi", ".mov", ".webm"}

SUPPORTED_EXTS = {
    # Documents
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    # Web / text
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    # Audio / Video – transcribed via Whisper
    ".mp3", ".wav", ".m4a", ".flac", ".ogg",
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
}

YOUTUBE_FILENAME = "youtube_links.txt"

# ── Whisper model (loaded once, lazily) ────────────────────────────
_whisper_model = None
WHISPER_MODEL_SIZE = "base"   # tiny | base | small | medium | large


def get_whisper_model():
    """Load and cache the Whisper model (downloaded once, cached on disk)."""
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            log.info(f"Loading Whisper '{WHISPER_MODEL_SIZE}' model (first-time download may take a moment)…")
            _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
            log.info("Whisper model ready.")
        except Exception as e:
            log.error(f"Could not load Whisper: {e}")
            raise
    return _whisper_model


# ── Audio/Video → full transcript via Whisper ──────────────────────
def extract_audio_to_wav(video_path: Path) -> Path:
    """
    Extract audio from any video/audio file and save as a 16-kHz mono WAV
    in a temp file.  Returns the temp WAV path.
    Uses ffmpeg if available, falls back to pydub.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    ext = video_path.suffix.lower()
    wav_formats = {".wav"}

    # Try ffmpeg first (best compatibility)
    if ffmpeg_path and Path(ffmpeg_path).exists():
        cmd = [
            ffmpeg_path,
            "-y",                   # overwrite output
            "-i", str(video_path),  # input
            "-ar", "16000",         # 16 kHz sample rate (Whisper prefers this)
            "-ac", "1",             # mono
            "-c:a", "pcm_s16le",    # 16-bit PCM
            str(tmp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return tmp_path
        else:
            log.warning(f"ffmpeg extraction failed: {result.stderr[-300:]}")

    # Fallback: pydub
    if AudioSegment is not None:
        fmt = ext.lstrip(".")
        audio = AudioSegment.from_file(str(video_path), format=fmt)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(str(tmp_path), format="wav")
        return tmp_path

    raise RuntimeError(
        "No audio extraction tool available. "
        "Install ffmpeg or pydub+ffmpeg to process audio/video files."
    )


def transcribe_with_whisper(file_path: Path) -> str:
    """
    Transcribe an audio/video file FULLY using OpenAI Whisper.
    Returns the complete transcript as a single string.
    """
    model = get_whisper_model()

    # For video files we need to extract audio first; Whisper accepts wav natively
    need_extraction = file_path.suffix.lower() not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    tmp_wav = None

    try:
        if need_extraction or file_path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov", ".webm"}:
            log.info(f"Extracting audio from {file_path.name}…")
            tmp_wav = extract_audio_to_wav(file_path)
            audio_input = str(tmp_wav)
        else:
            audio_input = str(file_path)

        log.info(f"Transcribing with Whisper ({WHISPER_MODEL_SIZE})… (this may take a moment for long files)")
        result = model.transcribe(
            audio_input,
            language=None,          # auto-detect language
            verbose=False,          # suppress per-segment stdout noise
            fp16=False,             # safe for CPU-only machines
            word_timestamps=False,
        )

        # Compose full transcript with timestamps per segment for readability
        segments = result.get("segments", [])
        if segments:
            lines = []
            for seg in segments:
                start = seg["start"]
                end   = seg["end"]
                text  = seg["text"].strip()
                if text:
                    mm_s = int(start // 60)
                    ss_s = int(start % 60)
                    mm_e = int(end   // 60)
                    ss_e = int(end   % 60)
                    lines.append(f"[{mm_s:02d}:{ss_s:02d} → {mm_e:02d}:{ss_e:02d}]  {text}")
            transcript = "\n".join(lines)
        else:
            transcript = result.get("text", "").strip()

        detected_lang = result.get("language", "unknown")
        log.info(f"Transcription complete – {len(transcript)} chars, language: {detected_lang}")
        return transcript

    finally:
        if tmp_wav and tmp_wav.exists():
            try:
                tmp_wav.unlink()
            except Exception:
                pass


# ── Audio/Video conversion ─────────────────────────────────────────
def convert_audio_file(filepath: Path, output_dir: Path) -> bool:
    """Convert an audio/video file to Markdown using Whisper transcription."""
    out_path = output_dir / (filepath.stem + ".md")
    if out_path.exists():
        log.info(f"Skipping: {filepath.name} (already converted)")
        return True

    log.info(f"Converting: {filepath.name}")
    try:
        transcript = transcribe_with_whisper(filepath)

        if not transcript or not transcript.strip():
            log.warning(f"Empty transcript for {filepath.name} – no speech detected or silent file.")
            return False

        header = (
            f"# {filepath.stem}\n\n"
            f"> Source: `{filepath.name}`  \n"
            f"> Converted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
            f"> Transcription: OpenAI Whisper ({WHISPER_MODEL_SIZE})\n\n"
            f"---\n\n"
        )

        out_path.write_text(header + "## Transcript\n\n" + transcript + "\n", encoding="utf-8")
        log.info(f"✅ Saved: {out_path.name}  ({len(transcript):,} chars)")
        return True

    except Exception as e:
        log.error(f"❌ Failed to convert {filepath.name}: {e}")
        return False


# ── Document conversion (PDF, DOCX, PPTX, XLSX, HTML, TXT…) ───────
def convert_file(filepath: Path, output_dir: Path) -> bool:
    """Convert a document to Markdown via MarkItDown. Returns True on success."""
    out_path = output_dir / (filepath.stem + ".md")
    if out_path.exists():
        log.info(f"Skipping: {filepath.name} (already converted)")
        return True

    md = MarkItDown()
    try:
        log.info(f"Converting: {filepath.name}")
        result = md.convert(str(filepath))

        if not result.text_content or result.text_content.strip() == "":
            log.warning(f"Empty output for {filepath.name} – skipping.")
            return False

        header = (
            f"# {filepath.stem}\n\n"
            f"> Source: `{filepath.name}`  \n"
            f"> Converted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"---\n\n"
        )

        out_path.write_text(header + result.text_content, encoding="utf-8")
        log.info(f"✅ Saved: {out_path.name}  ({len(result.text_content):,} chars)")
        return True

    except Exception as e:
        log.error(f"❌ Failed to convert {filepath.name}: {e}")
        return False


# ── YouTube link conversion ────────────────────────────────────────
def convert_youtube_links(filepath: Path, output_dir: Path):
    """Read a file of YouTube URLs (one per line) and convert each to Markdown."""
    md = MarkItDown()
    lines = filepath.read_text(encoding="utf-8").splitlines()
    urls = [l.strip() for l in lines if l.strip().startswith("http")]

    if not urls:
        log.warning("youtube_links.txt found but no valid URLs inside.")
        return

    log.info(f"Found {len(urls)} YouTube URL(s) to transcribe…")

    for url in urls:
        try:
            video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url[-11:]
            out_path = output_dir / f"youtube_{video_id}.md"

            if out_path.exists():
                log.info(f"Skipping YouTube URL: {url} (already converted)")
                continue

            log.info(f"Transcribing: {url}")
            result = md.convert(url)

            if not result.text_content or result.text_content.strip() == "":
                log.warning(f"Empty transcript for {url}")
                continue

            header = (
                f"# YouTube Transcript\n\n"
                f"> URL: {url}  \n"
                f"> Converted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"---\n\n"
            )

            out_path.write_text(header + result.text_content, encoding="utf-8")
            log.info(f"✅ Saved: {out_path.name}")

        except Exception as e:
            log.error(f"❌ Failed for {url}: {e}")


# ── Ignored file patterns ─────────────────────────────────────────
IGNORED_EXTS    = {".log", ".tmp", ".bak", ".part", ".crdownload", ".md"}
IGNORED_PREFIXES = (".", "~")   # hidden files and Office temp files


def is_ignorable(filepath: Path) -> bool:
    """Return True for files that should never be processed."""
    name = filepath.name
    if name.startswith(IGNORED_PREFIXES):
        return True
    if filepath.suffix.lower() in IGNORED_EXTS:
        return True
    return False


# ── Dispatch: decide how to handle a file ─────────────────────────
def handle_new_file(filepath: Path, output_dir: Path):
    """Decide how to handle a newly detected file."""
    if not filepath.exists():
        log.warning(f"File disappeared before processing: {filepath.name}")
        return

    if is_ignorable(filepath):
        log.debug(f"Ignored file: {filepath.name}")
        return

    # Special case: YouTube links
    if filepath.name.lower() == YOUTUBE_FILENAME:
        convert_youtube_links(filepath, output_dir)
        return

    ext = filepath.suffix.lower()
    if ext in AUDIO_EXTS:
        convert_audio_file(filepath, output_dir)
    elif ext in SUPPORTED_EXTS:
        convert_file(filepath, output_dir)
    else:
        log.warning(f"Skipped (unsupported extension): {filepath.name}")


# ── Process files already present on startup ───────────────────────
def process_existing_files(input_dir: Path, output_dir: Path):
    """On startup, convert any files already in the input folder."""
    files = [f for f in input_dir.iterdir() if f.is_file()]
    if not files:
        log.info("Input folder is empty – waiting for files…")
        return
    log.info(f"Processing {len(files)} existing file(s) in input folder…")
    for f in sorted(files):
        handle_new_file(f, output_dir)


# ── Watchdog event handler ─────────────────────────────────────────
class FolderWatcher(FileSystemEventHandler):
    """Watches the input folder and auto-converts new files."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self._processing: set = set()   # debounce: filenames currently being processed

    def on_created(self, event):
        if event.is_directory:
            return
        self._process_event(event.src_path)

    def on_moved(self, event):
        """Handle files moved/renamed into the watched folder."""
        if event.is_directory:
            return
        self._process_event(event.dest_path)

    def _process_event(self, src_path: str):
        filepath = Path(src_path)

        # Skip if already being processed (debounce)
        key = str(filepath)
        if key in self._processing:
            return
        self._processing.add(key)

        try:
            # Wait for the file to finish being written (important for large videos)
            self._wait_for_file_stable(filepath)

            if filepath.exists():
                log.info(f"🆕 New file detected: {filepath.name}")
                handle_new_file(filepath, self.output_dir)
        finally:
            # Allow re-processing after 10s (in case the file is replaced)
            time.sleep(10)
            self._processing.discard(key)

    def _wait_for_file_stable(self, filepath: Path, timeout: int = 60):
        """Wait until the file size stops changing (fully written)."""
        prev_size = -1
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                curr_size = filepath.stat().st_size
            except FileNotFoundError:
                return
            if curr_size == prev_size and curr_size > 0:
                return          # stable
            prev_size = curr_size
            time.sleep(1.5)
        log.warning(f"Timeout waiting for {filepath.name} to finish writing.")


# ── Main ───────────────────────────────────────────────────────────
def main():
    global WHISPER_MODEL_SIZE  # must appear before any use of the name

    _default_model = WHISPER_MODEL_SIZE   # capture before possibly overwriting
    parser = argparse.ArgumentParser(
        description="Auto-convert files to Markdown using OpenAI Whisper + MarkItDown"
    )
    parser.add_argument(
        "--input", default="./inputs",
        help="Folder to watch for new files (default: ./inputs)"
    )
    parser.add_argument(
        "--output", default="./outputs",
        help="Folder to save .md files (default: ./outputs)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process existing files and exit (no watching)"
    )
    parser.add_argument(
        "--model", default=_default_model,
        choices=["tiny", "base", "small", "medium", "large"],
        help=f"Whisper model size (default: {_default_model}). "
             "Larger = more accurate but slower."
    )
    args = parser.parse_args()

    WHISPER_MODEL_SIZE = args.model
    input_dir  = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("  MarkItDown Auto-Converter  (Whisper Edition)")
    log.info("=" * 60)
    log.info(f"  Input  : {input_dir}")
    log.info(f"  Output : {output_dir}")
    log.info(f"  Whisper: {WHISPER_MODEL_SIZE} model")
    log.info(f"  Docs   : PDF, DOCX, PPTX, XLSX, HTML, TXT, CSV, JSON")
    log.info(f"  Media  : MP3, WAV, M4A, FLAC, OGG, MP4, MKV, AVI, MOV, WEBM")
    log.info("=" * 60)

    # Pre-load the Whisper model so the first conversion isn't slow
    try:
        get_whisper_model()
    except Exception:
        log.warning("Whisper model could not be loaded – audio/video conversion will fail.")

    # Process files already in the folder
    process_existing_files(input_dir, output_dir)

    if args.once:
        log.info("--once flag set. Exiting after processing existing files.")
        return

    # ── Start watching ──────────────────────────────────────────────
    handler  = FolderWatcher(output_dir)
    observer = Observer()
    observer.schedule(handler, str(input_dir), recursive=False)
    observer.start()

    log.info("👀 Watching for new files… (Press Ctrl+C to stop)")

    try:
        while True:
            # Heartbeat check: restart observer if it dies unexpectedly
            if not observer.is_alive():
                log.warning("Observer died – restarting…")
                observer = Observer()
                observer.schedule(handler, str(input_dir), recursive=False)
                observer.start()
            time.sleep(2)
    except KeyboardInterrupt:
        log.info("Stopping watcher…")
    finally:
        observer.stop()
        observer.join()
        log.info("Done.")


if __name__ == "__main__":
    main()