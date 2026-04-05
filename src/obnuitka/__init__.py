import argparse
import sys
from pathlib import Path

from obnuitka.formatter import format_file, format_directory


def main():
    parser = argparse.ArgumentParser(
        prog="obnuitka", description="Format Python files for Nuitka compilation"
    )
    parser.add_argument("path", type=Path, help="Path to file or directory to format")
    parser.add_argument(
        "-f", "--force", action="store_true", help="Format files in place"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: .obnuitka)",
    )

    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(1)

    if args.force:
        output_dir = args.path
    else:
        output_dir = args.output or args.path.parent / ".obnuitka"

    if args.path.is_file():
        result_path = format_file(args.path, output_dir, in_place=args.force)
        if result_path:
            print(f"Formatted: {result_path}")
    else:
        count = format_directory(args.path, output_dir, in_place=args.force)
        print(f"Formatted {count} files to {output_dir}")


if __name__ == "__main__":
    main()
