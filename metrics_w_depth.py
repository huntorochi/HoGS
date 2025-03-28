#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

from pathlib import Path
import os
from PIL import Image
import torch
import torchvision.transforms.functional as tf
import cv2
import matplotlib.pyplot as plt
import numpy as np
from utils.loss_utils import ssim
from lpipsPyTorch import lpips
import json
from tqdm import tqdm
from utils.image_utils import psnr
from argparse import ArgumentParser

def readImages0(renders_dir, gt_dir):
    renders = []
    gts = []
    image_names = []
    for fname in os.listdir(renders_dir):
        render = Image.open(renders_dir / fname)
        gt = Image.open(gt_dir / fname)
        renders.append(tf.to_tensor(render).unsqueeze(0)[:, :3, :, :].cuda())
        gts.append(tf.to_tensor(gt).unsqueeze(0)[:, :3, :, :].cuda())
        image_names.append(fname)
    return renders, gts, image_names

def readImages(renders_dir, gt_dir, dp_dir):
    renders = []
    gts = []
    depth_maps = []
    image_names = []

    # Sort GT images by their filenames
    gt_files = sorted(gt_dir.glob("*.png"))

    # Sort depth files in ascending order
    depth_files = sorted(dp_dir.glob("*.png"))

    for index, fname in enumerate(sorted(renders_dir.glob("*.png"))):
        render = Image.open(fname)

        # Get corresponding GT image based on sorted index
        gt = Image.open(gt_files[index])

        # Format output name for GT as "00000.png"
        formatted_gt_name = f"{index:05d}.png"

        # Convert images to tensors and add to lists
        renders.append(tf.to_tensor(render).unsqueeze(0)[:, :3, :, :].cuda())
        gts.append(tf.to_tensor(gt).unsqueeze(0)[:, :3, :, :].cuda())
        depth_maps.append(depth_files[index * 8])

        # Append formatted GT name
        image_names.append(formatted_gt_name)


    return renders, gts, depth_maps, image_names

def evaluate(model_paths, depth_paths):

    full_dict = {}
    per_view_dict = {}
    full_dict_polytopeonly = {}
    per_view_dict_polytopeonly = {}

    # print(depth_paths)

    far_threshold = 0.05
    threshold = 255 * far_threshold
    for idx, scene_dir in enumerate(model_paths):
        if True:
        # try:
            print("Scene:", scene_dir)
            full_dict[scene_dir] = {}
            per_view_dict[scene_dir] = {}
            full_dict_polytopeonly[scene_dir] = {}
            per_view_dict_polytopeonly[scene_dir] = {}

            test_dir = Path(scene_dir) / "test"
            depth_path = depth_paths[idx]

            for method in os.listdir(test_dir):
                print("Method:", method)

                full_dict[scene_dir][method] = {}
                per_view_dict[scene_dir][method] = {}
                full_dict_polytopeonly[scene_dir][method] = {}
                per_view_dict_polytopeonly[scene_dir][method] = {}

                method_dir = test_dir / method
                gt_dir = method_dir/ "gt"
                renders_dir = method_dir / "renders"
                renders, gts, depth_maps, image_names = readImages(renders_dir, gt_dir, Path(depth_path))
                dp_dir = method_dir / "depth_map_used"
                os.makedirs(dp_dir, exist_ok=True)

                renders_near = []
                renders_far = []
                gts_near = []
                gts_far = []

                for i in range(len(image_names)):
                    image_name = image_names[i]
                    num = int(os.path.splitext(image_name)[0])
                    depth_number = num# * 8
                    depth_name = f"DSC{depth_number:05d}.png"
                    depth_map_filename = str(dp_dir) + "/" + depth_name
                    depth_name = str(depth_maps[depth_number])
                    depth_map = cv2.resize(cv2.imread(depth_name, cv2.IMREAD_ANYDEPTH), (renders[i].shape[3], renders[i].shape[2]))
                    depth_map[depth_map < threshold] = 0
                    depth_data = torch.tensor(depth_map, device="cuda")
                    cv2.imwrite(depth_map_filename, depth_map)

                    mask_far = depth_data == 0
                    mask_far_bc = mask_far.unsqueeze(0).unsqueeze(0)
                    mask_near = depth_data > 0
                    mask_near_bc = mask_far.unsqueeze(0).unsqueeze(0)
                    render_far = renders[i] * mask_far
                    render_near = renders[i] * mask_near
                    gt_far = gts[i] * mask_far
                    gt_near = gts[i] * mask_near
                    renders_far.append(render_far)
                    renders_near.append(render_near)
                    gts_far.append(gt_far)
                    gts_near.append(gt_near)

                ssims = []
                psnrs = []
                lpipss = []

                ssims_near = []
                psnrs_near = []
                lpipss_near = []

                ssims_far = []
                psnrs_far = []
                lpipss_far = []



                for idx in tqdm(range(len(renders)), desc="Metric evaluation progress"):
                    ssims.append(ssim(renders[idx], gts[idx]))
                    psnrs.append(psnr(renders[idx], gts[idx]))
                    lpipss.append(lpips(renders[idx], gts[idx], net_type='vgg'))

                    ssims_near.append(ssim(renders_near[idx], gts_near[idx]))
                    psnrs_near.append(psnr(renders_near[idx], gts_near[idx]))
                    lpipss_near.append(lpips(renders_near[idx], gts_near[idx], net_type='vgg'))

                    ssims_far.append(ssim(renders_far[idx], gts_far[idx]))
                    psnrs_far.append(psnr(renders_far[idx], gts_far[idx]))
                    lpipss_far.append(lpips(renders_far[idx], gts_far[idx], net_type='vgg'))

                print("  SSIM : {:>12.7f}".format(torch.tensor(ssims).mean(), ".5"))
                print("  PSNR : {:>12.7f}".format(torch.tensor(psnrs).mean(), ".5"))
                print("  LPIPS: {:>12.7f}".format(torch.tensor(lpipss).mean(), ".5"))
                print("")
                print("  SSIM near : {:>12.7f}".format(torch.tensor(ssims_near).mean(), ".5"))
                print("  PSNR near : {:>12.7f}".format(torch.tensor(psnrs_near).mean(), ".5"))
                print("  LPIPS near: {:>12.7f}".format(torch.tensor(lpipss_near).mean(), ".5"))
                print("")
                print("  SSIM far : {:>12.7f}".format(torch.tensor(ssims_far).mean(), ".5"))
                print("  PSNR far : {:>12.7f}".format(torch.tensor(psnrs_far).mean(), ".5"))
                print("  LPIPS far: {:>12.7f}".format(torch.tensor(lpipss_far).mean(), ".5"))
                print("")


                full_dict[scene_dir][method].update({"SSIM": torch.tensor(ssims).mean().item(),
                                                     "PSNR": torch.tensor(psnrs).mean().item(),
                                                     "LPIPS": torch.tensor(lpipss).mean().item(),
                                                     "SSIM near": torch.tensor(ssims_near).mean().item(),
                                                     "PSNR near": torch.tensor(psnrs_near).mean().item(),
                                                     "LPIPS near": torch.tensor(lpipss_near).mean().item(),
                                                     "SSIM far": torch.tensor(ssims_far).mean().item(),
                                                     "PSNR far": torch.tensor(psnrs_far).mean().item(),
                                                     "LPIPS far": torch.tensor(lpipss_far).mean().item()
                                                     })
                per_view_dict[scene_dir][method].update({"SSIM": {name: ssim for ssim, name in zip(torch.tensor(ssims).tolist(), image_names)},
                                                         "PSNR": {name: psnr for psnr, name in zip(torch.tensor(psnrs).tolist(), image_names)},
                                                         "LPIPS": {name: lp for lp, name in zip(torch.tensor(lpipss).tolist(), image_names)},
                                                         "SSIM near": {name: ssim for ssim, name in
                                                                  zip(torch.tensor(ssims_near).tolist(), image_names)},
                                                         "PSNR near": {name: psnr for psnr, name in
                                                                  zip(torch.tensor(psnrs_near).tolist(), image_names)},
                                                         "LPIPS near": {name: lp for lp, name in
                                                                   zip(torch.tensor(lpipss_near).tolist(), image_names)},
                                                         "SSIM far": {name: ssim for ssim, name in
                                                                  zip(torch.tensor(ssims_far).tolist(), image_names)},
                                                         "PSNR far": {name: psnr for psnr, name in
                                                                  zip(torch.tensor(psnrs_far).tolist(), image_names)},
                                                         "LPIPS far": {name: lp for lp, name in
                                                                   zip(torch.tensor(lpipss_far).tolist(), image_names)},
                                                         })

            with open(scene_dir + "/results.json", 'w') as fp:
                json.dump(full_dict[scene_dir], fp, indent=True)
            with open(scene_dir + "/per_view.json", 'w') as fp:
                json.dump(per_view_dict[scene_dir], fp, indent=True)
        # except:
        #     print("Unable to compute metrics for model", scene_dir)

if __name__ == "__main__":
    device = torch.device("cuda:0")
    torch.cuda.set_device(device)

    # Set up command line argument parser
    parser = ArgumentParser(description="Training script parameters")
    parser.add_argument('--model_paths', '-m', required=True, nargs="+", type=str, default=[])
    parser.add_argument('--depth_paths', '-d', required=True, nargs="+", type=str, default=[])
    args = parser.parse_args()
    print(args)
    evaluate(args.model_paths, args.depth_paths)
