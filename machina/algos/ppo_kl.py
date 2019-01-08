# Copyright 2018 DeepX Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# This is an implementation of Proximal Policy Optimization
# in which gradient is clipped by the KL divergence especially.
# See https://arxiv.org/abs/1707.06347
# 


import torch
import torch.nn as nn

from machina import loss_functional as lf
from machina import logger


def update_pol(pol, optim_pol, batch, kl_beta, max_grad_norm):
    pol_loss = lf.pg_kl(pol, batch, kl_beta)
    optim_pol.zero_grad()
    pol_loss.backward()
    torch.nn.utils.clip_grad_norm_(pol.parameters(), max_grad_norm)
    optim_pol.step()
    return pol_loss.detach().cpu().numpy()

def update_vf(vf, optim_vf, batch):
    vf_loss = lf.monte_carlo(vf, batch)
    optim_vf.zero_grad()
    vf_loss.backward()
    optim_vf.step()
    return vf_loss.detach().cpu().numpy()

def train(traj, pol, vf,
        kl_beta, kl_targ,
        optim_pol, optim_vf,
        epoch, batch_size, max_grad_norm,
        num_epi_per_seq=1# optimization hypers
        ):

    pol_losses = []
    vf_losses = []
    logger.log("Optimizing...")
    iterator = traj.iterate(batch_size, epoch) if not pol.rnn else traj.iterate_rnn(batch_size=batch_size, num_epi_per_seq=num_epi_per_seq, epoch=epoch)
    for batch in iterator:
        pol_loss = update_pol(pol, optim_pol, batch, kl_beta, max_grad_norm)
        vf_loss = update_vf(vf, optim_vf, batch)

        pol_losses.append(pol_loss)
        vf_losses.append(vf_loss)

    iterator = traj.full_batch(1) if not pol.rnn else traj.iterate_rnn(batch_size=traj.num_epi)
    batch = next(iterator)
    with torch.no_grad():
        pol.reset()
        if pol.rnn:
            _, _, pd_params = pol(batch['obs'], h_masks=batch['h_masks'])
        else:
            _, _, pd_params = pol(batch['obs'])
        kl_mean = torch.mean(
            pol.pd.kl_pq(
                batch,
                pd_params
            )
        ).item()
    if kl_mean > 1.3 * kl_targ:
        new_kl_beta = 1.5 * kl_beta
    elif kl_mean < 0.7 * kl_targ:
        new_kl_beta = kl_beta / 1.5
    else:
        new_kl_beta = kl_beta
    logger.log("Optimization finished!")

    return dict(PolLoss=pol_losses, VfLoss=vf_losses, new_kl_beta=new_kl_beta, kl_mean=kl_mean)

