import copy
import unittest
import test_analysis
from vps_pipeline.analysis import AnalysisError,validate_submission,create_work_package


class CatalogMappingTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_analysis.AnalysisTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.envelope=self.fixture.envelope()
        self.mapping={'confirmed':True,'item_id':'12345-1','post_object_count':1,'reviewed_object_count':1,'entry_kind':'measured_vps','public_label':'Synthetic catalog object'}

    def test_mapping_optional_and_valid_mapping_preserved(self):
        for value in [None,self.mapping]:
            e=copy.deepcopy(self.envelope);e['catalog_mapping']=value
            result=validate_submission(self.fixture.manifest_path,e)
            self.assertEqual(result['submitted_envelope']['catalog_mapping'],value)

    def test_mapping_identity_and_counts_cannot_be_guessed_or_ambiguous(self):
        mutations=[{'confirmed':False},{'confirmed':1},{'item_id':'99999-1'},{'item_id':'12345-2'},
                   {'post_object_count':0},{'post_object_count':True},{'post_object_count':101},
                   {'reviewed_object_count':2},{'reviewed_object_count':True},
                   {'entry_kind':{}},{'entry_kind':'independent_machine'},{'extra':'unapproved'}]
        for change in mutations:
            with self.subTest(change=change):
                e=copy.deepcopy(self.envelope);e['catalog_mapping']=self.mapping|change
                with self.assertRaises(AnalysisError):validate_submission(self.fixture.manifest_path,e)

    def test_mapping_labels_cannot_send_paths_addresses_or_markup(self):
        for label in ['/home/private','C:\\private\\review','203.0.113.25','2001:db8::1','<script>alert(1)</script>','https://example.com','private@example.com']:
            with self.subTest(label=label):
                e=copy.deepcopy(self.envelope);e['catalog_mapping']=self.mapping|{'public_label':label}
                with self.assertRaises(AnalysisError):validate_submission(self.fixture.manifest_path,e)

    def test_exact_multiobject_target_is_explicitly_declared_not_fanned_out(self):
        e=copy.deepcopy(self.envelope);e['catalog_mapping']=self.mapping|{'item_id':'12345-2','post_object_count':2}
        result=validate_submission(self.fixture.manifest_path,e)
        self.assertEqual(result['submitted_envelope']['catalog_mapping']['item_id'],'12345-2')
        self.assertEqual(result['submitted_envelope']['catalog_mapping']['reviewed_object_count'],1)
