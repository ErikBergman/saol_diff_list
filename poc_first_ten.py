#!/usr/bin/env python3

from collections import defaultdict
from pathlib import Path
import csv

INPUT = Path("data/shlex-sslg-v01_0.txt")
LIMIT = 10

def main() -> None:
    counts = defaultdict(int)

    with INPUT.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            edition = row["#dictionary"]
            word = row["entry"]  # change to row["standardized"] if preferred

            if counts[edition] < LIMIT:
                counts[edition] += 1
                print(f"{edition}\t{counts[edition]}\t{word}")

if __name__ == "__main__":
    main()
