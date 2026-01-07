#!/usr/bin/env python3
"""
rename_photos.py

Rename photos using EXIF date (DateTimeOriginal) into filenames like YYYY-MM-DD_HH-MM-SS.ext
Primary EXIF reader: exifread. Falls back to exiftool (if available) for formats exifread doesn't handle.

Usage:
    python rename_photos.py /path/to/photos [other paths] [options]
"""
from __future__ import annotations
import argparse
import logging
import sys
import os
import shutil
import subprocess
from datetime import datetime
from typing import Optional, Tuple, List, Iterable

try:
    import exifread
except Exception:
    exifread = None  # may be None; we'll try exiftool as fallback

DEFAULT_EXTENSIONS = ["jpg", "jpeg", "heic", "cr2", "nef", "arw", "raf", "dng", "png"]

logger = logging.getLogger("photo-renamer")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rename photos using EXIF date")
    p.add_argument("paths", nargs="+", help="Files or directories to process")
    p.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into directories",
    )
    p.add_argument(
        "-s",
        "--simulate",
        action="store_true",
        help="Dry-run; show what would be renamed",
    )
    p.add_argument(
        "--use-filetime",
        action="store_true",
        help="If EXIF date missing, use file modification time",
    )
    p.add_argument(
        "-f",
        "--format",
        default="%Y-%m-%d_%H-%M-%S",
        help="Datetime format for new filename (strftime format). Default: %%Y-%%m-%%d_%%H-%%M-%%S",
    )
    p.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help=f"Comma-separated list of file extensions to process. Default: {','.join(DEFAULT_EXTENSIONS)}",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def iter_candidates(paths: Iterable[str], recursive: bool, extset: set) -> Iterable[str]:
    for p in paths:
        if os.path.isfile(p):
            if os.path.splitext(p)[1].lstrip(".").lower() in extset:
                yield os.path.abspath(p)
            else:
                logger.debug("Skipping file (extension not in set): %s", p)
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, files in os.walk(p):
                    for fn in files:
                        if os.path.splitext(fn)[1].lstrip(".").lower() in extset:
                            yield os.path.abspath(os.path.join(root, fn))
            else:
                for fn in os.listdir(p):
                    full = os.path.join(p, fn)
                    if os.path.isfile(full) and os.path.splitext(full)[1].lstrip(".").lower() in extset:
                        yield os.path.abspath(full)
        else:
            logger.warning("Path not found or unsupported: %s", p)


def parse_exif_date_exifread(path: str) -> Optional[datetime]:
    if exifread is None:
        return None
    try:
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, stop_tag="UNDEF", details=False)
        # Common tags:
        for tag in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
            if tag in tags:
                val = str(tags[tag])
                # format "YYYY:MM:DD HH:MM:SS"
                try:
                    dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                    return dt
                except Exception:
                    logger.debug("Failed parsing EXIF tag %s='%s' for %s", tag, val, path)
    except Exception as e:
        logger.debug("exifread failed on %s: %s", path, e)
    return None


def parse_exif_date_exiftool(path: str) -> Optional[datetime]:
    """
    Ask exiftool for DateTimeOriginal or CreateDate or FileModifyDate.
    Requires exiftool in PATH.
    """
    try:
        proc = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-CreateDate", "-DateTime", "-j", path],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            logger.debug("exiftool returned non-zero for %s: %s", path, proc.stderr.strip())
        out = proc.stdout.strip()
        if not out:
            return None
        import json

        try:
            data = json.loads(out)
            if not data or not isinstance(data, list):
                return None
            info = data[0]
            for key in ("DateTimeOriginal", "CreateDate", "DateTime"):
                if key in info and info[key]:
                    val = info[key]
                    # exiftool outputs "YYYY:MM:DD HH:MM:SS" or "YYYY:MM:DD HH:MM:SS+TZ"
                    val = val.split("+")[0].split("-")[0].strip()
                    try:
                        dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                        return dt
                    except Exception:
                        logger.debug("exiftool returned unparsable date '%s' for %s", val, path)
        except Exception as e:
            logger.debug("Failed to parse exiftool json output for %s: %s", path, e)
    except FileNotFoundError:
        logger.debug("exiftool not found in PATH")
    except Exception as e:
        logger.debug("exiftool error for %s: %s", path, e)
    return None


def get_image_datetime(path: str, use_filetime: bool) -> Optional[datetime]:
    dt = parse_exif_date_exifread(path)
    if dt:
        logger.debug("Parsed EXIF using exifread: %s -> %s", path, dt.isoformat())
        return dt
    dt2 = parse_exif_date_exiftool(path)
    if dt2:
        logger.debug("Parsed EXIF using exiftool: %s -> %s", path, dt2.isoformat())
        return dt2
    if use_filetime:
        try:
            ts = os.path.getmtime(path)
            dt3 = datetime.fromtimestamp(ts)
            logger.debug("Using file mtime as fallback: %s -> %s", path, dt3.isoformat())
            return dt3
        except Exception as e:
            logger.debug("Failed to get file mtime for %s: %s", path, e)
    return None


def unique_target_path(directory: str, base_name: str, ext: str) -> str:
    candidate = os.path.join(directory, f"{base_name}.{ext}")
    if not os.path.exists(candidate):
        return candidate
    # append counter
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{base_name}_{counter}.{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def rename_file(src: str, dst: str, simulate: bool = False) -> None:
    if simulate:
        print(f"SIMULATE: {src} -> {dst}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    print(f"RENAMED: {src} -> {dst}")


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    extset = set(e.strip().lower() for e in args.extensions.split(",") if e.strip())
    files = list(iter_candidates(args.paths, args.recursive, extset))
    if not files:
        logger.info("No files found matching extensions: %s", ", ".join(sorted(extset)))
        return 0

    logger.info("Found %d candidate files", len(files))

    mapping: List[Tuple[str, str]] = []
    failures: List[Tuple[str, str]] = []

    for src in files:
        try:
            dt = get_image_datetime(src, args.use_filetime)
            if not dt:
                logger.warning("No date found for %s (skipping)", src)
                failures.append((src, "no-date"))
                continue
            base = dt.strftime(args.format)
            directory = os.path.dirname(src)
            ext = os.path.splitext(src)[1].lstrip(".")
            target = unique_target_path(directory, base, ext)
            if os.path.abspath(src) == os.path.abspath(target):
                logger.info("Source and target are same for %s (skipping)", src)
                continue
            mapping.append((src, target))
        except Exception as e:
            logger.exception("Failed processing %s: %s", src, e)
            failures.append((src, str(e)))

    if not mapping:
        logger.info("Nothing to rename.")
        return 0

    # show summary
    print("Planned renames:")
    for s, t in mapping:
        print(f"{s} -> {t}")

    if args.simulate:
        print("Simulation mode; no files renamed.")
        return 0

    # Execute renames
    for s, t in mapping:
        try:
            rename_file(s, t, simulate=False)
        except Exception as e:
            logger.exception("Failed renaming %s -> %s: %s", s, t, e)
            failures.append((s, str(e)))

    if failures:
        logger.warning("Some files were not processed. Count: %d", len(failures))
        for f, reason in failures:
            logger.warning("%s: %s", f, reason)
        return 2

    logger.info("Done. Renamed %d files.", len(mapping))
    return 0


if __name__ == "__main__":
    sys.exit(main())