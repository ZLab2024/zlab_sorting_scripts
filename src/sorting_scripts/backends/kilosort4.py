"""Pinned KS4 backend with the lab's scoped guards and recovery checkpoints."""
from pathlib import Path
from spikeinterface.sorters import run_sorter
from ..kilosort_runtime import kilosort_runtime, resume_clustering


def sort(recording, folder, *, params=None, checkpoint=True):
    """Sort one isolated group; destination must be new, preprocessing is external."""
    folder = Path(folder)
    if folder.exists():
        raise FileExistsError(f'Sorter destination already exists: {folder}')
    params = dict(params or {})
    protected = {'folder', 'recording', 'sorter_name', 'remove_existing_folder', 'delete_recording_dat'}
    if protected & params.keys():
        raise ValueError(f'Reserved sorter parameters: {protected & params.keys()}')
    with kilosort_runtime(folder/'precluster_checkpoint.pt' if checkpoint else None):
        return run_sorter('kilosort4', recording, folder=folder, remove_existing_folder=False,
                          delete_recording_dat=not checkpoint, **params)
