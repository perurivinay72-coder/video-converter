"""
MarkItDown Auto-Converter
=========================
Watches an input folder. Any file dropped in is auto-converted to Markdown.
Output saved to /outputs folder with the same filename + .md extension.

Supported:
  - PDF, DOCX, PPTX, XLSX, XLS
  - MP3, WAV, M4A, FLAC (audio transcription via Google Speech)
  - HTML, TXT, CSV, JSON
  - youtube_links.txt (one YouTube URL per line)

Usage:
  python auto_converter.py
  python auto_converter.py --input ./my-folder --output ./my-output

Author: Built for Vinay's RAG pipeline
"""

import io
import os
import sys
import time
import math
import argparse
import logging
from pathlib import Path
from datetime import datetime


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

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    from pydub import AudioSegment
    if ffmpeg_path and ffprobe_path:
        AudioSegment.converter = ffmpeg_path
        AudioSegment.ffprobe = ffprobe_path
except ImportError:
    AudioSegment = None

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from markitdown import MarkItDown

# -- Logging setup --------------------------------------------------
console_stream = None
try:
    console_stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
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

# -- Supported file extensions -------------------------------------
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4"}
SUPPORTED_EXTS = {
    # Documents
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    # Web / text
    ".html", ".htm", ".txt", ".csv", ".json", ".xml",
    # Audio / video
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4",
    # Special: a .txt file named youtube_links.txt is handled separately
}

YOUTUBE_FILENAME = "youtube_links.txt"


def convert_file(filepath: Path, output_dir: Path) -> bool:
    """Convert a single file to Markdown. Returns True on success."""
    out_path = output_dir / (filepath.stem + ".md")
    if out_path.exists():
        log.info(f"Skipping: {filepath.name} (already converted, output file exists)")
        return True

    md = MarkItDown()
    try:
        log.info(f"Converting: {filepath.name}")
        result = md.convert(str(filepath))

        if not result.text_content or result.text_content.strip() == "":
            log.warning(f"Empty output for {filepath.name} - skipping.")
            return False

        # Add a nice header
        header = (
            f"# {filepath.stem}\n\n"
            f"> Source: `{filepath.name}`  \n"
            f"> Converted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"---\n\n"
        )

        out_path.write_text(header + result.text_content, encoding="utf-8")
        log.info(f"Saved: {out_path.name} ({len(result.text_content)} chars)")
        return True

    except Exception as e:
        log.error(f"Failed to convert {filepath.name}: {e}")
        return False


def transcribe_long_audio(file_path: Path) -> str:
    """Transcribe long audio using speech_recognition in chunks.

    Uses 10-second chunks with 1.5s overlap to stay within Google's free
    Speech API limits and avoid cutting words at chunk boundaries.
    Retries each chunk up to 3 times on transient failures.
    """
    if sr is None or AudioSegment is None:
        raise RuntimeError("speech_recognition and pydub are required for long audio transcription")

    audio_ext = file_path.suffix.lower().lstrip('.')
    audio = AudioSegment.from_file(str(file_path), format=audio_ext)
    duration_ms = len(audio)

    # Smaller chunks work far more reliably with Google's free Speech API.
    # 30-second chunks often get silently truncated; 10 seconds is the sweet spot.
    chunk_ms = 10_000
    overlap_ms = 1_500          # slight overlap so words aren't cut mid-syllable
    step_ms = chunk_ms - overlap_ms  # advance by 8.5 s per iteration
    max_retries = 3
    retry_delay = 2             # seconds between retries

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300   # sensible default for varied audio
    transcripts = []

    total_chunks = math.ceil(max(duration_ms - overlap_ms, 1) / step_ms)

    chunk_index = 0
    pos = 0
    while pos < duration_ms:
        chunk_index += 1
        end = min(pos + chunk_ms, duration_ms)
        segment = audio[pos:end]

        # Export chunk to in-memory WAV
        buffer = io.BytesIO()
        segment.export(buffer, format='wav')
        buffer.seek(0)

        text = ''
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                with sr.AudioFile(buffer) as source:
                    audio_data = recognizer.record(source)
                    text = recognizer.recognize_google(audio_data).strip()
                break  # success
            except sr.UnknownValueError:
                # Google couldn't understand the audio – likely silence / noise
                log.debug(f"Chunk {chunk_index}/{total_chunks}: speech not recognised (attempt {attempt})")
                text = ''
                break  # no point retrying if the audio itself is unintelligible
            except sr.RequestError as e:
                last_error = e
                log.warning(f"Chunk {chunk_index}/{total_chunks}: request error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    buffer.seek(0)  # reset buffer for retry
                    time.sleep(retry_delay)
            except Exception as e:
                last_error = e
                log.warning(f"Chunk {chunk_index}/{total_chunks}: unexpected error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    buffer.seek(0)
                    time.sleep(retry_delay)

        if text:
            transcripts.append(text)
            log.info(f"Transcribed chunk {chunk_index}/{total_chunks} ({len(text)} chars)")
        else:
            reason = f" – {last_error}" if last_error else " – no speech detected"
            log.warning(f"Chunk {chunk_index}/{total_chunks}: empty result{reason}")

        pos += step_ms  # advance by step (chunk minus overlap)

    if not transcripts:
        log.warning("No transcript produced for any chunk")
        return ''

    return ' '.join(transcripts)


def convert_audio_file(filepath: Path, output_dir: Path):
    """Convert an audio/video file to Markdown by chunked transcription."""
    out_path = output_dir / (filepath.stem + ".md")
    if out_path.exists():
        log.info(f"Skipping: {filepath.name} (already converted, output file exists)")
        return True

    try:
        log.info(f"Converting: {filepath.name}")
        transcript = transcribe_long_audio(filepath)

        if not transcript or transcript.strip() == "":
            log.warning(f"Empty transcript for {filepath.name}")
            return False

        header = (
            f"# {filepath.stem}\n\n"
            f"> Source: `{filepath.name}`  \n"
            f"> Converted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"---\n\n"
        )

        out_path.write_text(header + "### Audio Transcript:\n" + transcript, encoding="utf-8")
        log.info(f"Saved: {out_path.name}")
        return True

    except Exception as e:
        log.error(f"Failed to convert {filepath.name}: {e}")
        return False


def convert_youtube_links(filepath: Path, output_dir: Path):
    """Read a file of YouTube URLs (one per line) and convert each to Markdown."""
    md = MarkItDown()
    lines = filepath.read_text(encoding="utf-8").splitlines()
    urls = [l.strip() for l in lines if l.strip().startswith("http")]

    if not urls:
        log.warning("youtube_links.txt found but no valid URLs inside.")
        return

    log.info(f"Found {len(urls)} YouTube URL(s) to transcribe...")

    for url in urls:
        try:
            # Use video ID or sanitized URL as filename
            video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url[-11:]
            out_path = output_dir / f"youtube_{video_id}.md"

            if out_path.exists():
                log.info(f"Skipping YouTube URL: {url} (already converted, output file exists)")
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
            log.info(f"Saved: {out_path.name}")

        except Exception as e:
            log.error(f"Failed for {url}: {e}")

def process_existing_files(input_dir: Path, output_dir: Path):
    """On startup, convert any files already in the input folder."""
    files = list(input_dir.iterdir())
    if not files:
        return
    log.info(f"Processing {len(files)} existing file(s) in input folder...")
    for f in files:
        if f.is_file():
            handle_new_file(f, output_dir)


def handle_new_file(filepath: Path, output_dir: Path):
    """Decide how to handle a newly detected file."""
    # Special case: YouTube links file
    if filepath.name.lower() == YOUTUBE_FILENAME:
        convert_youtube_links(filepath, output_dir)
        return

    ext = filepath.suffix.lower()
    if ext in AUDIO_EXTS:
        convert_audio_file(filepath, output_dir)
    elif ext in SUPPORTED_EXTS:
        convert_file(filepath, output_dir)
    else:
        log.debug(f"Skipped (unsupported): {filepath.name}")


# ── Watchdog event handler ──────────────────────────────────────
class FolderWatcher(FileSystemEventHandler):
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self._recently_seen: set = set()

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)

        # Debounce: skip if we just saw this file (within 2 seconds)
        key = str(filepath)
        if key in self._recently_seen:
            return
        self._recently_seen.add(key)

        # Small delay to ensure file is fully written before reading
        time.sleep(1.5)

        if filepath.exists():
            handle_new_file(filepath, self.output_dir)

        # Clean up debounce set after 5 seconds
        time.sleep(5)
        self._recently_seen.discard(key)


# ── Main ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Auto-convert files to Markdown using MarkItDown"
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
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 55)
    log.info("  MarkItDown Auto-Converter")
    log.info("=" * 55)
    log.info(f"  Watching : {input_dir}")
    log.info(f"  Outputs  : {output_dir}")
    log.info(f"  Supported: PDF, DOCX, PPTX, XLSX, MP3, WAV, HTML, TXT + YouTube URLs")
    log.info("=" * 55)

    # Process files already in the folder
    process_existing_files(input_dir, output_dir)

    if args.once:
        log.info("--once flag set. Exiting after processing existing files.")
        return

    # Start watching
    handler = FolderWatcher(output_dir)
    observer = Observer()
    observer.schedule(handler, str(input_dir), recursive=False)
    observer.start()

    log.info("Watching for new files... (Press Ctrl+C to stop)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping watcher...")
        observer.stop()

    observer.join()
    log.info("Done.")


if __name__ == "__main__":
    main()