"""Opt-in real MS5 smoke run on synthetic data only; requires the mountainsort extra.

    python examples/synthetic_smoke.py --output /tmp/new-zlab-smoke

The destination must be new. This tests execution, not scientific accuracy.
"""
import argparse
from pathlib import Path
import spikeinterface as si
from sorting_scripts import run, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preset',choices=['bf_dummy8','bf_single8'],default='bf_dummy8')
    args = parser.parse_args()
    root=args.output.expanduser().resolve()
    root.mkdir(parents=True,exist_ok=False)
    recording, _ = si.generate_ground_truth_recording(
        durations=[3.],sampling_frequency=30000,num_channels=8,num_units=3,
        generate_sorting_kwargs={'firing_rates':30.},seed=11)
    recording.save(folder=root/'input',format='binary',n_jobs=1,progress_bar=False)
    folder=run({'input':{'format':'binary_folder','path':str(root/'input')},
                'probe':{'preset':args.preset,'replace_existing':True},
                'sorting':{'backend':'mountainsort5','profile':'bf_bundle_ms5' if args.preset == 'bf_dummy8' else 'bf_single_wire'},
                'curation':{'policy':'labels_only'},'output':{'root':str(root/'runs')}})
    manifest=status(folder)
    before=si.load(folder/manifest['outputs']['raw_sorting'])
    after=si.load(folder/manifest['outputs']['sorting'])
    signature=lambda s: sorted(tuple(s.get_unit_spike_train(u)) for u in s.unit_ids)
    assert signature(before)==signature(after), 'Labels-only changed spike trains'
    assert manifest['status']=='complete'
    print('Completed synthetic run:',folder)
    print('Units:',after.get_num_units(),'Spikes:',sum(after.count_num_spikes_per_unit().values()))


if __name__=='__main__': main()
