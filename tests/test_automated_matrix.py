import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.run_camera_matrix import plan_targets,workspace_path,markdown_report
from tools.camera_matrix import attach_automated_matrix


def camera(model='70D',available=True):
    return {'model':model,'qemu_model':model,'module_profiles':[{'model':model,'firmware':'1.1.2','native_raw':False}],
            'firmware_inputs':{'112':{'available':available,'files':[]}}}


class AutomatedMatrixTest(unittest.TestCase):
    def test_runtime_initialization_does_not_promote_raw_or_hardware(self):
        row={'model':'70D','module_profiles':[{'model':'70D','firmware':'1.1.2'}],
             'emulator_boot':'not_run','module_loaded_in_emulator':'not_verified',
             'raw_capture_in_emulator':'not_verified','candidate_hardware_test':'not_tested'}
        report={'models':[row],'counts':{}}
        observation={'kind':'automated-universal-module-matrix','hardware_test':False,'module':{'sha256':'same'},
            'targets':[{'target':'70D.112','model':'70D','firmware':'1.1.2','status':'emulator_limit_no_preview_delivery',
                'module_fixture':{'verified':True,'canon_liveview_delivery':False},
                'blockers':[],'runtime':{'ml_startup_observed':True,'module_initialization_observed':True,
                    'preview_frames':0,'effect_off_cleanup_observed':True}}]}
        attach_automated_matrix(report,observation,{'legacy':'same'})
        self.assertEqual(row['module_loaded_in_emulator'],'initialization_observed')
        self.assertEqual(row['raw_capture_in_emulator'],'not_verified')
        self.assertEqual(row['candidate_hardware_test'],'not_tested')
        self.assertEqual(report['counts']['synthetic_loaded_module_fixture_profiles_verified'],1)
        with self.assertRaisesRegex(ValueError,'different module'):
            attach_automated_matrix(report,observation,{'legacy':'changed'})
        observation['targets'][0]['runtime']['native_raw_capture_verified']=True
        with self.assertRaisesRegex(ValueError,'cannot attest native capture'):
            attach_automated_matrix(report,observation,{'legacy':'same'})

    def test_missing_roms_do_not_require_a_bundle_or_suppress_other_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=plan_targets({'models':[camera(available=False),camera('100D')]},root,root)
            self.assertEqual([r['status'] for r in rows],['skipped_missing_roms','skipped_missing_core_card_bundle'])
            self.assertEqual(len(rows),2)

    def test_invalid_bundle_does_not_stop_the_rest_of_the_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'70D.112.json').write_text('{broken')
            rows=plan_targets({'models':[camera(),camera('100D',False)]},root,root)
            self.assertEqual([r['status'] for r in rows],['skipped_invalid_core_card_bundle','skipped_missing_roms'])

    def test_matching_bundle_required_including_hashes_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=b'cohort';(root/'input').write_bytes(data)
            bundle={'target':'70D.112','canon_id':'K325','symbol_name':'70D_112.sym',
                    'artifacts':{n:{'path':'input','sha256':hashlib.sha256(data).hexdigest()} for n in ('core','autoexec','symbols','sd','cf')}}
            path=root/'70D.112.json';path.write_text(json.dumps(bundle))
            self.assertEqual(plan_targets({'models':[camera()]},root,root)[0]['status'],'ready')
            (root/'input').write_bytes(b'changed')
            self.assertEqual(plan_targets({'models':[camera()]},root,root)[0]['status'],'skipped_invalid_core_card_bundle')
            bundle['target']='EOSM.202';path.write_text(json.dumps(bundle))
            self.assertIn('target mismatch',plan_targets({'models':[camera()]},root,root)[0]['blockers'][0])

    def test_paths_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'inside workspace'):
                workspace_path('../elsewhere',Path(directory))

    def test_excluded_models_do_not_become_emulator_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            row=camera();row['module_profiles']=[]
            self.assertEqual(plan_targets({'models':[row]},Path(directory),Path(directory)),[])

    def test_unmeasured_render_and_capture_are_explicit(self):
        report={'module':{'sha256':'one'},'targets':[{'target':'70D.112','status':'emulator_limit_no_preview_delivery',
                'source_abi':'checked_fields_match','runtime':{'module_initialization_observed':True,'liveview_flag':True,'preview_frames':0}}]}
        result=markdown_report(report)
        self.assertIn('0 | not_run',result)
        self.assertIn('Hardware validation remains required',result)
        report['targets'][0]['module_fixture']={'verified':True}
        result=markdown_report(report)
        self.assertIn('0 | not_run | 44 layouts + corruption rejection',result)


if __name__=='__main__':unittest.main()
