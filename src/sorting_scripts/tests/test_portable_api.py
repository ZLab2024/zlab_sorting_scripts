"""Synthetic contracts for multi-project imports, additional inputs and archiving."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import spikeinterface as si
from sorting_scripts import load_recording
from sorting_scripts.config import load_config
from sorting_scripts.io import list_streams
from sorting_scripts.io.generic import reader_arguments
from sorting_scripts.probes import make_deeparray128, make_linear_probe, get_probe, save_probe
from sorting_scripts.provenance import input_identity

ROOT = Path(__file__).resolve().parents[3]


class PortableInputTests(unittest.TestCase):
    def test_raw_binary_samples_scaling_and_runner_validation(self):
        from sorting_scripts.pipeline import validate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw = root/'raw'; raw.mkdir()
            path = raw/'traces.raw'
            samples = np.arange(200*8, dtype='int16').reshape(200, 8)
            samples.tofile(path)
            kwargs = dict(dtype='int16', num_channels=8, gain_to_uV=.195, offset_to_uV=0.)
            recording = load_recording(path, format='binary', sampling_frequency=30000, reader_kwargs=kwargs)
            np.testing.assert_array_equal(recording.get_traces(), samples)
            np.testing.assert_allclose(recording.get_channel_gains(), .195)
            config = {'input': {'format': 'binary', 'path': str(path), 'sampling_frequency':30000, 'reader_kwargs':kwargs},
                      'output': {'root':str(root/'runs')}}
            summary = validate(config, check_backend=False)
            self.assertEqual(len(summary['groups']), 8)
            self.assertFalse((root/'runs').exists())
            with self.assertRaises(ValueError):
                load_recording(path, format='binary', sampling_frequency=20000,
                               reader_kwargs={**kwargs,'sampling_frequency':30000})

    def test_generic_reader_binding_streams_and_type_contract(self):
        import spikeinterface.extractors as extractors
        recording = si.NumpyRecording(np.zeros((100,8),dtype='int16'),30000)
        calls = []
        def reader(folder_path, stream_id=None, load_sync_channel=False):
            calls.append((folder_path,stream_id,load_sync_channel))
            return recording
        with patch.object(extractors,'read_spikeglx',reader):
            result = load_recording('/data/source',format='spikeinterface',extractor='spikeglx',
                                    stream_id='imec0.ap',reader_kwargs={'load_sync_channel':False})
            self.assertIs(result,recording)
            self.assertEqual(calls,[('/data/source','imec0.ap',False)])
            with self.assertRaises(ValueError):reader_arguments('/data','spikeglx',reader_kwargs={'folder_path':'/other'})
        for name in ['os.system','_private','unknown_source']:
            with self.assertRaises(ValueError):reader_arguments('/data',name)
        def not_recording(folder_path):return si.NumpySorting.from_unit_dict({},30000)
        with patch.object(extractors,'read_spikeglx',not_recording):
            with self.assertRaises(TypeError):load_recording('/data',format='spikeinterface',extractor='spikeglx')
        with patch.object(extractors,'get_neo_streams',return_value=(['amplifier'],['0'])):
            self.assertEqual(list_streams('/data',format='neuralynx'),[{'stream_id':'0','name':'amplifier'}])

    def test_config_options_and_reader_side_input_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'data'/'trace.bin').write_bytes(b'raw')
            (root/'settings.xml').write_text('version1')
            mapping = {'input':{'format':'spikeinterface','extractor':'openephys','path':'data',
                                'reader_kwargs':{'settings_file':'settings.xml'}},'output':{'root':'runs'}}
            configpath=root/'session.json';configpath.write_text(json.dumps(mapping))
            config=load_config(configpath)
            self.assertEqual(config['input']['reader_kwargs']['settings_file'],str(root/'settings.xml'))
            original=input_identity(config)
            (root/'settings.xml').write_text('version2')
            self.assertNotEqual(input_identity(config),original)
            mapping['input']['reader_kwargs']={'password':'should-not-persist'}
            with self.assertRaisesRegex(ValueError,'Credentials'):load_config(mapping)
            with self.assertRaises(ValueError):load_recording(root/'data',format='intan',reader_kwargs={'x':1})

    def test_external_binary_folder_data_fingerprinted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache=root/'cache';cache.mkdir()
            external=root/'external.raw';external.write_bytes(b'first')
            (cache/'binary.json').write_text(json.dumps({'kwargs':{'file_paths':[str(external)]},'relative_paths':False}))
            config=load_config({'input':{'format':'binary_folder','path':str(cache)},'output':{'root':str(root/'runs')}})
            before=input_identity(config);external.write_bytes(b'changed')
            self.assertNotEqual(before,input_identity(config))


class PortableProbeTests(unittest.TestCase):
    def test_generation_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'linear.json'
            probe=make_linear_probe(8,pitch_um=25)
            save_probe(probe,path)
            self.assertEqual(get_probe(path).probes[0].get_contact_count(),8)
            before=path.read_bytes()
            with self.assertRaises(FileExistsError):save_probe('bf_single8',path)
            self.assertEqual(path.read_bytes(),before)
            generated=make_deeparray128();packaged=get_probe('deeparray128').probes[0]
            np.testing.assert_array_equal(generated.contact_positions,packaged.contact_positions)
            np.testing.assert_array_equal(generated.device_channel_indices,packaged.device_channel_indices)
        for n in [True,0,-1,2.5]:
            with self.assertRaises(ValueError):make_linear_probe(n)

    def test_prb_and_probe_cli(self):
        from sorting_scripts.cli import main
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            prb=root/'probe.prb';prb.write_text('channel_groups = {0: {"channels": [0,1], "geometry": {0:(0,0),1:(0,25)}}}')
            self.assertEqual(get_probe(prb).probes[0].get_contact_count(),2)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                main(['probe','--preset','bf_single8','--channels','16','--output',str(root/'bf.json')])
            self.assertEqual(len(get_probe(json.loads(out.getvalue())['probe']).probes),16)

    def test_manual_curation_has_no_patient_path_assumptions(self):
        from sorting_scripts.curation import apply_manual_curation
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'analyzer';source.mkdir()
            analyzer=Mock(folder=source);curated=Mock()
            with patch('spikeinterface.curation.apply_curation',return_value=curated) as apply:
                apply_manual_curation(analyzer,{'version':'1'},root/'new.zarr')
                apply.assert_called_once_with(analyzer,curation_dict_or_model={'version':'1'},merging_mode='hard')
                curated.save_as.assert_called_once_with(format='zarr',folder=root/'new.zarr')
                with self.assertRaises(ValueError):apply_manual_curation(analyzer,{},source/'nested.zarr')


class ArchiveAndCompatibilityTests(unittest.TestCase):
    def test_archive_integrity_and_legacy_import_identity(self):
        manifest=json.loads((ROOT/'archive/manifest.json').read_text())
        for row in manifest['files']:
            archived=ROOT/row['archived']
            self.assertEqual(hashlib.sha256(archived.read_bytes()).hexdigest(),row['sha256'])
        from sorting_scripts import zsort
        from sorting_scripts.legacy import zsort as legacy
        from sorting_scripts.gui import launch_curation_gui
        self.assertIs(zsort,legacy)
        self.assertIs(zsort.launch_curation_gui,launch_curation_gui)

    def test_resume_rejects_added_artifact(self):
        from sorting_scripts.pipeline import _check_artifacts
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);attempt=root/'attempt';attempt.mkdir()
            (attempt/'sorting.json').write_text('{}')
            hashes={'attempt/sorting.json':hashlib.sha256(b'{}').hexdigest()}
            _check_artifacts(root,hashes,attempt)
            (attempt/'unexpected.npy').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'artifact set'):_check_artifacts(root,hashes,attempt)


if __name__ == '__main__':unittest.main()
