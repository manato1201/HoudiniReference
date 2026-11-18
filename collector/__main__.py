import argparse
import sys
from pathlib import Path

from .run import run

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m collector", description="HoudiniReference collector")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--site-data-dir", type=Path, default=ROOT / "site" / "data")
    ap.add_argument("--dry-run", action="store_true", help="取得せず、見込み(特に X の件数)だけ表示")
    ap.add_argument("--only", help="この id の情報源だけ取得")
    ap.add_argument("--no-x", action="store_true")
    ap.add_argument("--no-youtube-api", action="store_true")
    a = ap.parse_args(argv)
    return run(a.data_dir, a.site_data_dir, dry_run=a.dry_run, only=a.only, no_x=a.no_x, no_youtube_api=a.no_youtube_api)


if __name__ == "__main__":
    sys.exit(main())
