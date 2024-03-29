import os
import pdb
import cv2
import time
import torch
import logging
import traceback
import numpy as np

# from config import HOME
from tensorboard_logger import log_value, log_images
from torchnet.meter import ConfusionMeter
from sklearn.metrics import roc_auc_score, roc_curve
from matplotlib import pyplot as plt

plt.switch_backend("agg")


def logger_init(save_folder):
    mkdir(save_folder)
    logging.basicConfig(
        filename=os.path.join(save_folder, "log.txt"),
        filemode="a",
        level=logging.DEBUG,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    console = logging.StreamHandler()
    logger = logging.getLogger(__name__)
    logger.addHandler(console)
    return logger


class Meter(ConfusionMeter):
    def __init__(self, k, phase, epoch, save_folder, normalized=False):
        ConfusionMeter.__init__(self, k, normalized=normalized)
        self.predictions = []
        self.targets = []
        self.threshold = 0.5  # used for confusion matrix
        self.phase = phase
        self.epoch = epoch
        self.save_folder = save_folder

    def update(self, targets, outputs):
        self.targets.extend(targets)
        self.predictions.extend(outputs)
        outputs = (outputs > self.threshold).type(torch.Tensor).squeeze()
        self.add(outputs, targets)

    def get_metrics(self):
        conf = self.value().flatten()
        total_images = np.sum(conf)
        TN, FP, FN, TP = conf
        acc = (TP + TN) / total_images
        tpr = TP / (FN + TP)
        fpr = FP / (TN + FP)
        tnr = TN / (TN + FP)
        fnr = FN / (TP + FN)
        precision = TP / (TP + FP)
        roc = roc_auc_score(self.targets, self.predictions)
        plot_ROC(
            roc,
            self.targets,
            self.predictions,
            self.phase,
            self.epoch,
            self.save_folder,
        )
        return acc, precision, tpr, fpr, tnr, fnr, roc


def plot_ROC(roc, targets, predictions, phase, epoch, folder):
    roc_plot_folder = os.path.join(folder, "ROC_plots")
    mkdir(os.path.join(roc_plot_folder))
    fpr, tpr, thresholds = roc_curve(targets, predictions)
    roc_plot_name = "ROC_%s_%s_%0.4f" % (phase, epoch, roc)
    roc_plot_path = os.path.join(roc_plot_folder, roc_plot_name + ".jpg")
    fig = plt.figure(figsize=(10, 5))
    plt.plot([0, 1], [0, 1], linestyle="--")
    plt.plot(fpr, tpr, marker=".")
    plt.legend(["diagonal-line", roc_plot_name])
    fig.savefig(roc_plot_path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)  # see footnote [1]

    plot = cv2.imread(roc_plot_path)
    log_images(roc_plot_name, [plot], epoch)


def print_time(log, start, string):
    diff = time.time() - start
    log(string + ": %02d:%02d" % (diff // 60, diff % 60))


def adjust_lr(lr, optimizer):
    """ Update the lr of base model
    # Adapted from PyTorch Imagenet example:
    # https://github.com/pytorch/examples/blob/master/imagenet/main.py
    """
    for param_group in optimizer.param_groups[:-1]:
        param_group["lr"] = lr
    return optimizer


def iter_log(log, phase, epoch, iteration, epoch_size, loss, start):
    diff = time.time() - start
    log(
        "%s epoch: %d (%d/%d) loss: %.4f || %02d:%02d",
        phase,
        epoch,
        iteration,
        epoch_size,
        loss.item(),
        diff // 60,
        diff % 60,
    )


def epoch_log(log, phase, epoch, epoch_loss, meter, start):
    diff = time.time() - start
    acc, precision, tpr, fpr, tnr, fnr, roc = meter.get_metrics()
    log("%s epoch: %d finished" % (phase, epoch))
    log("%s Epoch: %d, loss: %0.4f, roc: %0.4f", phase, epoch, epoch_loss, roc)
    log("Acc: %0.4f | Precision: %0.4f", acc, precision)
    log("tnr: %0.4f | fpr: %0.4f", tnr, fpr)
    log("fnr: %0.4f | tpr: %0.4f", fnr, tpr)
    log("Time taken for %s phase: %02d:%02d \n", phase, diff // 60, diff % 60)
    log_value(phase + " loss", epoch_loss, epoch)
    log_value(phase + " roc", roc, epoch)
    log_value(phase + " acc", acc, epoch)
    log_value(phase + " precision", precision, epoch)
    log_value(phase + " tnr", tnr, epoch)
    log_value(phase + " fpr", fpr, epoch)
    log_value(phase + " fnr", fnr, epoch)
    log_value(phase + " tpr", tpr, epoch)


def mkdir(folder):
    if not os.path.exists(folder):
        os.mkdir(folder)


"""Footnotes:

[1]: https://stackoverflow.com/questions/21884271/warning-about-too-many-open-figures

"""
