"""Compatibility CLI; canonical generator is sorting_scripts.probes.make_deeparray128."""
import argparse
from pathlib import Path
from probeinterface import write_probeinterface
from sorting_scripts.probes.deeparray import make_deeparray128 as create_probe

OUTPUT_PATH = Path(__file__).with_name('deeparray128_P1925-127_H1925-116.json')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    write_probeinterface(args.output, create_probe())
    print(f'Saved 128 contacts to {args.output.resolve()}')

if __name__ == '__main__': main()
