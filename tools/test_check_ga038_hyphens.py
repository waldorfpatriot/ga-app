#!/usr/bin/env python3
"""Negative scope guards for the independent GA038 source-hyphen checker."""
from copy import deepcopy
import unittest
from check_ga038_hyphens import inspect_replacement, printed_word


def entry(old, new, kind='physical_word_hyphen'):
    return {'field':'text','old':old,'new':new,'kind':kind,'count':1,'evidence':'Originaldruck'}


class IndependentHyphenTests(unittest.TestCase):
    def test_real_compounds_and_historical_ck(self):
        inspect_replacement(entry('National-Lite-ratur','National-Literatur'))
        inspect_replacement(entry('schik-ken','schicken','historical_ck_hyphen'))
        for old,new,kind in [('schik-ken','schicken','physical_word_hyphen'),
                             ('National-Lite-ratur','NationalLiteraturen','physical_word_hyphen'),
                             ('Geist- und','Geistund','physical_word_hyphen'),
                             ('National-\nLiteratur','NationalLiteratur','physical_gap_after_lexical_hyphen')]:
            with self.subTest(old=old):
                with self.assertRaises(ValueError):inspect_replacement(entry(old,new,kind))

    def test_only_the_two_literal_printed_continuations(self):
        valid=[('ga-038-doc-heading-10','hin-','hinlenkten?',66,'lenkten?'),
               ('ga-038-doc-heading-51','unterzubrin-','unterzubringen sein.',189,'gen sein.')]
        for pid,old,new,page,missing in valid:
            repair=entry(old,new,'source_word_continuation')
            repair.update(passage_id=pid,continuation_witness={'page':page,'missing_text':missing,'reviewed':True})
            inspect_replacement(repair)
            for field,value in [('passage_id','foreign'),('new',new+' Zusatz'),('count',2)]:
                bad=deepcopy(repair);bad[field]=value
                with self.assertRaises(ValueError):inspect_replacement(bad)
            bad=deepcopy(repair);bad['continuation_witness']['page']=page+1
            with self.assertRaises(ValueError):inspect_replacement(bad)
            bad=deepcopy(repair);bad['continuation_witness']['reviewed']=False
            with self.assertRaises(ValueError):inspect_replacement(bad)

    def test_printed_small_caps_spacing_and_lexical_hyphens(self):
        for old,before,after,wanted in [
            ('Hör-nes','bearbeitet); H ö R -','NES, Elemente der Paläontologie','HöR-NES'),
            ('Ita-lia',"Carta geologica d'Ita-",'lia, 1 : 1 111 111','Ita-lia'),
            ('Be-wußt-Seiendem','Identität von Be-','wußt-Seiendem und Seiendem','Be-wußt-Seiendem'),
            ('National-Lite-ratur','Deutscher National-Lite-','ratur» erscheinen.','National-Lite-ratur')]:
            repair=entry(old,old.replace('-',''))
            pair={'lines':[{'text':before},{'text':after}]}
            self.assertEqual(printed_word(repair,pair),wanted)
        with self.assertRaises(ValueError):
            printed_word(entry('National-Lite-ratur','National-Literatur'),
                         {'lines':[{'text':'Fremder Lite-'},{'text':'ratur'}]})


if __name__ == '__main__':unittest.main()
