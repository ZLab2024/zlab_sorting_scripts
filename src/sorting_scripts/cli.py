"""Command line interface for the same APIs used by notebooks."""
import argparse
import json
from .provenance import json_default


def main(argv=None):
    """Run zsort validate/run/status/resume/inspect or explicit KS4 checkpoint recovery."""
    parser = argparse.ArgumentParser(prog='zsort', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'run'):
        cmd = commands.add_parser(name); cmd.add_argument('--config', required=True)
        if name == 'validate': cmd.add_argument('--skip-backend-check', action='store_true')
    cmd = commands.add_parser('status'); cmd.add_argument('--run', required=True)
    cmd = commands.add_parser('resume'); cmd.add_argument('--run', required=True); cmd.add_argument('--config')
    cmd = commands.add_parser('inspect'); cmd.add_argument('--analyzer', required=True)
    cmd.add_argument('--unit'); cmd.add_argument('--output', help='New PNG outside source analyzer')
    cmd = commands.add_parser('resume-clustering'); cmd.add_argument('--checkpoint',required=True); cmd.add_argument('--output',required=True)
    cmd = commands.add_parser('probe', help='Export a named probe preset to a NEW JSON file')
    from .probes import PRESETS
    cmd.add_argument('--preset', choices=PRESETS, required=True)
    cmd.add_argument('--channels', type=int)
    cmd.add_argument('--output', required=True)
    cmd = commands.add_parser('streams', help='List native recording stream IDs/names')
    cmd.add_argument('--input', required=True)
    cmd.add_argument('--format', choices=['intan','neuralynx','med','spikeinterface'], required=True)
    cmd.add_argument('--extractor')
    cmd.add_argument('--password-env', default='MED_PASSWORD')
    args = parser.parse_args(argv)
    from . import pipeline
    if args.command == 'probe':
        from .probes import get_probe, save_probe
        result = {'probe': str(save_probe(get_probe(args.preset, n_channels=args.channels), args.output))}
    elif args.command == 'streams':
        from .io import list_streams
        result = list_streams(args.input, format=args.format, extractor=args.extractor, password_env=args.password_env)
    elif args.command == 'validate':
        result = pipeline.validate(args.config, check_backend=not args.skip_backend_check)
    elif args.command == 'run': result = {'run': str(pipeline.run(args.config))}
    elif args.command == 'status': result = pipeline.status(args.run)
    elif args.command == 'resume': result = {'run':str(pipeline.run(args.config, resume=args.run))}
    elif args.command == 'resume-clustering':
        from .kilosort_runtime import resume_clustering
        result = {'sorter_output':str(resume_clustering(args.checkpoint,args.output))}
    else:
        from .inspection import inspect_analyzer
        analyzer = inspect_analyzer(args.analyzer, unit_id=args.unit, output=args.output)
        result = dict(unit_ids=analyzer.unit_ids, channels=analyzer.channel_ids)
    print(json.dumps(result, indent=2, default=json_default))
    return 0
