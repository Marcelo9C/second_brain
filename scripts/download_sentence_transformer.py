from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a SentenceTransformer model into the local models directory."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Remote model id to download from Hugging Face.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "models" / "all-MiniLM-L6-v2"),
        help="Target directory to store the downloaded model.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise SystemExit(
            "sentence-transformers is not installed. Install it before downloading the model."
        ) from error

    output_dir = Path(args.output_dir).resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {args.model}...")
    model = SentenceTransformer(args.model)
    model.save(str(output_dir))
    print(f"Saved to {output_dir}")


if __name__ == "__main__":
    main()
