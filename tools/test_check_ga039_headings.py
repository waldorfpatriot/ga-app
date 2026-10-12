#!/usr/bin/env python3
"""Independent scope and source-markup guards for the GA039 layer."""
import unittest
from xml.etree import ElementTree as ET
from check_ga039_headings import prefix_repair, source_reading, reading_blocks

class IndependentHeadingTests(unittest.TestCase):
    def repair(self,old,new,start=0,field='title'):
        return {'old':old,'new':new,'start_codepoint':start,'field':field,'count':1,'evidence':'Scan',
                'passage_id':'ga-039-doc-heading-55','kind':'source_heading_number'}
    def test_only_header_prefix_changes(self):
        self.assertEqual(prefix_repair(self.repair('45^.','452.'),'45^. AN DIE ELTERN'),'452. AN DIE ELTERN')
        text='Erwähnt Brief45^. innerhalb eines Satzes.'
        with self.assertRaises(ValueError):prefix_repair(self.repair('45^.','452.',13,'text'),text)
        with self.assertRaises(ValueError):prefix_repair(self.repair('45^. AN DIE ELTERN','452. Fremder Empfänger'),'45^. AN DIE ELTERN')
        with self.assertRaises(ValueError):prefix_repair(self.repair('45^.','452. Zusatz'),'45^. AN DIE ELTERN')
    def test_source_physical_lines_and_real_br(self):
        atom=ET.fromstring('<p>Erste\nphysische Zeile<br/>Zweite\nphysische Zeile.</p>')
        self.assertEqual(source_reading(atom,'br'),'Erste physische Zeile\nZweite physische Zeile.')
        with self.assertRaises(ValueError):source_reading(atom,'paragraph')
        with self.assertRaises(ValueError):source_reading(atom,'literal')
    def test_utf16_heading_ranges_keep_all_prose(self):
        text='📖 Anfang.\n\n452. AN DIE ELTERN\n\nWeiterer Text.'
        start=text.index('452.');end=text.index('\n\nWeiterer')
        blocks=reading_blocks(text,[{'field':'text','start_codepoint':start,'end_codepoint':end}])
        self.assertEqual([b['kind'] for b in blocks],['prose','heading','prose'])
        self.assertEqual(blocks[1]['start_offset'],start+1)
        self.assertEqual(blocks[1]['end_offset'],end+1)
        with self.assertRaises(ValueError):reading_blocks(text,[{'field':'text','start_codepoint':start,'end_codepoint':end}]*2)

if __name__=='__main__':unittest.main()
