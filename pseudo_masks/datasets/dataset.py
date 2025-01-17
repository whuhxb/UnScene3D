# Copyright (c) Facebook, Inc. and its affiliates.
# 
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
from abc import ABC
from pathlib import Path
from collections import defaultdict

import random
import numpy as np
from enum import Enum
import torch
from torch.utils.data import Dataset, DataLoader

import MinkowskiEngine as ME

from plyfile import PlyData
import lib.utils.transforms as t
from lib.datasets.dataloader import InfSampler
from lib.datasets.voxelizer import Voxelizer


class DatasetPhase(Enum):
    Train = 0
    Val = 1
    Val2 = 2
    TrainVal = 3
    Test = 4
    Debug = 5
    DebugVal = 6
    Clean = 7


def datasetphase_2str(arg):
    if arg == DatasetPhase.Train:
        return 'train'
    elif arg == DatasetPhase.Val:
        return 'val'
    elif arg == DatasetPhase.Val2:
        return 'val2'
    elif arg == DatasetPhase.TrainVal:
        return 'trainval'
    elif arg == DatasetPhase.Test:
        return 'test'
    elif arg == DatasetPhase.Debug:
        return 'debug'
    elif arg == DatasetPhase.DebugVal:
        return 'debugval'
    elif arg == DatasetPhase.Clean:
        return 'clean'
    else:
        raise ValueError('phase must be one of dataset enum.')


def str2datasetphase_type(arg):
    if arg.upper() == 'TRAIN':
        return DatasetPhase.Train
    elif arg.upper() == 'VAL':
        return DatasetPhase.Val
    elif arg.upper() == 'VAL2':
        return DatasetPhase.Val2
    elif arg.upper() == 'TRAINVAL':
        return DatasetPhase.TrainVal
    elif arg.upper() == 'TEST':
        return DatasetPhase.Test
    elif arg.upper() == 'DEBUG':
        return DatasetPhase.Debug
    elif arg.upper() == 'DEBUGVAL':
        return DatasetPhase.DebugVal
    elif arg.upper() == 'CLEAN':
        return DatasetPhase.Clean
    else:
        raise ValueError('phase must be one of train/val/test')


def cache(func):
    def wrapper(self, *args, **kwargs):
        # Assume that args[0] is index
        index = args[0]
        if self.cache:
            if index not in self.cache_dict[func.__name__]:
                results = func(self, *args, **kwargs)
                self.cache_dict[func.__name__][index] = results
            return self.cache_dict[func.__name__][index]
        else:
            return func(self, *args, **kwargs)

    return wrapper


class DictDataset(Dataset, ABC):
    IS_FULL_POINTCLOUD_EVAL = False

    def __init__(self,
                 data_paths,
                 prevoxel_transform=None,
                 input_transform=None,
                 target_transform=None,
                 cache=False,
                 data_root='/'):
        """
        data_paths: list of lists, [[str_path_to_input, str_path_to_label], [...]]
        """
        Dataset.__init__(self)

        # Allows easier path concatenation
        if not isinstance(data_root, Path):
            data_root = Path(data_root)

        self.data_root = data_root
        self.data_paths = data_paths

        self.prevoxel_transform = prevoxel_transform
        self.input_transform = input_transform
        self.target_transform = target_transform

        # dictionary of input
        self.data_loader_dict = {
            'input': (self.load_input, self.input_transform),
            'target': (self.load_target, self.target_transform)
        }

        # For large dataset, do not cache
        self.cache = cache
        self.cache_dict = defaultdict(dict)
        self.loading_key_order = ['input', 'target']

    def load_input(self, index):
        raise NotImplementedError

    def load_target(self, index):
        raise NotImplementedError

    def get_classnames(self):
        pass

    def reorder_result(self, result):
        return result

    def __getitem__(self, index):
        out_array = []
        for k in self.loading_key_order:
            loader, transformer = self.data_loader_dict[k]
            v = loader(index)
            if transformer:
                v = transformer(v)
            out_array.append(v)
        return out_array

    def __len__(self):
        return len(self.data_paths)


class VoxelizationDatasetBase(DictDataset, ABC):
    IS_TEMPORAL = False
    CLIP_BOUND = (-1000, -1000, -1000, 1000, 1000, 1000)
    ROTATION_AXIS = None
    NUM_IN_CHANNEL = None
    NUM_LABELS = -1  # Number of labels in the dataset, including all ignore classes
    IGNORE_LABELS = None  # labels that are not evaluated

    def __init__(self,
                 data_paths,
                 prevoxel_transform=None,
                 input_transform=None,
                 target_transform=None,
                 cache=False,
                 data_root='/',
                 ignore_mask=255,
                 return_transformation=False,
                 **kwargs):
        """
        ignore_mask: label value for ignore class. It will not be used as a class in the loss or evaluation.
        """
        DictDataset.__init__(
            self,
            data_paths,
            prevoxel_transform=prevoxel_transform,
            input_transform=input_transform,
            target_transform=target_transform,
            cache=cache,
            data_root=data_root)

        self.ignore_mask = ignore_mask

    def __getitem__(self, index):
        raise NotImplementedError

    def load_data(self, index, data_root=None):
        filepath = self.data_root / self.data_paths[index] if data_root is None else Path(data_root) / f'{self.data_paths[index]}.pth'
        pointcloud = torch.load(filepath)
        coords = pointcloud[0].astype(np.float32)
        feats = pointcloud[1].astype(np.float32)
        labels = pointcloud[2].astype(np.int32)
        instances = pointcloud[3].astype(np.int32)
        scene_name = filepath.stem

        return coords, feats, labels, instances, scene_name

    def load_ply(self, index):
        filepath = self.data_root / self.data_paths[index]
        scene_name = self.data_paths[index]
        return self.load_ply_w_path(filepath, scene_name)

    def load_ply_w_path(self, filepath, scene_name):

        plydata = PlyData.read(filepath)
        data = plydata.elements[0].data
        coords = np.array([data['x'], data['y'], data['z']], dtype=np.float32).T
        feats = np.array([data['red'], data['green'], data['blue']], dtype=np.float32).T
        labels = np.array(data['label'], dtype=np.int32)

        try:  # for scenes
            instances = np.array(data['instance_id'], dtype=np.int32)
        except:  # for sampled instances
            instances = None

        return coords, feats, labels, instances, scene_name

    def __len__(self):
        num_data = len(self.data_paths)
        return num_data


def load_data(self, index):
    raise NotImplementedError


def __len__(self):
    num_data = len(self.data_paths)
    return num_data


class VoxelizationDataset(VoxelizationDatasetBase):
    """This dataset loads RGB point clouds and their labels as a list of points
    and voxelizes the pointcloud with sufficient data augmentation.
    """
    # Voxelization arguments
    CLIP_BOUND = None
    TEST_CLIP_BOUND = None
    VOXEL_SIZE = 0.05

    # Coordinate Augmentation Arguments: Unlike feature augmentation, coordinate
    # augmentation has to be done before voxelization
    SCALE_AUGMENTATION_BOUND = (0.9, 1.1)
    ROTATION_AUGMENTATION_BOUND = ((-np.pi / 64, np.pi / 64), (-np.pi / 64, np.pi / 64), (-np.pi, np.pi))
    TRANSLATION_AUGMENTATION_RATIO_BOUND = ((-0.2, 0.2), (-0.2, 0.2), (0, 0))
    ELASTIC_DISTORT_PARAMS = ((0.2, 0.4), (0.8, 1.6))

    ROTATION_AXIS = 'z'
    LOCFEAT_IDX = 2

    # MISC.
    PREVOXELIZATION_VOXEL_SIZE = None

    # Augment coords to feats
    AUGMENT_COORDS_TO_FEATS = False

    IS_FULL_POINTCLOUD_EVAL = True

    def __init__(self,
                 data_paths,
                 prevoxel_transform=None,
                 input_transform=None,
                 target_transform=None,
                 data_root='/',
                 ignore_label=255,
                 return_transformation=False,
                 augment_data=False,
                 config=None,
                 cache=False,
                 **kwargs):

        self.augment_data = augment_data
        self.config = config
        VoxelizationDatasetBase.__init__(
            self,
            data_paths,
            prevoxel_transform=prevoxel_transform,
            input_transform=input_transform,
            target_transform=target_transform,
            cache=cache,
            data_root=data_root,
            ignore_mask=ignore_label,
            return_transformation=return_transformation)

        # Prevoxel transformations
        self.voxelizer = Voxelizer(
            voxel_size=self.VOXEL_SIZE,
            clip_bound=self.CLIP_BOUND,
            use_augmentation=augment_data,
            scale_augmentation_bound=self.SCALE_AUGMENTATION_BOUND,
            rotation_augmentation_bound=self.ROTATION_AUGMENTATION_BOUND,
            translation_augmentation_ratio_bound=self.TRANSLATION_AUGMENTATION_RATIO_BOUND,
            ignore_label=ignore_label)

    def _augment_coords_to_feats(self, coords, feats, labels=None):
        norm_coords = coords - coords.mean(0)
        # color must come first.
        if isinstance(coords, np.ndarray):
            feats = np.concatenate((feats, norm_coords), 1)
        else:
            feats = torch.cat((feats, norm_coords), 1)
        return coords, feats, labels

    def convert_mat2cfl(self, mat):
        # Generally, xyz,rgb,label
        return mat[:, :3], mat[:, 3:-1], mat[:, -1]

    def get_instance_info(self, xyz, instance_ids):
        '''
        :param xyz: (n, 3)
        :param instance_ids: (n), int, (1~nInst, -1)
        :return: instance_num, dict
        '''
        centers = np.ones((xyz.shape[0], 3), dtype=np.float32) * -1  # (n, 9), float, (cx, cy, cz, minx, miny, minz, maxx, maxy, maxz, occ, num_instances)
        occupancy = {}  # (nInst), int
        bbox = {}
        unique_ids = np.unique(instance_ids)
        for id_ in unique_ids:
            if id_ == -1:
                continue

            mask = (instance_ids == id_)
            xyz_ = xyz[mask]
            bbox_min = xyz_.min(0)
            bbox_max = xyz_.max(0)
            center = xyz_.mean(0)

            centers[mask] = center
            occupancy[id_] = mask.sum()
            bbox[id_] = np.concatenate([bbox_min, bbox_max])

        return {"ids": instance_ids, "center": centers, "occupancy": occupancy, "bbox": bbox}

    def __getitem__(self, index):
        coords, feats, labels, instances, scene_names = self.load_data(index)
        # Downsample the pointcloud with finer voxel size before transformation for memory and speed
        if self.PREVOXELIZATION_VOXEL_SIZE is not None:
            inds = ME.utils.sparse_quantize(
                coords / self.PREVOXELIZATION_VOXEL_SIZE, return_index=True)
            coords = coords[inds]
            feats = feats[inds]
            labels = labels[inds]
            instances = instances[inds]

        # Prevoxel transformations
        if self.prevoxel_transform is not None:
            coords, feats, labels = self.prevoxel_transform(coords, feats, labels)

        coords, feats, labels, instances, transformation = self.voxelizer.voxelize(
            coords, feats, labels, instances)

        # map labels not used for evaluation to ignore_label
        if self.input_transform is not None:
            coords, feats, labels, instances = self.input_transform(coords, feats, labels, instances)
        if self.target_transform is not None:
            coords, feats, labels, instances = self.target_transform(coords, feats, labels, instances)

        if self.augment_data:
            # For some networks, making the network invariant to even, odd coords is important
            coords += (torch.rand(3) * 100).int().numpy()

        # ----------------Instances-------------------------
        instance_info = instances
        condition = (labels == self.ignore_mask)
        instances[condition] = -1
        IGNORE_LABELS_INSTANCE = self.IGNORE_LABELS if self.config.misc.train_stuff else self.IGNORE_LABELS_INSTANCE
        for ignore_id in IGNORE_LABELS_INSTANCE:
            condition = (labels == ignore_id)
            instances[condition] = -1
        instance_info = self.get_instance_info(coords, instances)

        # ------------- label mapping --------------------
        if self.IGNORE_LABELS is not None:
            labels = np.array([self.label_map[x] for x in labels], dtype=np.int)

        # Use coordinate features if config is set
        if self.AUGMENT_COORDS_TO_FEATS:
            coords, feats, labels = self._augment_coords_to_feats(coords, feats, labels)

        return_args = [coords, feats, labels, instance_info, scene_names, transformation.astype(np.float32)]

        return tuple(return_args)


class TemporalVoxelizationDataset(VoxelizationDataset):
    IS_TEMPORAL = True

    def __init__(self,
                 data_paths,
                 prevoxel_transform=None,
                 input_transform=None,
                 target_transform=None,
                 data_root='/',
                 ignore_label=255,
                 temporal_dilation=1,
                 temporal_numseq=3,
                 return_transformation=False,
                 augment_data=False,
                 config=None,
                 **kwargs):
        VoxelizationDataset.__init__(
            self,
            data_paths,
            prevoxel_transform=prevoxel_transform,
            input_transform=input_transform,
            target_transform=target_transform,
            data_root=data_root,
            ignore_label=ignore_label,
            return_transformation=return_transformation,
            augment_data=augment_data,
            config=config,
            **kwargs)
        self.temporal_dilation = temporal_dilation
        self.temporal_numseq = temporal_numseq
        temporal_window = temporal_dilation * (temporal_numseq - 1) + 1
        self.numels = [len(p) - temporal_window + 1 for p in self.data_paths]
        if any([numel <= 0 for numel in self.numels]):
            raise ValueError('Your temporal window configuration is too wide for '
                             'this dataset. Please change the configuration.')

    def load_world_pointcloud(self, filename):
        raise NotImplementedError

    def __getitem__(self, index):
        for seq_idx, numel in enumerate(self.numels):
            if index >= numel:
                index -= numel
            else:
                break

        numseq = self.temporal_numseq
        if self.augment_data and self.config.data.temporal_rand_numseq:
            numseq = random.randrange(1, self.temporal_numseq + 1)
        dilations = [self.temporal_dilation for i in range(numseq - 1)]
        if self.augment_data and self.config.data.temporal_rand_dilation:
            dilations = [random.randrange(1, self.temporal_dilation + 1) for i in range(numseq - 1)]
        files = [self.data_paths[seq_idx][index + sum(dilations[:i])] for i in range(numseq)]

        world_pointclouds = [self.load_world_pointcloud(f) for f in files]
        ptcs, centers = zip(*world_pointclouds)

        # Downsample pointcloud for speed and memory
        if self.PREVOXELIZATION_VOXEL_SIZE is not None:
            new_ptcs = []
            for ptc in ptcs:
                inds = ME.utils.sparse_quantize(
                    ptc[:, :3] / self.PREVOXELIZATION_VOXEL_SIZE, return_index=True)
                new_ptcs.append(ptc[inds])
            ptcs = new_ptcs

        # Apply prevoxel transformations
        ptcs = [self.prevoxel_transform(ptc) for ptc in ptcs]

        coords, feats, labels = zip(*ptcs)
        outs = self.voxelizer.voxelize_temporal(coords, feats, labels, centers=centers, return_transformation=True)
        coords_t, feats_t, labels_t, transformation_t = outs


        joint_coords = np.vstack([
            np.hstack((coords, np.ones((coords.shape[0], 1)) * i)) for i, coords in enumerate(coords_t)
        ])
        joint_feats = np.vstack(feats_t)
        joint_labels = np.hstack(labels_t)

        # map labels not used for evaluation to ignore_label
        if self.input_transform is not None:
            joint_coords, joint_feats, joint_labels = self.input_transform(joint_coords, joint_feats,
                                                                           joint_labels)
        if self.target_transform is not None:
            joint_coords, joint_feats, joint_labels = self.target_transform(joint_coords, joint_feats,
                                                                            joint_labels)
        if self.IGNORE_LABELS is not None:
            joint_labels = np.array([self.label_map[x] for x in joint_labels], dtype=np.int)

        return_args = [joint_coords, joint_feats, joint_labels]

        pointclouds = np.vstack([
            np.hstack((pointcloud[0][:, :6], np.ones((pointcloud[0].shape[0], 1)) * i))
            for i, pointcloud in enumerate(world_pointclouds)
        ])
        transformations = np.vstack(
            [np.hstack((transformation, [i])) for i, transformation in enumerate(transformation_t)])

        return_args.extend([pointclouds.astype(np.float32), transformations.astype(np.float32)])

        return tuple(return_args)

    def __len__(self):
        num_data = sum(self.numels)
        return num_data


def initialize_data_loader(DatasetClass,
                           config,
                           phase,
                           num_workers,
                           shuffle,
                           repeat,
                           augment_data,
                           batch_size,
                           input_transform=None,
                           target_transform=None,
                           persistent=False):
    """Initialize a data loader for a given dataset class."""

    limit_numpoints = config.data.train_limit_numpoints

    if not config.SOLO3D.solo_instseg:
        collate_fn = t.cfl_collate_fn_factory(limit_numpoints)
    else:
        collate_fn = t.cfl_instance_collate_fn_factory(limit_numpoints)

    prevoxel_transform_train = []
    if augment_data and config.augmentation.elastic_distortion:
        prevoxel_transforms = t.Compose([t.ElasticDistortion(DatasetClass.ELASTIC_DISTORT_PARAMS)])
    else:
        prevoxel_transforms = None

    input_transforms = []
    if input_transform is not None:
        input_transforms += input_transform

    if augment_data:
        input_transforms += [
            t.RandomDropout(0.2),
            t.RandomHorizontalFlip(DatasetClass.ROTATION_AXIS, DatasetClass.IS_TEMPORAL),
            t.ChromaticAutoContrast(),
            t.ChromaticTranslation(config.augmentation.data_aug_color_trans_ratio),
            t.ChromaticJitter(config.augmentation.data_aug_color_jitter_std),
            t.HueSaturationTranslation(config.augmentation.data_aug_hue_max, config.augmentation.data_aug_saturation_max),
        ]
        input_transforms = t.Compose(input_transforms)
    else:
        input_transforms = None

    dataset = DatasetClass(
        config,
        prevoxel_transform=prevoxel_transforms,
        input_transform=input_transforms,
        target_transform=target_transform,
        cache=config.data.cache_data,
        augment_data=augment_data,
        phase=phase)

    data_args = {
        'dataset': dataset,
        'num_workers': num_workers,
        'batch_size': batch_size,
        'collate_fn': collate_fn,
        'persistent_workers': persistent,
    }

    if repeat:
        data_args['sampler'] = InfSampler(dataset, shuffle)
    else:
        data_args['shuffle'] = shuffle

    data_loader = DataLoader(**data_args)

    return data_loader
