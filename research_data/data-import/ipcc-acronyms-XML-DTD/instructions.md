# Instructions for IPCC acronyms XML import

## Series (Property in Wikibase) / Report (in XML) code and QID

SR1.5  - Q10 - Special Report on Global Warming of 1.5 degrees C

SRCCL  - Q35 - Special Report on Climate Change and Land

SROCC  - Q57 - Special Report on the Ocean and Cryosphere in a Changing Climate

SYR    - Q189 - Synthesis Report 

WGI    - Q77 - Working Group I: The Physical Science Basis 

WGII   - Q106 - Working Group II: Impacts, Adaptation and Vulnerability #

WGIII  - Q150 - Working Group III: Mitigation of Climate Change 

## Instructions

The project is to import acronyms into Wikibase and associate them to the items from the Series Property.

Creat a new Property for Acronyms. Label is acronym (code). Description is 'Acronym for: <first description>'

Statement instance of (P1) Acronym. Add Qualifier (P19) 'IPCC AR6'

Statement Part of (P3) - List Series (Report)

Statement Definition (P13) - List Descriptions, one entry per description. Add Qualifier (P19) 'IPCC AR6' for each entry


