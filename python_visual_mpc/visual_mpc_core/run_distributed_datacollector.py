import argparse
import os
import pdb
import importlib.machinery
import importlib.util
from python_visual_mpc.visual_mpc_core.infrastructure.run_sim import Sim
from multiprocessing import Pool
import copy
import random
import numpy as np
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import tensorflow as tf
import ray
import matplotlib; matplotlib.use('Agg'); import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from python_visual_mpc.visual_mpc_core.infrastructure.utility.logger import Logger

from tensorflow.python.platform import gfile
from python_visual_mpc.visual_mpc_core.infrastructure.remote_synchronizer import sync
import re


GEN_VAL_FREQ = 100
VAL_TASK_FREQ = 200


from tensorflow.python.framework.errors_impl import NotFoundError
def get_maxiter_weights(dir):
    try:
        filenames = gfile.Glob(dir +'/model*')
    except NotFoundError:
        print('nothing found at ', dir +'/model*')
        return None
    iternums = []
    if len(filenames) != 0:
        for f in filenames:
            try:
                iternums.append(int(re.match('.*?([0-9]+)$', f).group(1)))
            except:
                iternums.append(-1)
        iternums = np.array(iternums)
        return filenames[np.argmax(iternums)].split('.')[0] # skip the str after the '.'
    else:
        return None

def worker(conf):
    d = Data_Collector(conf)
    d.run_traj()

# @ray.remote
class Data_Collector(object):
    def __init__(self, conf):
        self.logger = Logger(conf['agent']['logging_dir'], 'datacollector_gpu{}_log.txt'.format(conf['gpu_id']), conf['printout'])
        self.logger.log('started process with PID {}'.format(os.getpid()))
        self.itraj = conf['start_index']
        self.ntraj = 0
        self.maxtraj = conf['end_index']
        random.seed(None)
        np.random.seed(None)
        self.conf = conf
        self.sim = Sim(conf, gpu_id=conf['gpu_id'], logger=self.logger)
        self.logger.log('init data collectors done.')
        self.last_weights_loaded = None

    def run_traj(self):
        self.logger.log('starting data collection')
        while self.itraj < self.maxtraj:
            max_iter_weights = get_maxiter_weights('/result/modeldata')
            if max_iter_weights != None:
                self.logger.log('len trajlist', len(self.sim.trajectory_list))
                if max_iter_weights != self.last_weights_loaded and len(self.sim.trajectory_list) == 0:
                    self.last_weights_loaded = copy.deepcopy(max_iter_weights)
                    self.conf['load_latest'] = max_iter_weights
                    self.sim = Sim(self.conf, gpu_id=self.conf['gpu_id'], logger=self.logger)
            self.logger.log('-------------------------------------------------------------------')
            self.logger.log('run number ', self.itraj)
            self.logger.log('-------------------------------------------------------------------')

            # reinitilize policy between rollouts
            record_dir = self.sim.agentparams['result_dir'] + '/verbose/traj{0}'.format(self.itraj)
            if not os.path.exists(record_dir):
                os.makedirs(record_dir)
            self.sim.agent._hyperparams['record'] = record_dir

            if self.itraj % GEN_VAL_FREQ:
                self.sim.task_mode= 'val'
            else: self.sim.task_mode= 'train'
            self.sim.take_sample(self.itraj)

            self.itraj += 1

        self.logger.log('done. itraj {} maxtraj {}'.format(self.itraj, self.maxtraj))

def main():
    parser = argparse.ArgumentParser(description='run parllel data collection')
    parser.add_argument('experiment', type=str, help='experiment name')
    parser.add_argument('--nworkers', type=int, help='use multiple threads or not', default=1)
    parser.add_argument('--nsplit', type=int, help='number of splits to partition the generated data indices', default=-1)
    parser.add_argument('--isplit', type=int, help='split id: number from 0 to nsplit-1', default=0)
    parser.add_argument('--printout', type=int, help='print to console if 1', default=0)

    args = parser.parse_args()
    hyperparams_file = args.experiment
    printout = bool(args.printout)

    n_worker = args.nworkers
    if args.nworkers == 1:
        parallel = False
    else:
        parallel = True
    print('parallel ', bool(parallel))
    hyperparams = load_module(hyperparams_file, 'mod_hyper')

    if args.nsplit != -1:
        n_persplit = (hyperparams['end_index']+1)//args.nsplit
        hyperparams['start_index'] = args.isplit * n_persplit
        hyperparams['end_index'] = (args.isplit+1) * n_persplit -1

    n_traj = hyperparams['end_index'] - hyperparams['start_index'] +1
    traj_per_worker = int(n_traj // np.float32(n_worker))
    start_idx = [hyperparams['start_index'] + traj_per_worker * i for i in range(n_worker)]
    end_idx = [hyperparams['start_index'] + traj_per_worker * (i+1)-1 for i in range(n_worker)]

    if 'RESULT_DIR' in os.environ:
        print('clearing result dir')
        os.system('rm -r {}/*'.format(os.environ['RESULT_DIR']))

        result_dir = os.environ['RESULT_DIR']
        if 'verbose' in hyperparams['policy'] and not os.path.exists(result_dir + '/verbose'):
            os.makedirs(result_dir + '/verbose')
        hyperparams['agent']['result_dir'] = result_dir
        hyperparams['agent']['logging_dir'] = os.environ['RESULT_DIR'] + '/logging_node{}'.format(args.isplit)
    else:
        hyperparams['agent']['result_dir'] = hyperparams['current_dir']

    exp_name = '/'.join(str.split(hyperparams_file.partition('cem_exp')[2], '/')[:-1])
    hyperparams['exp_name'] = exp_name

    if not os.path.exists(hyperparams['agent']['logging_dir']):
        os.makedirs(hyperparams['agent']['logging_dir'])

    # if not parallel:
    #     ray.init()
    #     hyperparams['gpu_id'] = 0
    #     d = Data_Collector(hyperparams, 0, printout=True)
    #     d.run_traj()
    # else:
    #     ray.init()
    #     data_collectors = []
    #     print('launching datacollectors.')
    #     for i in range(n_worker):
    #         modconf = copy.deepcopy(hyperparams)
    #         modconf['start_index'] = start_idx[i]
    #         modconf['end_index'] = end_idx[i]
    #         modconf['gpu_id'] = i
    #         data_collectors.append(Data_Collector.remote(modconf, i, printout))
    #
    #     todo_ids = [d.run_traj.remote() for d in data_collectors]
    #     print('launched datacollectors.')

    conflist = []
    hyperparams['printout'] = printout
    hyperparams['collector_id'] = args.isplit
    for i in range(n_worker):
        modconf = copy.deepcopy(hyperparams)
        modconf['start_index'] = start_idx[i]
        modconf['end_index'] = end_idx[i]
        modconf['gpu_id'] = i
        conflist.append(modconf)
    if parallel:
        p = Pool(n_worker)
        p.map(worker, conflist)
    else:
        worker(conflist[0])

    sync_todo_id = sync.remote(args.isplit, hyperparams)
    print('launched sync')
    ray.wait([sync_todo_id])

    # ray.wait(todo_ids)

def load_module(hyperparams_file, name):
    loader = importlib.machinery.SourceFileLoader(name, hyperparams_file)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    hyperparams = mod.config
    return hyperparams

if __name__ == '__main__':
    main()