"""Synthetic integration contracts for consolidated probes, imports and runner."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.io import savemat
import spikeinterface as si
from sorting_scripts import pipeline
from sorting_scripts.config import load_config
from sorting_scripts.probes import get_probe, attach_probe
from sorting_scripts.io.osort import load_osort, frames_from_times
from sorting_scripts.lineage import verify_lineage
from sorting_scripts.provenance import writer_lock


class ProbeTests(unittest.TestCase):
    def rec(self, n=8):
        r=si.NumpyRecording(np.arange(200*n,dtype='int16').reshape(200,n),sampling_frequency=30000,
                            channel_ids=[f'wire{i}' for i in range(n)])
        r.set_channel_gains(np.arange(n)+.5); r.set_channel_offsets(np.arange(n))
        return r

    def test_three_presets_and_packaged_dummy(self):
        for name, n, probes in [('deeparray128',128,1),('bf_dummy8',16,2),('bf_single8',16,16),('dummy8_probe.json',8,1)]:
            with self.subTest(name=name):
                raw=self.rec(n); result=attach_probe(raw,name)
                self.assertEqual(len(result.get_probegroup().probes),probes)
                np.testing.assert_array_equal(raw.get_traces(),result.get_traces())
                np.testing.assert_array_equal(raw.channel_ids,result.channel_ids)
                np.testing.assert_array_equal(raw.get_channel_gains(),result.get_channel_gains())
                self.assertEqual(len(np.unique(result.get_property('group'))),probes)
        self.assertEqual(len(get_probe('bf_single8').probes),8)

    def test_no_silent_channel_loss_or_replacement(self):
        raw=self.rec(16)
        with self.assertRaisesRegex(ValueError,'original recording'): attach_probe(raw,'dummy8_probe.json')
        self.assertEqual(raw.get_num_channels(),16)
        wired=attach_probe(raw,'bf_single8')
        with self.assertRaisesRegex(ValueError,'already attached'):attach_probe(wired,'bf_single8')
        self.assertEqual(attach_probe(wired,'bf_single8',replace=True).get_num_channels(),16)

    def test_reordered_map_preserves_acquisition_order_and_groups(self):
        raw=self.rec(8); ids=list(reversed(raw.channel_ids))
        wired=attach_probe(raw,'bf_single8',channel_ids=ids)
        np.testing.assert_array_equal(wired.get_traces(),raw.get_traces())
        np.testing.assert_array_equal(wired.channel_ids,raw.channel_ids)
        np.testing.assert_array_equal(wired.get_property('group'),list(reversed(range(8))))
        with self.assertRaises(ValueError):attach_probe(raw,'bf_single8',channel_ids=['wire0']*8)
        group=get_probe('bf_single8');group.probes[1].device_channel_indices=np.array([0])
        with self.assertRaises(ValueError):attach_probe(raw,group)


class ImportLineageTests(unittest.TestCase):
    def test_osort_samples_gaps_bounds_and_duplicate_events(self):
        np.testing.assert_array_equal(frames_from_times([1000.,1100.,20000.], [1000.,20000.],30000),[0,3,512])
        with self.assertRaises(ValueError):frames_from_times([19000.],[1000.,20000.],30000)
        with self.assertRaises(ValueError):frames_from_times([1001.],[1000.],30000)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'units.mat'
            savemat(path,dict(useNegative=[0,1,2,99999999],assignedNegative=[1,1,2,99999999],
                             newTimestampsNegative=[1000.,1000.,1100.,-999.]))
            sorting=load_osort(path,sampling_frequency=30000,start_time_us=1000.,num_samples=100)
            np.testing.assert_array_equal(sorting.get_unit_spike_train(1),[0,0])
            verify_lineage(sorting,sorting,{1:1,2:2})
            with self.assertRaises(ValueError):load_osort(path,sampling_frequency=30000,start_time_us=1000.,num_samples=2)
            changed=si.NumpySorting.from_unit_dict({1:np.array([0]),2:np.array([3])},30000)
            with self.assertRaises(ValueError):verify_lineage(sorting,changed,{1:1,2:2})

    def test_complete_link_does_not_merge_chains(self):
        from sorting_scripts.merging import complete_link_groups
        self.assertEqual(complete_link_groups([1,2,3],{(1,2):.9,(2,3):.8}),[[1,2]])

    def test_labels_only_preserves_empty_units_and_duplicate_spikes(self):
        from sorting_scripts.analysis import prepare_analyzer
        from sorting_scripts.curation import apply_policy
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            r=si.NumpyRecording(np.random.default_rng(5).normal(size=(30000,8)).astype('float32'),30000)
            r.set_channel_gains(1.);r.set_channel_offsets(0.)
            r=attach_probe(r,'bf_single8').select_channels([0])
            r=r.save(folder=root/'recording',format='binary',n_jobs=1,progress_bar=False)
            sorting=si.NumpySorting.from_unit_dict({1:np.array([1000,1000,3000,4000]),2:np.array([],dtype='int64')},30000)
            analyzer=prepare_analyzer(r,sorting,root/'analyzer',virtual_geometry=True)
            labeled=apply_policy(analyzer,root/'labels',policy='labels_only')
            verify_lineage(sorting,labeled,{1:1,2:2})
            self.assertEqual(labeled.unit_ids.tolist(),[1,2])

    def test_med_header_patch_restores_on_failure(self):
        from importlib.util import find_spec
        if find_spec('dhn_med_py') is None: self.skipTest('Optional MED extra unavailable')
        from sorting_scripts.io import med
        import dhn_med_py
        original=dhn_med_py.MedSession
        with patch.object(med._MedRawIO,'_parse_header',side_effect=ValueError('header fixture')):
            with self.assertRaises(ValueError):med.CleanMedRawIO._parse_header(object.__new__(med.CleanMedRawIO))
        self.assertIs(dhn_med_py.MedSession,original)

    def test_med_extractor_serializes_env_reference_and_reloads_in_fresh_process(self):
        from importlib.util import find_spec
        if find_spec('dhn_med_py') is None: self.skipTest('Optional MED extra unavailable')
        helper=Path(__file__).with_name('_med_serialization_fixture.py')
        with tempfile.TemporaryDirectory() as d:
            fixture=Path(d)/'extractor.json'
            subprocess.run([sys.executable,str(helper),'write',str(fixture)],check=True,capture_output=True)
            subprocess.run([sys.executable,str(helper),'read',str(fixture)],check=True,capture_output=True)

    def test_med_module_optional_import_fresh_process(self):
        code='from sorting_scripts.io.med import MedRecordingExtractor; print(MedRecordingExtractor.__module__)'
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True)
        self.assertIn('sorting_scripts.io.med',result.stdout)


class BackendContractTests(unittest.TestCase):
    def test_ms5_explicit_recipe_and_no_overwrite(self):
        from sorting_scripts.backends import mountainsort5
        with tempfile.TemporaryDirectory() as d, patch.object(mountainsort5,'run_sorter',return_value='sorted') as run:
            path=Path(d)/'new'
            mountainsort5.sort(object(),path,profile='bf_bundle_ms5',params={'detect_threshold':5})
            self.assertFalse(run.call_args.kwargs['filter'])
            self.assertFalse(run.call_args.kwargs['whiten'])
            self.assertFalse(run.call_args.kwargs['remove_existing_folder'])
            path.mkdir();(path/'evidence').write_text('keep')
            with self.assertRaises(FileExistsError):mountainsort5.sort(object(),path,profile='bf_bundle_ms5')
            self.assertEqual((path/'evidence').read_text(),'keep')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        rec=si.NumpyRecording(np.random.default_rng(0).normal(0,5,(12000,8)).astype('float32'),sampling_frequency=30000)
        rec.set_channel_gains(1.);rec.set_channel_offsets(0.)
        rec.save(folder=self.root/'input',format='binary',verbose=False)
        self.config={'input':{'format':'binary_folder','path':str(self.root/'input')},
                     'probe':{'preset':'bf_single8'},
                     'sorting':{'backend':'mountainsort5','profile':'bf_single_wire'},
                     'curation':{'policy':'none'},'output':{'root':str(self.root/'runs')}}

    def fake_sort(self,rec,folder,**kwargs):
        self.assertEqual(rec.get_num_channels(),1)
        return si.NumpySorting.from_unit_dict({7:np.array([1000,2000,3000,4000,5000,6000])},30000)

    def test_config_and_validation_write_nothing(self):
        with patch.object(pipeline,'find_spec',return_value=object()):
            result=pipeline.validate(self.config)
        self.assertEqual(len(result['groups']),8)
        self.assertFalse((self.root/'runs').exists())
        bad=json.loads(json.dumps(self.config));bad['input']['typo']=1
        with self.assertRaises(ValueError):load_config(bad)
        bad=json.loads(json.dumps(self.config));bad['output']['root']=str(self.root/'input'/'runs')
        with self.assertRaises(ValueError):load_config(bad)

    def test_real_analyzer_roundtrip_and_readonly_inspection(self):
        from sorting_scripts.inspection import inspect_analyzer
        from sorting_scripts.provenance import tree_hashes
        with patch.object(pipeline,'find_spec',return_value=object()),patch.object(pipeline.backends,'sort',side_effect=self.fake_sort) as backend:
            run=pipeline.run(self.config)
        self.assertEqual(backend.call_count,8)
        state=pipeline.status(run);self.assertEqual(state['status'],'complete')
        analyzer_path=run/state['outputs']['analyzer']
        before=tree_hashes(analyzer_path)
        analyzer=inspect_analyzer(analyzer_path,unit_id=0,output=self.root/'unit.png')
        self.assertEqual(analyzer.get_num_units(),8)
        self.assertEqual(before,tree_hashes(analyzer_path))
        self.assertTrue((self.root/'unit.png').is_file())
        import pandas as pd
        table=pd.read_csv(run/state['outputs']['results']/'unit_map.csv')
        self.assertEqual(table.unit_id.tolist(),list(range(8)))
        self.assertEqual(analyzer.sorting.get_property('sorting_group').tolist(),list(range(8)))
        self.assertTrue(analyzer.is_sparse())
        self.assertEqual(analyzer.sparsity.mask.sum(axis=1).tolist(),[1]*8)
        with self.assertRaisesRegex(ValueError,'Completed'):pipeline.run(resume=run)

    def test_resume_reuses_complete_groups_preserves_failed_attempts(self):
        calls=[]
        def fail(rec,folder,**kwargs):
            calls.append(folder)
            if len(calls)==3:
                folder.mkdir();(folder/'failed.txt').write_text('preserve')
                raise RuntimeError('synthetic failure')
            return self.fake_sort(rec,folder,**kwargs)
        with patch.object(pipeline,'find_spec',return_value=object()),patch.object(pipeline.backends,'sort',side_effect=fail):
            with self.assertRaises(RuntimeError):pipeline.run(self.config)
            run=next((self.root/'runs').iterdir())
            self.assertEqual(len(pipeline.status(run)['groups']),2)
            failed=next(run.rglob('failed.txt'))
            with patch.object(pipeline.backends,'sort',side_effect=self.fake_sort) as backend:
                pipeline.run(resume=run)
            self.assertEqual(backend.call_count,6)
        self.assertEqual(failed.read_text(),'preserve')
        self.assertEqual(pipeline.status(run)['status'],'complete')

    def test_resume_rejects_changed_inputs_and_locks(self):
        with patch.object(pipeline,'find_spec',return_value=object()),patch.object(pipeline.backends,'sort',side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):pipeline.run(self.config)
            run=next((self.root/'runs').iterdir())
            with writer_lock(run):
                with self.assertRaises(FileExistsError):pipeline.run(resume=run)
            (self.root/'input'/'new.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'identity differs'):pipeline.run(resume=run)

    def test_all_empty_outputs_have_maps_and_no_analyzer(self):
        def empty(rec,folder,**kwargs):
            return si.NumpySorting.from_unit_dict({},30000)
        with patch.object(pipeline,'find_spec',return_value=object()),patch.object(pipeline.backends,'sort',side_effect=empty):
            folder=pipeline.run(self.config)
        state=pipeline.status(folder)
        self.assertEqual(state['status'],'complete')
        self.assertIsNone(state['outputs']['analyzer'])
        import pandas as pd
        frame=pd.read_csv(folder/state['outputs']['results']/'unit_map.csv')
        self.assertEqual(list(frame.columns),['unit_id','group','group_unit_id','channel_ids','bundle'])

    def test_cli_status_and_no_gui_import(self):
        from sorting_scripts.cli import main
        (self.root/'manifest.json').write_text('{"status":"failed"}')
        with contextlib.redirect_stdout(io.StringIO()) as out:main(['status','--run',str(self.root)])
        self.assertEqual(json.loads(out.getvalue())['status'],'failed')
        code='import sorting_scripts.inspection; import sys; assert "spikeinterface_gui" not in sys.modules'
        subprocess.run([sys.executable,'-c',code],check=True)


if __name__=='__main__': unittest.main()
