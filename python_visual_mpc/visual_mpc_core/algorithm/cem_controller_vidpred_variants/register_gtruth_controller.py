from python_visual_mpc.visual_mpc_core.algorithm.cem_controller_vidpred import CEM_Controller_Vidpred
import copy
import numpy as np
from python_visual_mpc.video_prediction.utils_vpred.animate_tkinter import resize_image
from python_visual_mpc.visual_mpc_core.algorithm.utils.make_cem_visuals import CEM_Visual_Preparation_Registration
import imp
import pdb
from python_visual_mpc.visual_mpc_core.algorithm.cem_controller_base import CEM_Controller_Base

from python_visual_mpc.goaldistancenet.setup_gdn import setup_gdn

class Register_Gtruth_Controller(CEM_Controller_Vidpred):
    def __init__(self, ag_params, policyparams, gpu_id, ngpu):
        super().__init__(ag_params, policyparams, gpu_id, ngpu)
        
        self._hp = self._default_hparams()
        self.override_defaults(policyparams)

        if self._hp.trade_off_reg:
            self.reg_tradeoff = np.ones([self.ncam, self.ndesig])/self.ncam/self.ndesig

        params = imp.load_source('params', ag_params['current_dir'] + '/gdnconf.py')
        self.gdnconf = params.configuration
        self.goal_image_warper = setup_gdn(self.gdnconf, gpu_id)
        self.visualizer = CEM_Visual_Preparation_Registration()

        num_reg_images = len(self._hp.register_gtruth)
        self.ntask = self.ntask = self.ndesig // num_reg_images


    def _default_hparams(self):
        default_dict = {
            'register_gtruth':['start','goal'],
            
        }
        parent_params = super()._default_hparams()

        for k in default_dict.keys():
            parent_params.add_hparam(k, default_dict[k])
        return parent_params

    def prep_vidpred_inp(self, actions, cem_itr):
        actions, last_frames, last_states, t_0 = super(Register_Gtruth_Controller, self).prep_vidpred_inp(actions, cem_itr)
        if 'image_medium' in self.agentparams:  # downsample to video-pred reslution
            last_frames = resize_image(last_frames, (self.img_height, self.img_width))
        if self._hp.register_gtruth and cem_itr == 0:
            self.start_image = copy.deepcopy(self.images[0]).astype(np.float32) / 255.
            self.warped_image_start, self.warped_image_goal, self.reg_tradeoff = self.register_gtruth(self.start_image,
                                                                                                      last_frames)
        return actions, last_frames, last_states, t_0

    def register_gtruth(self,start_image, last_frames):
        """
        :param start_image:
        :param last_frames:
        :param goal_image:
        :return:  returns tradeoff with shape: ncam, ndesig
        """
        last_frames = last_frames[0, self.ncontxt -1]

        desig_pix_l, warperrs_l = [], []
        warped_image_start, _, start_warp_pts = self.goal_image_warper(last_frames[None], start_image[None])
        if 'goal' in self._hp.register_gtruth:
            warped_image_goal, _, goal_warp_pts = self.goal_image_warper(last_frames[None], self.goal_image[None])

        imheight, imwidth = self.goal_image.shape[1:3]
        for n in range(self.ncam):
            start_warp_pts = start_warp_pts.reshape(self.ncam, imheight, imwidth, 2)
            warped_image_start = warped_image_start.reshape(self.ncam, imheight, imwidth, 3)
            if 'goal' in self._hp.register_gtruth:
                goal_warp_pts = goal_warp_pts.reshape(self.ncam, imheight, imwidth, 2)
                warped_image_goal = warped_image_goal.reshape(self.ncam, imheight, imwidth, 3)
            else:
                goal_warp_pts = None
                warped_image_goal = None
            warperr, desig_pix = self.get_warp_err(n, start_image, self.goal_image, start_warp_pts, goal_warp_pts, warped_image_start, warped_image_goal)
            warperrs_l.append(warperr)
            desig_pix_l.append(desig_pix)

        self.desig_pix = np.stack(desig_pix_l, axis=0).reshape(self.ncam, self.ndesig, 2)

        warperrs = np.stack(warperrs_l, 0)    # shape: ncam, ntask, r

        tradeoff = (1 / warperrs)
        normalizers = np.sum(np.sum(tradeoff, 0, keepdims=True), 2, keepdims=True)
        tradeoff = tradeoff / normalizers
        tradeoff = tradeoff.reshape(self.ncam, self.ndesig)

        self.plan_stat['tradeoff'] = tradeoff
        self.plan_stat['warperrs'] = warperrs.reshape(self.ncam, self.ndesig)

        # fill visualzation data object:
        self.vd.reg_tradeoff = tradeoff
        self.vd.ntask = self.ntask
        self.vd.warped_image_start = warped_image_start
        self.vd.warped_image_goal = warped_image_goal
        self.vd.desig_pix_t0_med = self.desig_pix_t0_med
        self.vd.desig_pix_t0 = self.desig_pix_t0
        self.vd.desig_pix = self.desig_pix
        self.vd.start_image = self.start_image
        self.vd.goal_image = self.goal_image

        return warped_image_start, warped_image_goal, tradeoff

    def get_warp_err(self, icam, start_image, goal_image, start_warp_pts, goal_warp_pts, warped_image_start, warped_image_goal):
        r = len(self._hp.register_gtruth)
        warperrs = np.zeros((self.ntask, r))
        desig = np.zeros((self.ntask, r, 2))
        for p in range(self.ntask):
            if 'image_medium' in self.agentparams:
                pix_t0 = self.desig_pix_t0_med[icam, p]
                goal_pix = self.goal_pix_med[icam, p]
                self.logger.log('using desig goal pix medium')
            else:
                pix_t0 = self.desig_pix_t0[icam, p]     # desig_pix_t0 shape: icam, ndesig, 2
                goal_pix = self.goal_pix_sel[icam, p]
                # goal_image = cv2.resize(goal_image, (self.agentparams['image_width'], self.agentparams['image_height']))

            if 'start' in self._hp.register_gtruth:
                desig[p, 0] = np.flip(start_warp_pts[icam][pix_t0[0], pix_t0[1]], 0)
                warperrs[p, 0] = np.linalg.norm(start_image[icam][pix_t0[0], pix_t0[1]] -
                                                warped_image_start[icam][pix_t0[0], pix_t0[1]])

            if 'goal' in self._hp.register_gtruth:
                desig[p, 1] = np.flip(goal_warp_pts[icam][goal_pix[0], goal_pix[1]], 0)
                warperrs[p, 1] = np.linalg.norm(goal_image[icam][goal_pix[0], goal_pix[1]] -
                                                warped_image_goal[icam][goal_pix[0], goal_pix[1]])

        if 'image_medium' in self.agentparams:
            desig = desig * self.agentparams['image_height']/ self.agentparams['image_medium'][0]
        return warperrs, desig


    def act(self, t=None, i_tr=None, desig_pix=None, goal_pix=None, images=None, goal_image=None, state=None):

        num_reg_images = len(self._hp.register_gtruth)
        self.goal_pix_sel = np.array(goal_pix).reshape((self.ncam, self.ntask, 2))
        self.goal_pix = np.tile(self.goal_pix_sel[:,:,None,:], [1,1,num_reg_images,1])  # copy along r: shape: ncam, ntask, r
        self.goal_pix = self.goal_pix.reshape(self.ncam, self.ndesig, 2)
        if 'image_medium' in self.agentparams:
            self.goal_pix_med = (self.goal_pix * self.agentparams['image_medium'][0] / self.agentparams['image_height']).astype(np.int)
        self.goal_image = goal_image[-1]

        if t == 0:
            self.desig_pix_t0 = np.array(desig_pix).reshape((self.ncam, self.ntask, 2))   # 1,1,2
            if 'image_medium' in self.agentparams:
                self.desig_pix_t0_med = (self.desig_pix_t0 * self.agentparams['image_medium'][0]/self.agentparams['image_height']).astype(np.int)
            else: self.desig_pix_t0_med = None

        self.images = images
        self.state = state
        return super(CEM_Controller_Vidpred, self).act(t, i_tr)
