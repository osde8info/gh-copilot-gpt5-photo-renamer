# Photo Renamer (EXIF date)

Rename photos using EXIF date (DateTimeOriginal) into filenames like `YYYY-MM-DD_HH-MM-SS.ext`.

Requirements

- Python 3.8+
- Install dependency:
  - pip install -r requirements.txt

By default the script uses the `exifread` library (works for JPEG). If you have `exiftool` installed (command-line tool), the script will use it as a fallback for formats exifread doesn't support (HEIC, some RAWs).

Usage

```bash
python rename_photos.py [path ...] [options]
```

Examples

- Rename all files in a directory (non-recursive):

  ```bash
  python rename_photos.py /path/to/photos
  ```

- Recursive, dry-run:

  ```
  python rename_photos.py /path/to/photos -r --simulate
  ```

- Use file modification time when EXIF missing:

  ```
  python rename_photos.py /path/to/photos --use-filetime
  ```

Options

- -r, --recursive: walk directories recursively
- -s, --simulate: dry-run (shows what would be renamed)
- --use-filetime: if EXIF date not found, fall back to filesystem modified time
- -f, --format: filename format string (default: `%Y-%m-%d_%H-%M-%S`)
- -v, --verbose: verbose logging
- --extensions: comma-separated list of file extensions to process (default: jpg,jpeg,heic,cr2,nef,arw,raf,dng,png)

Behavior

- For each image, the script tries EXIF DateTimeOriginal, then EXIF DateTime, then (if enabled) file mtime.
- If target filename already exists, a suffix `_1`, `_2`, ... is appended.
- The script prints a mapping of renamed files and returns non-zero only on unhandled fatal errors.

License: MIT
