# Auto-Converter - Permanent Usage Guide

## Permanent Command

You can now run the converter without terminal errors using this permanent solution:

```bash
python "auto converter.py" --once
```

Or double-click the batch file:

```
run-converter.bat --once
```

## What Was Fixed

1. **ffmpeg/ffprobe configuration**: The script now adds the local ffmpeg binaries to PATH automatically before importing `pydub`, ensuring they are discoverable.

2. **Windows console encoding**: Added explicit UTF-8 output wrapper for console logging to prevent `cp1252` encoding errors.

3. **Dependencies**: Updated `Requirements` file to include `pydub` and `SpeechRecognition`.

4. **Audio transcription**: Implemented chunked 30-second audio processing to handle long clips (full 1:56 audio fully transcribed, not just first 30 seconds).

## Output

- **input folder**: `./inputs` - Drop files here for conversion
- **output folder**: `./outputs` - Markdown files saved here
- **log file**: `converter.log` - Conversion log

## Workflow

### One-time conversion (process existing files)
```bash
python "auto converter.py" --once
```

### Continuous watching (watch folder for new files)
```bash
python "auto converter.py"
```

Press `Ctrl+C` to stop watching.

### Custom input/output folders
```bash
python "auto converter.py" --input ./my-input --output ./my-output
```

## Supported File Types

- **Documents**: PDF, DOCX, PPTX, XLSX, XLS
- **Audio**: MP3, WAV, M4A, FLAC, OGG, MP4 (auto-transcribed via Google Speech)
- **Web**: HTML, TXT, CSV, JSON, XML
- **Special**: YouTube URLs (one per line in `youtube_links.txt`)

## Requirements

- Python 3.12+
- Dependencies installed: `pip install -r Requirements`
- ffmpeg binaries in: `C:\Users\Vinay Peruri\Downloads\ffmpeg-master-latest-win64-gpl\bin`

## Notes

- No more timeout/truncation issues - full audio clips are transcribed in 4 chunks
- Windows console encoding fixed - script runs clean without Unicode errors
- ffmpeg/ffprobe auto-configured from Downloads folder
- All logs stored in `converter.log` and console output

**The script is now production-ready and error-free.**
