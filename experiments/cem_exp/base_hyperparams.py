""" Base Hyperparameters for benchmarks"""
from __future__ import division

from datetime import datetime
import os.path

import numpy as np

from python_visual_mpc.visual_mpc_core.agent.agent_mjc import AgentMuJoCo

IMAGE_WIDTH = 64
IMAGE_HEIGHT = 64
IMAGE_CHANNELS = 3

num_objects = 1

current_dir = '/'.join(str.split(__file__, '/')[:-1])

alpha = 30*np.pi/180
agent = {
    'type': AgentMuJoCo,
    'filename': './../../mjc_models/pushing2d_controller.xml',
    'filename_nomarkers': './../../mjc_models/pushing2d_controller_nomarkers.xml',
    'data_collection': False,
    'x0': np.array([0., 0., 0., 0.,
                    .1, .1, 0., np.cos(alpha/2), 0, 0, np.sin(alpha/2)  #object pose (x,y,z, quat)
                     ]),
    'state_dim': 2,
    'dt': 0.05,
    'substeps': 20,  #10
    'T': 15,
    'skip_first': 0,
    'additional_viewer': True,
    'image_height' : IMAGE_HEIGHT,
    'image_width' : IMAGE_WIDTH,
    'image_channels' : IMAGE_CHANNELS,
    'num_objects': num_objects,
    'current_dir': current_dir,
    'record': current_dir + '/data_files/rec',
    'add_traj': True
}

from python_visual_mpc.visual_mpc_core.algorithm.pos_controller import Pos_Controller
low_level_conf = {
    'type': Pos_Controller,
    'mode': 'relative',
    'randomtargets' : False
}

from python_visual_mpc.visual_mpc_core.algorithm.cem_controller import CEM_controller
policy = {
    'type' : CEM_controller,
    'current_dir': current_dir
}

config = {
    'save_data': False,
    'start_index':None,
    'end_index': None,
    'verbose_policy_trials': 0,
    'agent': agent,
    'policy': policy
}

