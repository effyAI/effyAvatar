import time
from pathlib import Path
import cv2, os
import torch
from numpy import random

from models.experimental import attempt_load
from utils.datasets import LoadImages
from utils.general import check_img_size, non_max_suppression, apply_classifier, scale_coords, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_synchronized


def new_detect_custom(source):
    weights = 'src/image_cropping/crowdhuman_yolov5m.pt'
    # print('weight path exists: ', os.path.exists(weights))
    
    view_img = True
    imgsz = 640
    conf_thres = 0.25
    iou_thres = 0.45
    device = ''  # 'cuda:0' for GPU, 'cpu' for CPU
    save_img = True
    classes = None
    agnostic_nms = False
    augment = False
    person = False
    heads = True

    # Directories
    # save_dir = Path(increment_path(Path(project) / name,
    #                 exist_ok=exist_ok))  # increment run
    # (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True,
    #                                                       exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size
    if half:
        model.half()  # to FP16

    # Second-stage classifier
    classify = False
    if classify:
        modelc = load_classifier(name='resnet101', n=2)  # initialize
        modelc.load_state_dict(torch.load(
            'weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    save_img = True
    dataset = LoadImages(source, img_size=imgsz, stride=stride)

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(
            next(model.parameters())))  # run once
    t0 = time.time()
    for path, img, im0s, _ in dataset:
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Inference
        t1 = time_synchronized()
        pred = model(img, augment=augment)[0]

        # Apply NMS
        pred = non_max_suppression(
            pred, conf_thres, iou_thres, classes=classes, agnostic=agnostic_nms)
        t2 = time_synchronized()

        # Apply Classifier
        if classify:
            pred = apply_classifier(pred, modelc, img, im0s)

        # Process detections
        for i, det in enumerate(pred):  # detections per image
            _, _, im0, _ = path, '', im0s, getattr(dataset, 'frame', 0)

            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(
                    img.shape[2:], det[:, :4], im0.shape).round()

                # Write results
                for *xyxy, conf, cls in reversed(det):
                    # print("*xyxy: ", *xyxy)
                    # print("conf: ", conf)
                    # print('cls: ', cls)

                    if save_img or view_img:  # Add bbox to image
                        label = f'{names[int(cls)]} {conf:.2f}'
                        heads = torch.true_divide
                        if heads or person:
                            if 'head' in label and heads:
                                plot_one_box(
                                    xyxy, im0, label=label, color=colors[int(cls)], line_thickness=3)
                                return [i.item() for i in xyxy]
                        else:
                            plot_one_box(xyxy, im0, label=label,
                                         color=colors[int(cls)], line_thickness=3)

    print('head not found')
    return [0, 0, 0, 0]
            # Print time (inference + NMS)
            # print(f'{s}Done. ({t2 - t1:.3f}s)')