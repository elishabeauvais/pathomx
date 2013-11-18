# -*- coding: utf-8 -*-
import os

from plugins import ImportPlugin

# Import PyQt5 classes
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWebKit import *
from PyQt5.QtNetwork import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebKitWidgets import *
from PyQt5.QtPrintSupport import *


import utils
import csv
import xml.etree.cElementTree as et
from collections import defaultdict

import numpy as np

import ui, db
from data import DataSet


class GEOView( ui.ImportDataView ):

    import_filename_filter = "All compatible files (*.soft);;Simple Omnibus Format in Text (*.soft);;All files (*.*)"
    import_description =  "Open experimental data from downloaded data"

    def __init__(self, plugin, parent, **kwargs):
        super(GEOView, self).__init__(plugin, parent, **kwargs)

       
    # Data file import handlers (#FIXME probably shouldn't be here)
        
    def load_datafile(self, filename):
    
        # Determine if we've got a csv or peakml file (extension)
        fn, fe = os.path.splitext(filename)
        formats = { # Run specific loading function for different source data types
                '.soft': self.load_soft_dataset,
            }
            
        if fe in formats.keys():
            print "Loading... %s" %fe
            self.setWorkspaceStatus('active')

            dso=formats[fe](filename)


            dso.name = os.path.basename( filename )
            self.set_name( dso.name )
            dso.description = 'Imported %s file' % fe  

            self.setWorkspaceStatus('done')
            self.data.put('output',dso) 
            self.render({})

            self.clearWorkspaceStatus()
            
        else:
            print "Unsupported file format."
        
###### LOAD HANDLERS
    '''
^DATABASE = GeoMiame
!Database_name = Gene Expression Omnibus (GEO)
!Database_institute = NCBI NLM NIH
!Database_web_link = http://www.ncbi.nlm.nih.gov/geo
!Database_email = geo@ncbi.nlm.nih.gov
^SERIES = GSE10220
!Series_title = Gene expression profiling of human monocytes and monocyte-derived-macrophages
!Series_geo_accession = GSE10220
!Series_status = Public on Aug 31 2008
!Series_submission_date = Jan 21 2008
...
^PLATFORM = GPL1946
!Platform_data_row_count = 26496
#ID = 
#BLOCK = Block-within array
#COLUMN = Column-within array
#ROW = Row-within array
#INTERNAL_ID = Internal ID
#GENE_SYMBOL = Gene symbol
#GB_LIST = Genbank accession number LINK_PRE:"http://www.ncbi.nlm.nih.gov/nuccore/?term=" DELIMIT:","
#UNIGENE = Unigene ID; LINK_PRE:"http://www.ncbi.nlm.nih.gov/UniGene/clust.cgi?ORG=Hs&CID="
#LOCUS_ID = LocusLink ID
#SPOT_ID = control, buffer, no information, etc.
!platform_table_begin
ID	BLOCK	COLUMN	ROW	INTERNAL_ID	GENE_SYMBOL	GB_LIST	UNIGENE	LOCUS_ID	SPOT_ID
1	1	1	1	65850	FOXN4	NM_213596	75535	121643	
2	1	2	1	73331	FLJ38343	NM_175915	194766	284895	
3	1	3	1	71694	DMRTA1	NM_022160	371976	63951	
4	1	4	1	134423	MYOCD	NM_153604	42128	93649	
5	1	5	1	24633	ZNF409	NM_014894	225975	22830	
6	1	6	1	20891	NKX2-8	NM_014360	234763	26257	
...
!platform_table_end
^SAMPLE = GSM257886
!Sample_title = RNG_Macrophage_Pool2
!Sample_geo_accession = GSM257886
!Sample_status = Public on Aug 31 2008
!Sample_submission_date = Jan 20 2008
!Sample_last_update_date = Jul 28 2008
!Sample_type = RNA
...
!Sample_supplementary_file = ftp://ftp.ncbi.nlm.nih.gov/pub/geo/DATA/supplementary/samples/GSM257nnn/GSM257886/GSM257886.gpr.gz
!Sample_series_id = GSE10220
!Sample_data_row_count = 26496
#ID_REF = 
#VALUE = normalized log ratio of (test/reference)
!sample_table_begin
ID_REF	VALUE
1	-0.049561119
10	-0.569066573
100	0.138019598    
    
    
    '''
    
    def preprocess_soft(self, reader):
        # Preprocess into the chunks (then can manageable process them in turn)
        soft_data = defaultdict( list )
        for row in reader:
            if row[0].startswith('^'): # Control row
                section = row[0]
                continue
            soft_data[ section ].append( row )
        
        return soft_data
            
    
    def get_soft_metadata(self, rows, while_starts_with='!'):

        metadata = {}
    
        for row in rows:
            if not row[0].startswith('!'):
                break
            
            key,value = row[0][1:].split(' = ') # Remove the ! and then split, removing the ' = '
            metadata[ key ] = value
            
        return metadata
    
    def get_soft_data(self, rows, starts, ends):
        headers = False
        data = {} 
        headers_at = False
        for n,row in enumerate(rows):
            if row[0] == starts:
                headers_at = n+1
                start_at = n+2
                break

        if not headers_at:
            return False
        
        headers = rows[headers_at]
        
        for row in rows[start_at:]:
            if row[0] == ends:
                break
                
            data[ row[0] ] = dict( zip(headers, row) )
                
        return data
    
        
    def load_soft_dataset(self, filename): # Load from soft data file for genes
        # SOFT files are a /sort of/ basterdized csv with data in tab-separated columns
        # So, we use the csv reader to get that, accounting for most stuff being single field with 
        # slightly strange identifiers
        
        reader = csv.reader( open( filename, 'rU'), delimiter='\t', dialect='excel')
        
        soft_data = self.preprocess_soft( reader )
        # soft_data now contains lists of sections with ^ markers
        
        database = {}
        dataset = {}
        dataset_data = {}
        subsets = {}
        
        for section, rows in soft_data.items():
        
            if section.startswith('^DATABASE'):
                database = self.get_soft_metadata( rows )

            elif section.startswith('^DATASET'):
                dataset.update( self.get_soft_metadata( rows ) ) # update because seems can be >1 entry to dataset
                data = self.get_soft_data( rows,'!dataset_table_begin','!dataset_table_end')
                dataset_data = data

            elif section.startswith('^SUBSET'):
                key,subset_id = section.split(' = ')
                subsets[subset_id] = self.get_soft_metadata( rows )
                subsets[subset_id]['subset_sample_id'] = subsets[subset_id]['subset_sample_id'].split(',') # Turn to list of ids

        # We now have the entire dataset loaded; but in a bit of a messed up format
        # Build a dataset object to fit and map the data in
        sample_ids = []
        for k, subset in subsets.items():
            sample_ids.extend( subset['subset_sample_id'] )
        sample_ids = sorted( sample_ids ) # Get the samples sorted so we keep everything lined up
        
        print sample_ids
        print subsets
        
        class_lookup = {}
        for class_id, s in subsets.items():
            for s_id in s['subset_sample_id']:
                class_lookup[ s_id ] = "%s (%s)" % ( s['subset_description'] if 'subset_description' in s else '', class_id)
                    
        xdim = len( dataset_data ) # Use first sample to access the gene list
        ydim = len( sample_ids )
        
        # Build dataset object        
        dso = DataSet( size=(xdim, ydim) ) #self.add_data('imported_data', DataSetself) )
        dso.empty(size=(ydim, xdim))
        
        gene_ids = sorted( dataset_data.keys() ) # Get the keys sorted so we keep everything lined up
        
        dso.labels[0] = sample_ids
        dso.classes[0] = [ class_lookup[ s_id ] for s_id in sample_ids ]
        dso.labels[1] = [ dataset_data[gene_id]['IDENTIFIER'] for gene_id in gene_ids ]
        dso.entities[1] = [ self.m.db.get_via_synonym(gene_id) for gene_id in dso.labels[1] ] 
        
        for xn, gene_id in enumerate(gene_ids):
            for yn, sample_id in enumerate(sample_ids):
                
                dso.data[yn,xn] = dataset_data[ gene_id ][sample_id]

        return dso
                


    def load_soft_series_family(self, filename): # Load from soft data file for genes
        # SOFT files are a /sort of/ basterdized csv with data in tab-separated columns
        # So, we use the csv reader to get that, accounting for most stuff being single field with 
        # slightly strange identifiers
        
        reader = csv.reader( open( filename, 'rU'), delimiter='\t', dialect='excel')
        soft_data = self.preprocess_soft( reader )
        
        database = {}
        platform = {}
        samples = {}
        sample_data = {}
        
        for section, rows in soft_data.items():

            if section.startswith('^DATABASE'):
                database = self.get_soft_metadata( rows )

            elif section.startswith('^PLATFORM'):
                platform = self.get_soft_metadata( rows )
                platform_data = self.get_soft_data(rows,'!platform_table_begin','!platform_table_end')

            elif section.startswith('^SAMPLE'):
                key,sample_id = row[0].split(' = ')
                samples[sample_id] = self.get_soft_metadata( rows )
                sample_data[sample_id] = self.get_soft_data(rows,'!sample_table_begin','!sample_table_end')

        # We now have the entire dataseries loaded; but in a bit of a messed up format
        # Build a dataset object to fit and map the data in
        
        xdim = len( platform_data ) # Use first sample to access the gene list
        ydim = len( sample_data )
        
        # Build dataset object        
        dso = DataSet( size=(xdim, ydim) ) #self.add_data('imported_data', DataSetself) )
        dso.empty(size=(ydim, xdim))
        
        sample_ids = sorted( samples.keys() ) # Get the samples sorted so we keep everything lined up
        gene_ids = sorted( platform_data.keys() ) # Get the keys sorted so we keep everything lined up
        
        dso.labels[0] = sample_ids
        dso.labels[1] = [ platform_data[gene_id]['UNIGENE'] for gene_id in gene_ids ]
        dso.entities[1] = [ self.m.db.get_via_unification('UNIGENE',gene_id) for gene_id in dso.labels[1] ] 
        
        for xn, gene_id in enumerate(gene_ids):
            for yn, sample_id in enumerate(sample_ids):
                
                dso.data[yn,xn] = sample_data[ sample_id ][gene_id]['VALUE']

        return dso
                

        

class GEO(ImportPlugin):

    def __init__(self, **kwargs):
        super(GEO, self).__init__(**kwargs)
        self.register_app_launcher( self.app_launcher )

    def app_launcher(self):
        return GEOView( self, self.m )
