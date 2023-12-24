from glob import glob
import shutil
import torch
from time import  strftime
import os, sys, time
from argparse import ArgumentParser, Namespace

from src.utils.preprocess import CropAndExtract
from src.test_audio2coeff import Audio2Coeff  
from src.facerender.animate import AnimateFromCoeff
from src.generate_batch import get_data
from src.generate_facerender_batch import get_facerender_data
from src.utils.init_path import init_path



def main(driven_audio, source_image, ref_eyeblink, args):
    #torch.backends.cudnn.enabled = False

    pic_path = source_image
    audio_path = driven_audio
    save_dir = os.path.join(args.result_dir, strftime("%Y_%m_%d_%H.%M.%S"))
    os.makedirs(save_dir, exist_ok=True)
    pose_style = args.pose_style
    device = args.device
    batch_size = args.batch_size
    input_yaw_list = args.input_yaw
    input_pitch_list = args.input_pitch
    input_roll_list = args.input_roll
    ref_eyeblink = ref_eyeblink
    ref_pose = args.ref_pose

    # current_root_path = os.path.split(sys.argv[0])[0]
    current_root_path = 'src/sadTalker'

    sadtalker_paths = init_path(args.checkpoint_dir, os.path.join(current_root_path, 'src/config'), args.size, args.old_version, args.preprocess)

    #init model
    preprocess_model = CropAndExtract(sadtalker_paths, device)

    audio_to_coeff = Audio2Coeff(sadtalker_paths,  device)
    
    animate_from_coeff = AnimateFromCoeff(sadtalker_paths, device)

    #crop image and extract 3dmm from image
    first_frame_dir = os.path.join(save_dir, 'first_frame_dir')
    os.makedirs(first_frame_dir, exist_ok=True)
    print('3DMM Extraction for source image')
    first_coeff_path, crop_pic_path, crop_info =  preprocess_model.generate(pic_path, first_frame_dir, args.preprocess,\
                                                                             source_image_flag=True, pic_size=args.size)
    # shutil.rmtree(first_frame_dir, ignore_errors=True)
    if first_coeff_path is None:
        print("Can't get the coeffs of the input")
        return

    if ref_eyeblink is not None:
        ref_eyeblink_videoname = os.path.splitext(os.path.split(ref_eyeblink)[-1])[0]
        ref_eyeblink_frame_dir = os.path.join(save_dir, ref_eyeblink_videoname)
        os.makedirs(ref_eyeblink_frame_dir, exist_ok=True)
        print('3DMM Extraction for the reference video providing eye blinking')
        ref_eyeblink_coeff_path, _, _ =  preprocess_model.generate(ref_eyeblink, ref_eyeblink_frame_dir, args.preprocess, source_image_flag=False)
    else:
        ref_eyeblink_coeff_path=None

    if ref_pose is not None:
        if ref_pose == ref_eyeblink: 
            ref_pose_coeff_path = ref_eyeblink_coeff_path
        else:
            ref_pose_videoname = os.path.splitext(os.path.split(ref_pose)[-1])[0]
            ref_pose_frame_dir = os.path.join(save_dir, ref_pose_videoname)
            os.makedirs(ref_pose_frame_dir, exist_ok=True)
            print('3DMM Extraction for the reference video providing pose')
            ref_pose_coeff_path, _, _ =  preprocess_model.generate(ref_pose, ref_pose_frame_dir, args.preprocess, source_image_flag=False)
    else:
        ref_pose_coeff_path=None

    #audio2ceoff
    batch = get_data(first_coeff_path, audio_path, device, ref_eyeblink_coeff_path, still=args.still)
    coeff_path = audio_to_coeff.generate(batch, save_dir, pose_style, ref_pose_coeff_path)

    # 3dface render
    if args.face3dvis:
        from src.face3d.visualize import gen_composed_video
        gen_composed_video(args, device, first_coeff_path, coeff_path, audio_path, os.path.join(save_dir, '3dface.mp4'))
    
    #coeff2video
    data = get_facerender_data(coeff_path, crop_pic_path, first_coeff_path, audio_path, 
                                batch_size, input_yaw_list, input_pitch_list, input_roll_list,
                                expression_scale=args.expression_scale, still_mode=args.still, preprocess=args.preprocess, size=args.size)
    
    result = animate_from_coeff.generate(data, save_dir, pic_path, crop_info, \
                                enhancer=args.enhancer, background_enhancer=args.background_enhancer, preprocess=args.preprocess, img_size=args.size)
    
    shutil.move(result, save_dir+'.mp4')
    print('The generated video is named:', save_dir+'.mp4')

    if not args.verbose:
        shutil.rmtree(save_dir)

    talking_video = save_dir+'.mp4'
    shutil.rmtree(first_frame_dir, ignore_errors=True)

    return talking_video

def lip_sync(driven_audio, source_image, working_dir, ref_eyeblink):
    default_args = {
        # "driven_audio": './examples/driven_audio/bus_chinese.wav',
        # "source_image": './examples/source_image/full_body_1.png',
        # "ref_eyeblink": None,
        "ref_pose": None,
        "checkpoint_dir": 'src/sadTalker/checkpoints',
        "result_dir": working_dir,
        "pose_style": 0,
        "batch_size": 10,
        "size": 256,
        "expression_scale": 1.0,
        "input_yaw": None,
        "input_pitch": None,
        "input_roll": None,
        "enhancer": '',
        "background_enhancer": None,
        "cpu": False,
        "face3dvis": False,
        "still": True,
        "preprocess": 'full',
        "verbose": False,
        "old_version": False,
        "net_recon": 'resnet50',
        "init_path": None,
        "use_last_fc": False,
        "bfm_folder": './checkpoints/BFM_Fitting/',
        "bfm_model": 'BFM_model_front.mat',
        "focal": 1015.0,
        "center": 112.0,
        "camera_d": 10.0,
        "z_near": 5.0,
        "z_far": 15.0
    }

    args = Namespace(**default_args)

    if torch.cuda.is_available() and not args.cpu:
        args.device = "cuda"
    else:
        args.device = "cpu"

    return main(driven_audio, source_image, ref_eyeblink, args)

# print('talking video path: ', lip_sync( './examples/driven_audio/bus_chinese.wav', './examples/source_image/full_body_1.png', None))
