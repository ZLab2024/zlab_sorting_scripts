"""MountainSort5 recipe migrated from the Sort_BF notebook."""
from pathlib import Path
from spikeinterface.sorters import run_sorter


def sort(recording, folder, *, profile, params=None):
    """Sort one group after central filtering/whitening; preserve existing output."""
    if Path(folder).exists():
        raise FileExistsError(f'Sorter destination already exists: {folder}')
    supplied = dict(params or {})
    protected = {'folder', 'recording', 'sorter_name', 'remove_existing_folder', 'filter', 'whiten'}
    if protected & supplied.keys():
        raise ValueError(f'Reserved sorter parameters: {protected & supplied.keys()}')
    settings = dict(scheme='2', filter=False, whiten=False,
                    scheme2_phase1_detect_channel_radius=110., scheme2_detect_channel_radius=110.,
                    snippet_mask_radius=110., scheme2_training_recording_sampling_mode='uniform')
    settings.update(supplied)
    return run_sorter('mountainsort5', recording, folder=folder, remove_existing_folder=False, **settings)
