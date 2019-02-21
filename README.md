# CHAOS Challenge
The chaos challenge can be found here: https://chaos.grand-challenge.org/

## What is here
The script `build_chaos_mri_dataset.py` converts the dataset as given by the organizers to another of medical images.
As given, the dataset consists of single dicom files, which have anonimized dicom files, which all have different
InstanceUIDs making these hard to read with standard tools. For the T1 sequence, the separation of the in-phase and
out-phase image is done using the echo time from the dicom header. Next to that the masks are given als PNG files.
This tool converts these to a new mask format with the following values:

`
MAPPING = {
    0: 'background',
    1: 'liver',
    2: 'right kidney',
    3: 'left kidney',
    4: 'spleen'
}`