"""Corrupt-safe MED reader migrated from Sort_BF.

Passwords resolve from an environment variable at open/reload time and are not
stored in extractor kwargs. Cache sequentially before random-access sorting.
Header parsing uses a process-local lock around the inherited Neo adapter hook.
"""
import os
import threading
_HEADER_LOCK = threading.RLock()


def _password(name):
    if name not in os.environ:
        raise ValueError(f'Set environment variable {name} before opening MED')
    return os.environ[name]

def _channel_dir(meta: dict) -> str:
    """Return the ``.ticd`` directory base name for a channel's metadata."""
    return os.path.basename(meta["path"]).rsplit(".ticd", 1)[0]


def _is_corrupt(meta: dict) -> bool:
    """A channel is corrupt if its stored name != its on-disk directory name."""
    return _channel_dir(meta) != meta["channel_name"]


def _filtered_med_session_class():
    """A ``MedSession`` subclass that deactivates corrupt channels on open."""
    from dhn_med_py import MedSession as _BaseMedSession

    class _FilteredMedSession(_BaseMedSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for entry in list(self.session_info["channels"]):
                meta = entry["metadata"]
                if _is_corrupt(meta):
                    self.set_channel_inactive(_channel_dir(meta))

        def set_major_dimension(self, dimension):
            if hasattr(self, "data_matrix"):
                self.data_matrix.major_dimension = dimension
            else:
                super().set_major_dimension(dimension)

        def set_reference_channel(self, channel):
            if hasattr(self, "data_matrix"):
                self.reference_channel = channel
            else:
                super().set_reference_channel(channel)

        def set_channel_inactive(self, channel):
            if hasattr(self, "data_matrix"):
                if channel == "all":
                    channel = [entry["metadata"]["channel_name"] for entry in self.session_info["channels"]]
                self.set_channel_active(channel, False)
            else:
                super().set_channel_inactive(channel)

        def read_by_index(self, *args, **kwargs):
            read_data = super().read_by_index(*args, **kwargs)
            if isinstance(read_data, dict):
                self.data = read_data
                return self.data["channels"]
            if read_data is None:
                return self.data["channels"]
            self.data = {"channels": [{"data": channel} for channel in read_data]}
            return read_data

    return _FilteredMedSession


try:  # Optional dependencies; imported only when MED is requested.
    from neo.rawio.medrawio import MedRawIO as _MedRawIO

    class CleanMedRawIO(_MedRawIO):
        """``MedRawIO`` that transparently drops corrupt channels (e.g. parity).

        Neo's ``_parse_header`` references every channel and the native medlib
        aborts on a channel whose stored name does not match its directory. We
        temporarily swap the ``MedSession`` it imports for one that deactivates
        those channels on open, so the rest of Neo's parsing runs unchanged.
        """

        def _parse_header(self):
            import dhn_med_py

            with _HEADER_LOCK:
                original = dhn_med_py.MedSession
                try:
                    dhn_med_py.MedSession = _filtered_med_session_class()
                    super()._parse_header()
                finally:
                    dhn_med_py.MedSession = original

    # Register so ``getattr(neo.rawio, "CleanMedRawIO")`` works on reload.
    import neo.rawio as _neo_rawio

    _neo_rawio.CleanMedRawIO = CleanMedRawIO

    from spikeinterface.extractors.neoextractors.neobaseextractor import (
        NeoBaseRecordingExtractor as _NeoBaseRecordingExtractor,
    )

    class MedRecordingExtractor(_NeoBaseRecordingExtractor):
        """SpikeInterface recording backed by Neo's MED reader (corrupt-safe)."""

        NeoRawIOClass = "CleanMedRawIO"

        def __init__(
            self,
            dirname,
            password_env: str = "MED_PASSWORD",
            stream_id=None,
            stream_name=None,
            keep_original_times: bool = False,
            all_annotations: bool = False,
            use_names_as_ids: bool = True,
        ):
            password = _password(password_env)
            neo_kwargs = self.map_to_neo_kwargs(dirname, password, keep_original_times)
            _NeoBaseRecordingExtractor.__init__(
                self,
                stream_id=stream_id,
                stream_name=stream_name,
                all_annotations=all_annotations,
                use_names_as_ids=use_names_as_ids,
                **neo_kwargs,
            )
            self._kwargs.pop("password", None)
            self._kwargs.update(
                {
                    "dirname": str(dirname),
                    "password_env": password_env,
                    "all_annotations": all_annotations,
                    "use_names_as_ids": use_names_as_ids,
                    "stream_id": self.stream_id,
                    "stream_name": self.stream_name,
                    "keep_original_times": keep_original_times,
                }
            )

        @classmethod
        def map_to_neo_kwargs(cls, dirname, password="", keep_original_times=False):
            return {
                "dirname": str(dirname),
                "password": password,
                "keep_original_times": keep_original_times,
            }

except ImportError:  # Optional MED/Neo dependencies absent
    CleanMedRawIO = None
    MedRecordingExtractor = None


def read_med_recording(path, *, password_env='MED_PASSWORD', sampling_frequency=None, stream_id=None):
    """Return a lazy serializable recording; select ambiguous streams explicitly.

    sampling_frequency is checked against the opened stream, including single-stream
    sessions. No gain is inferred from a different channel. Discontinuities remain
    segments and the central runner rejects multisegment input pending explicit policy.
    """
    if MedRecordingExtractor is None:
        raise ImportError('Install the med extra (dhn-med-py and neo)')
    password = _password(password_env)
    if stream_id is None:
        names, ids = MedRecordingExtractor.get_streams(path, password=password)
        if len(ids) != 1:
            raise ValueError(f'Select stream_id explicitly; available MED streams: {list(zip(ids, names))}')
        stream_id = ids[0]
    recording = MedRecordingExtractor(str(path), password_env=password_env, stream_id=stream_id)
    if sampling_frequency is not None and recording.get_sampling_frequency() != sampling_frequency:
        raise ValueError('MED stream sampling frequency differs from requested rate')
    return recording
