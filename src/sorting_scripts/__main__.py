"""Allow python -m sorting_scripts without reinstalling the console entry point."""
from .cli import main

if __name__ == '__main__':
    raise SystemExit(main())
