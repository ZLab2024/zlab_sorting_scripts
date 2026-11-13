"""Exercise extractor reconstruction plumbing without opening a native MED file."""
import os,sys,json
from unittest.mock import patch
import numpy as np
import spikeinterface as si
from spikeinterface.core import BaseRecording, NumpyRecording
from sorting_scripts.io import med

def fake_init(self,stream_id=None,stream_name=None,**kwargs):
    BaseRecording.__init__(self,30000,np.array(['wire']),np.dtype('int16'))
    source=NumpyRecording(np.arange(20,dtype='int16').reshape(-1,1),30000)
    self.add_recording_segment(source._recording_segments[0])
    self.stream_id=stream_id;self.stream_name=stream_name
    self._kwargs=dict(kwargs)

os.environ['ZLAB_TEST_MED_PASSWORD']='synthetic-only-secret'
with patch.object(med._NeoBaseRecordingExtractor,'__init__',fake_init):
    if sys.argv[1]=='write':
        recording=med.MedRecordingExtractor('unused',password_env='ZLAB_TEST_MED_PASSWORD',stream_id='0')
        data=recording.to_dict(recursive=True)
        serialized=json.dumps(data)
        assert 'synthetic-only-secret' not in serialized
        assert '"password"' not in serialized
        open(sys.argv[2],'w').write(serialized)
    else:
        recording=si.load(json.load(open(sys.argv[2])))
        assert recording.get_traces().ravel().tolist()==list(range(20))
        assert recording._kwargs['password_env']=='ZLAB_TEST_MED_PASSWORD'
        print('Fresh-process MED extractor reconstruction passed (stubbed decoder)')
