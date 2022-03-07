import json
import os
import pkgutil
from collections import namedtuple

import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from docarray import Document
from sklearn.metrics import (
    precision_recall_curve,
    average_precision_score,
    PrecisionRecallDisplay,
)
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, label_binarize
from sklearn.svm import LinearSVC

colors = [
    "navy",
    "turquoise",
    "darkorange",
    "cornflowerblue",
    "teal",
    'maroon',
    'purple',
    'green',
    'lime',
    'navy',
    'teal',
]


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def multi_class_svm(embed, labels, title):
    # multi-label setting for ROC curve
    classes = np.arange(start=0, stop=len(set(labels)))
    Y = label_binarize(labels, classes=classes)

    n_classes = Y.shape[1]

    # split the dataset
    X_train, X_test, Y_train, Y_test = train_test_split(
        embed, Y, test_size=0.25, random_state=42
    )

    # define the classifier
    clf = OneVsRestClassifier(
        make_pipeline(StandardScaler(), LinearSVC(max_iter=5000, random_state=42))
    )

    clf.fit(X_train, Y_train)
    y_score = clf.decision_function(X_test)

    # For each class
    precision = dict()
    recall = dict()
    average_precision = dict()
    for i in range(n_classes):
        precision[i], recall[i], _ = precision_recall_curve(Y_test[:, i], y_score[:, i])
        average_precision[i] = average_precision_score(Y_test[:, i], y_score[:, i])

    _, ax = plt.subplots()

    for i, color in zip(range(n_classes), colors):
        display = PrecisionRecallDisplay(
            recall=recall[i],
            precision=precision[i],
            average_precision=average_precision[i],
        )
        display.plot(ax=ax, color=color)

    # add the legend for the iso-f1 curves
    handles, labels = display.ax_.get_legend_handles_labels()
    # set the legend and the axes
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.legend(handles=handles, labels=labels, loc="best")
    ax.set_title("Precision-recall curve for top-10 class")
    plt.tight_layout()
    plt.savefig(title + '.png')
    plt.close()


def binary_svm(embed, labels, title):
    # split the dataset
    X_train, X_test, Y_train, Y_test = train_test_split(
        embed, labels, test_size=1, random_state=42
    )

    classifier = make_pipeline(StandardScaler(), LinearSVC(random_state=42))
    classifier.fit(X_train, Y_train)

    y_score = classifier.decision_function(X_test)

    display = PrecisionRecallDisplay.from_predictions(Y_test, y_score)
    ax = display.ax_.set_title("Binary Precision-Recall curve")
    _, ax = plt.subplots()

    display.plot(ax=ax, name=f"LinearSVC")
    handles, labels = display.ax_.get_legend_handles_labels()
    # set the legend and the axes
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.legend(handles=handles, labels=labels, loc="best")
    plt.tight_layout()
    plt.savefig(title + '.png')
    plt.close()


def get_pr_curve(embed, labels, title='finetuned'):
    # check the number of class
    num_class = len(set(labels))
    if num_class <= 2:
        binary_svm(embed, labels, title)
    else:
        multi_class_svm(embed, labels, title)


def save_before_after_image(path):
    figs = [
        ['pretrained.png', 'finetuned.png'],
        ['pretrained_pr.png', 'finetuned_pr.png'],
        ['pretrained_m.png', 'finetuned_m.png'],
    ]
    imgs = [im1, im2, im3, im4, im5, im6] = [
        Image.open(img) for imgs in figs for img in imgs
    ]

    big_w = im1.width if im1.width > im3.width else im3.width

    im1 = im1.resize(
        (big_w, int(im1.height * big_w / im1.width)), resample=Image.BICUBIC
    )
    im2 = im2.resize(
        (big_w, int(im2.height * big_w / im2.width)), resample=Image.BICUBIC
    )
    im3 = im3.resize(
        (big_w, int(im3.height * big_w / im3.width)), resample=Image.BICUBIC
    )
    im4 = im4.resize(
        (big_w, int(im4.height * big_w / im4.width)), resample=Image.BICUBIC
    )
    im5 = im5.resize(
        (big_w, int(im5.height * big_w / im5.width)), resample=Image.BICUBIC
    )
    im6 = im6.resize(
        (big_w, int(im6.height * big_w / im6.width)), resample=Image.BICUBIC
    )

    width = (
        max(im1.width + im2.width, im3.width + im4.width, im5.width + im6.width) + 200
    )
    height = (
        max(
            im1.height + im3.height + im5.height,
            im2.height + im4.height + im6.height,
        )
        + 300
    )

    dst = Image.new('RGB', (width, height), color=(255, 255, 255))

    dst.paste(im1, (10, 150))
    dst.paste(im2, (im1.width + 150, 150))
    dst.paste(im3, (10, im1.height + 250))
    dst.paste(im4, (im1.width + 120, im1.height + 250))
    dst.paste(im5, (50, im3.height + im1.height + 300))
    dst.paste(im6, (im1.width + 200, im3.height + im1.height + 300))
    draw = ImageDraw.Draw(dst)
    font = ImageFont.truetype(
        'fonts/arial.ttf', 50
    )  # this font does not work in docker currently
    # font = ImageFont.load_default()
    draw.line(
        (im1.width + 80, 0, im1.width + 80, im1.height + im2.height + im3.height + 250),
        width=10,
        fill='black',
    )  # vertical line
    draw.line(
        (0, im1.height + 200, im1.width + im2.width + 250, im1.height + 200),
        width=10,
        fill='black',
    )  # horizontal line
    draw.line(
        (
            0,
            im1.height + im2.height,
            im1.width + im2.width + 250,
            im1.height + im2.height,
        ),
        width=10,
        fill='black',
    )  # horizontal line
    draw.text(((im1.width - 150) // 2, 0), "Pre-trained Results", 0, font=font)
    draw.text((im1.width + 50 + (im2.width // 2), 0), "Finetuned Results", 0, font=font)
    font = ImageFont.truetype('fonts/arial.ttf', 30)
    draw.text((20, 100), "Query", 0, font=font)
    draw.text((im1.width + 150, 100), "Query", 0, font=font)
    draw.text((im1.width // 2, 100), "Top-k", 0, font=font)
    draw.text((im1.width + 100 + (im2.width // 2), 100), "Top-k", 0, font=font)
    dst.save(path)
    for imgs in figs:
        for img in imgs:
            if os.path.isfile(img):
                os.remove(img)


def visual_result(
    data,
    querys,
    output: str = None,
    canvas_size: int = 1500,
    channel_axis: int = -1,
    img_per_row=11,
    label='finetuner_label',
):
    img_size = int(canvas_size / img_per_row)
    img_h, img_w = img_size, img_size

    if data == 'geolocation-geoguessr':
        img_h, img_w = img_size, 2 * img_size

    sprite_img = np.zeros([img_h * len(querys), img_w * img_per_row, 3], dtype='uint8')

    for img_id, q in enumerate(querys):
        _d = Document(q, copy=True)
        if _d.content_type != 'tensor':
            _d.convert_blob_to_image_tensor()
            channel_axis = -1

        _d.set_image_tensor_channel_axis(channel_axis, -1).set_image_tensor_shape(
            shape=(img_h, img_w)
        )

        row_id = img_id
        col_id = 0
        sprite_img[
            (row_id * img_h) : ((row_id + 1) * img_h),
            (col_id * img_w) : ((col_id + 1) * img_w),
        ] = _d.tensor

        sprite_img[
            (row_id * img_h) : ((row_id + 1) * img_h),
            ((col_id + 1) * img_w) : ((col_id + 2) * img_w),
        ] = np.ones_like(_d.tensor.shape)

        for j, d in enumerate(q.matches, start=1):
            _d = Document(d, copy=True)
            if _d.content_type != 'tensor':
                _d.convert_blob_to_image_tensor()
                channel_axis = -1

            _d.set_image_tensor_channel_axis(channel_axis, -1).set_image_tensor_shape(
                shape=(img_h - 10, img_w - 10)
            )

            match_img = np.ones([img_h, img_w, 3], dtype='uint8')
            match_img[5:-5, 5:-5] = _d.tensor  # center the match results image
            # apply green if it is same class else red
            if q.tags[label] == _d.tags[label]:
                match_img[0:5, ...] = (0, 255, 0)
                match_img[-5:-1, ...] = (0, 255, 0)
                match_img[:, 0:5, ...] = (0, 255, 0)
                match_img[:, -5:-1, ...] = (0, 255, 0)
            else:
                match_img[0:5, ...] = (255, 0, 0)
                match_img[-5:-1, ...] = (255, 0, 0)
                match_img[:, 0:5, ...] = (255, 0, 0)
                match_img[:, -5:-1, ...] = (255, 0, 0)

            # paste it on the main canvas
            col_id = j + 1
            sprite_img[
                (row_id * img_h) : ((row_id + 1) * img_h),
                (col_id * img_w) : ((col_id + 1) * img_w),
            ] = match_img

    from PIL import Image

    img = Image.fromarray(sprite_img)
    if output:
        with open(output, 'wb') as fp:
            img.save(fp)


def plot_metrics(metrics_dict, title):
    dst = Image.new(
        'RGB',
        (500, 300),
        color=(255, 255, 255),
    )
    draw = ImageDraw.Draw(dst)
    font = ImageFont.truetype(
        'fonts/arial.ttf', 20
    )  # this font does not work in docker currently
    # font = ImageFont.load_default()
    for idx, (key, val) in enumerate(metrics_dict.items()):
        draw.text((50, idx * 30), f'{key}', 0, font=font)
        draw.text((250, idx * 30), f":  {val:.3f}", 0, font=font)

    dst.save(title)

def custom_spinner():
    SPINNERS_DATA = pkgutil.get_data(__name__, "custom-spinners.json").decode("utf-8")

    def _hook(dct):
        return namedtuple("Spinner", dct.keys())(*dct.values())

    return json.loads(SPINNERS_DATA, object_hook=_hook)

def download(url, filename):
    import functools
    import pathlib
    import shutil
    import requests
    from tqdm.auto import tqdm

    r = requests.get(url, stream=True, allow_redirects=True)
    if r.status_code != 200:
        r.raise_for_status()  # Will only raise for 4xx codes, so...
        raise RuntimeError(f"Request to {url} returned status code {r.status_code}")
    file_size = int(r.headers.get('Content-Length', 0))

    path = pathlib.Path(filename).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    desc = "(Unknown total file size)" if file_size == 0 else ""
    r.raw.read = functools.partial(r.raw.read, decode_content=True)  # Decompress if needed
    with tqdm.wrapattr(r.raw, "read", total=file_size, desc=desc) as r_raw:
        with path.open("wb") as f:
            shutil.copyfileobj(r_raw, f)

    return path