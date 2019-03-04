# encoding: utf-8
__author__ = 'Jonas Teuwen'
import os
import sys
import re
import numpy as np
import PIL.Image
import argparse

from tqdm import tqdm
from glob import glob
import SimpleITK as sitk
from collections import defaultdict


# Mapping
# 0 is background
# 1 is liver
# 2 is right kidney
# 3 is left kidney
# 4 is spleen


def class_mapping(input_value):
    if 55 < input_value <= 70:
        return 1
    elif 110 < input_value <= 135:
        return 2
    elif 175 < input_value <= 200:
        return 3
    elif 240 < input_value <= 255:
        return 4
    else:
        return 0


def parse_args():
    """Parse input arguments"""
    parser = argparse.ArgumentParser(description='Parse CHAOS dataset')
    parser.add_argument(
        'modality',
        help='modality, either MR or CT',)
    parser.add_argument(
        'root_dir',
        help='root to data',)
    parser.add_argument(
        'write_to',
        help='folder to write output to', )

    return parser.parse_args()


def get_patients(path):
    patients = []
    regex = '^\d+$'
    for x in os.listdir(path):
        if re.match(regex, x):
            patients.append(x)

    return patients


def get_masks(gt_images, vol_img, mask_name):
    all_masks = []
    # I need to do this for the CT masks, the seem to be flipped.
    if mask_name == 'CT':
        gt_images = gt_images[::-1]
    gt_arr = np.stack([np.asarray(PIL.Image.open(_)) for _ in gt_images])
    unique_values_mask = np.unique(gt_arr)
    gt_mask = np.zeros_like(gt_arr).astype(np.uint8)
    for unique_value in unique_values_mask:
        if mask_name == 'liver':
            gt_mask[gt_arr.astype(np.int) == 1] = 1
        else:
            gt_mask[gt_arr == unique_value] = class_mapping(unique_value)
    gt_sitk_mask = sitk.GetImageFromArray(gt_mask)
    gt_sitk_mask.SetOrigin(vol_img.GetOrigin())
    gt_sitk_mask.SetDirection(vol_img.GetDirection())
    gt_sitk_mask.SetSpacing(vol_img.GetSpacing())
    all_masks.append((mask_name, gt_sitk_mask))
    return all_masks


def get_mri_images_from_patient(patient_path):
    all_images = []
    for sequence_type in ['T1DUAL', 'T2SPIR']:
        dicoms = os.path.join(patient_path, sequence_type, 'DICOM_anon')
        dcm_images = glob(os.path.join(dicoms, '**', 'IMG*.dcm'), recursive=True)
        gt = os.path.join(patient_path, sequence_type, 'Ground')
        gt_images = glob(os.path.join(gt, '*'))
        gt_images = sorted(gt_images, key=lambda x: int(os.path.basename(x).split('-')[-1].split('.png')[0]))
        # Try to read the dicom images
        slice_thicknesses = []

        images_dict = defaultdict(list)
        location_dict = {}
        for dcm in dcm_images:
            file_reader = sitk.ImageFileReader()

            file_reader.SetFileName(dcm)
            file_reader.ReadImageInformation()
            slice_thickness = float(file_reader.GetMetaData('0018|0050').strip())
            slice_thicknesses.append(slice_thickness)

            slice_location = float(file_reader.GetMetaData('0020|1041').strip())
            echo_time = float(file_reader.GetMetaData('0018|0081'))
            images_dict[echo_time].append(dcm)
            location_dict[dcm] = slice_location

        assert len(set(slice_thicknesses)) == 1, f'Multiple thicknesses in images: {slice_thicknesses}'

        for echo_time, dcm_fns in images_dict.items():
            dcm_fns = sorted(dcm_fns, key=lambda x: location_dict[x])
            slices = [sitk.ReadImage(_) for _ in dcm_fns]
            vol_img = sitk.Image(slices[0].GetSize()[0], slices[0].GetSize()[1], len(slices), slices[0].GetPixelID())
            for idx_z, slice_vol in enumerate(slices):
                vol_img = sitk.Paste(vol_img, slice_vol, slice_vol.GetSize(), destinationIndex=[0, 0, idx_z])
            vol_img.SetSpacing(slices[0].GetSpacing())
            vol_img.SetOrigin(slices[0].GetOrigin())
            all_images.append((sequence_type, echo_time, vol_img))

        all_masks = get_masks(gt_images, vol_img, sequence_type)

    return all_images, all_masks


def get_ct_images_from_patient(patient_path):
    dicoms = os.path.join(patient_path, 'DICOM_anon')
    gt = os.path.join(patient_path, 'Ground')
    gt_images = glob(os.path.join(gt, '*.png'))
    gt_images = sorted(gt_images, key=lambda x: int(os.path.basename(x).split('_')[-1].split('.png')[0]))
    # Try to read the dicom images

    reader = sitk.ImageSeriesReader()
    series_ids = list(reader.GetGDCMSeriesIDs(dicoms))
    assert len(series_ids) == 1, 'Assuming one series id'

    fns = reader.GetGDCMSeriesFileNames(dicoms, series_ids[0])
    reader.SetFileNames(fns)
    vol_img = reader.Execute()

    all_masks = get_masks(gt_images, vol_img, 'liver')

    return vol_img, all_masks


def main_mri(args):
    patients = get_patients(args.root_dir)
    for patient in tqdm(patients):
        images, masks = get_mri_images_from_patient(os.path.join(args.root_dir, patient))
        images.sort(key=lambda x: x[1])  # Sort on echo time, longer echo time is the in-phase image

        for idx, image_list in enumerate(images):
            sequence_type, echo_time, image = image_list
            if sequence_type == 'T1DUAL':
                if idx == 0:
                    fn = f'T1DUAL_out_phase_image.nrrd'
                else:
                    fn = f'T1DUAL_in_phase_image.nrrd'
            elif sequence_type == 'T2SPIR':
                fn = 'T2SPIR_image.nrrd'

            write_to_folder = os.path.join(args.write_to, f'Patient_{patient}')
            os.makedirs(write_to_folder, exist_ok=True)
            sitk.WriteImage(image, os.path.join(write_to_folder, fn), True)

        for mask_name, mask in masks:
            fn = f'{mask_name}_mask.nrrd'
            write_to_folder = os.path.join(args.write_to, f'Patient_{patient}')
            sitk.WriteImage(mask, os.path.join(write_to_folder, fn), True)


def main_ct(args):
    patients = get_patients(args.root_dir)
    for patient in tqdm(patients):
        image, masks = get_ct_images_from_patient(os.path.join(args.root_dir, patient))
        mask_name, mask = masks[0]
        write_to_folder = os.path.join(args.write_to, f'Patient_{patient}')
        os.makedirs(write_to_folder, exist_ok=True)
        sitk.WriteImage(image, os.path.join(write_to_folder, 'CT_image.nrrd'), True)

        sitk.WriteImage(mask, os.path.join(write_to_folder, f'{mask_name}_mask.nrrd'), True)


def main():
    args = parse_args()
    if args.modality == 'CT':
        main_ct(args)
    elif args.modality == 'MR':
        main_mri(args)
    else:
        sys.exit('Choose MR or CT as modality.')


if __name__ == '__main__':
    main()


