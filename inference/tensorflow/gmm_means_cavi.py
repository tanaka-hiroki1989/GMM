# -*- coding: UTF-8 -*-

"""
Coordinate Ascent Variational Inference process to approximate a mixture
of gaussians with common variance for all classes
"""

from __future__ import absolute_import

import argparse
import math
import os
import pickle as pkl
import sys
from time import time

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf

sys.path.insert(1, os.path.join(sys.path[0], '..'))

from utils import dirichlet_expectation, log_beta_function, softmax

from viz import plot_iteration

"""
Parameters:
    * maxIter: Max number of iterations
    * dataset: Dataset path
    * k: Number of clusters
    * verbose: Printing time, intermediate variational parameters, plots, ...
    
Execution:
    python gmm_means_gavi.py -dataset data_k2_1000.pkl -k 2 -verbose 
"""

parser = argparse.ArgumentParser(description='CAVI in mixture of gaussians')
parser.add_argument('-maxIter', metavar='maxIter', type=int, default=300)
parser.add_argument('-dataset', metavar='dataset', type=str,
                    default='../../data/synthetic/2D/k2/data_k2_1000.pkl')
parser.add_argument('-k', metavar='k', type=int, default=2)
parser.add_argument('-verbose', dest='verbose', action='store_true')
parser.set_defaults(verbose=False)
args = parser.parse_args()

K = args.k
VERBOSE = args.verbose
THRESHOLD = 1e-6

sess = tf.Session()


# Get data
with open('{}'.format(args.dataset), 'r') as inputfile:
    data = pkl.load(inputfile)
    xn = data['xn']
    xn_tf = tf.convert_to_tensor(xn, dtype=tf.float64)
N, D = xn.shape

if VERBOSE: init_time = time()

# Model hyperparameters
alpha_aux = [1.0] * K
m_o_aux = np.array([0.0, 0.0])
beta_o_aux = 0.01
delta_o_aux = np.zeros((D, D), long)
np.fill_diagonal(delta_o_aux, 1)

# Priors (TF castings)
alpha_o = tf.convert_to_tensor([alpha_aux], dtype=tf.float64)
m_o = tf.convert_to_tensor([list(m_o_aux)], dtype=tf.float64)
beta_o = tf.convert_to_tensor(beta_o_aux, dtype=tf.float64)
delta_o = tf.convert_to_tensor(delta_o_aux, dtype=tf.float64)

# Initializations
lambda_phi_aux = np.random.dirichlet(alpha_aux, N)
lambda_pi_aux = alpha_aux + np.sum(lambda_phi_aux, axis=0)
lambda_beta_aux = beta_o_aux + np.sum(lambda_phi_aux, axis=0)
lambda_m_aux = np.tile(1. / lambda_beta_aux, (2, 1)).T * \
                  (beta_o_aux * m_o_aux + np.dot(lambda_phi_aux.T, xn))

# Variational parameters
lambda_phi = tf.Variable(lambda_phi_aux, dtype=tf.float64)
lambda_pi = tf.Variable(lambda_pi_aux, dtype=tf.float64)
lambda_beta = tf.Variable(lambda_beta_aux, dtype=tf.float64)
lambda_m = tf.Variable(lambda_m_aux, dtype=tf.float64)

# Reshapes
lambda_mu_beta_res = tf.reshape(lambda_beta, [K, 1])

# Lower Bound definition
LB = log_beta_function(lambda_pi)
LB = tf.subtract(LB, log_beta_function(alpha_o))
LB = tf.add(LB, tf.matmul(tf.subtract(alpha_o, lambda_pi),
                          tf.reshape(dirichlet_expectation(lambda_pi),
                                     [K, 1])))
LB = tf.add(LB, tf.multiply(tf.cast(K / 2., tf.float64),
                            tf.log(tf.matrix_determinant(
                                tf.multiply(beta_o, delta_o)))))
LB = tf.add(LB, tf.cast(K * (D / 2.), tf.float64))
for k in range(K):
    a1 = tf.subtract(lambda_m[k, :], m_o)
    a2 = tf.matmul(delta_o, tf.transpose(tf.subtract(lambda_m[k, :], m_o)))
    a3 = tf.multiply(tf.div(beta_o, 2.), tf.matmul(a1, a2))
    a4 = tf.div(tf.multiply(tf.cast(D, tf.float64), beta_o),
                tf.multiply(tf.cast(2., tf.float64), lambda_mu_beta_res[k]))
    a5 = tf.multiply(tf.cast(1 / 2., tf.float64),
                     tf.log(tf.multiply(tf.pow(lambda_mu_beta_res[k], 2),
                                        tf.matrix_determinant(delta_o))))
    a6 = tf.add(a3, tf.add(a4, a5))
    LB = tf.subtract(LB, a6)
    b1 = tf.transpose(lambda_phi[:, k])
    b2 = dirichlet_expectation(lambda_pi)[k]
    b3 = tf.log(lambda_phi[:, k])
    b4 = tf.multiply(tf.cast(1 / 2., tf.float64),
                     tf.log(tf.div(tf.matrix_determinant(delta_o),
                                   tf.multiply(tf.cast(2., tf.float64),
                                               math.pi))))
    b5 = tf.subtract(xn_tf, lambda_m[k, :])
    b6 = tf.matmul(delta_o, tf.transpose(tf.subtract(xn_tf, lambda_m[k, :])))
    b7 = tf.multiply(tf.cast(1 / 2., tf.float64),
                     tf.stack([tf.matmul(b5, b6)[i, i] for i in range(N)]))
    b8 = tf.div(tf.cast(D, tf.float64),
                tf.multiply(tf.cast(2., tf.float64), lambda_beta[k]))
    b9 = tf.subtract(tf.subtract(tf.add(tf.subtract(b2, b3), b4), b7), b8)
    b1 = tf.reshape(b1, [1, N])
    b9 = tf.reshape(b9, [N, 1])
    LB = tf.add(LB, tf.reshape(tf.matmul(b1, b9), [1]))

# Parameter updates
assign_lambda_pi = lambda_pi.assign(
    tf.reshape(tf.add(alpha_o, tf.reduce_sum(lambda_phi, 0)), [K, ]))

c1 = dirichlet_expectation(lambda_pi)
phi_tmp = []
for n in range(N):
    k_list = []
    for k in range(K):
        c2 = tf.reshape(tf.subtract(xn_tf[n, :], lambda_m[k, :]), [1, D])
        c3 = tf.matmul(delta_o, tf.reshape(
            tf.transpose(tf.subtract(xn_tf[n, :], lambda_m[k, :])), [D, 1]))
        c4 = tf.multiply(tf.cast(-1 / 2., tf.float64), tf.matmul(c2, c3))
        c5 = tf.div(tf.cast(D, tf.float64),
                    tf.multiply(tf.cast(2., tf.float64), lambda_beta[k]))
        k_list.append(tf.add(c1[k], tf.subtract(c4, c5)))
    phi_tmp.append(tf.reshape(softmax(tf.stack(k_list)), [K, 1]))
assign_lambda_phi = lambda_phi.assign(tf.reshape(tf.stack(phi_tmp), [N, K]))

assign_lambda_beta = lambda_beta.assign(
    tf.add(beta_o, tf.reduce_sum(lambda_phi, axis=0)))

d1 = tf.transpose(
    tf.reshape(tf.tile(tf.div(tf.cast(1., tf.float64), lambda_beta), [D]),
               [D, K]))
d2 = tf.add(tf.multiply(m_o, beta_o), tf.matmul(tf.transpose(lambda_phi), xn_tf))
assign_lambda_m = lambda_m.assign(tf.multiply(d1, d2))

# Summaries definition
tf.summary.histogram('lambda_phi', lambda_phi)
tf.summary.histogram('lambda_pi', lambda_pi)
tf.summary.histogram('lambda_mu_m', lambda_m)
tf.summary.histogram('lambda_mu_beta', lambda_beta)
merged = tf.summary.merge_all()
file_writer = tf.summary.FileWriter('/tmp/tensorboard/', tf.get_default_graph())


def main():

    # Plot configs
    if VERBOSE:
        plt.ion()
        fig = plt.figure(figsize=(10, 10))
        ax_spatial = fig.add_subplot(1, 1, 1)
        circs = []
        sctZ = None

    # Inference
    init = tf.global_variables_initializer()
    sess.run(init)
    lbs = []
    n_iters = 0
    for _ in range(args.maxIter):

        # Variational parameter updates
        sess.run(assign_lambda_pi)
        sess.run(assign_lambda_phi)
        sess.run(assign_lambda_beta)
        sess.run(assign_lambda_m)
        m_out, beta_out, pi_out, phi_out = sess.run(
            [lambda_m, lambda_beta, lambda_pi, lambda_phi])

        # ELBO computation
        mer, lb = sess.run([merged, LB])
        lbs.append(lb[0][0])

        if VERBOSE:
            print('\n******* ITERATION {} *******'.format(n_iters))
            print('lambda_pi: {}'.format(pi_out))
            print('lambda_beta: {}'.format(beta_out))
            print('lambda_m: {}'.format(m_out))
            print('lambda_phi: {}'.format(phi_out[0:9, :]))
            print('ELBO: {}'.format(lb))
            ax_spatial, circs, sctZ = plot_iteration(ax_spatial, circs, sctZ,
                                                     sess.run(lambda_m),
                                                     sess.run(delta_o),
                                                     xn, n_iters, K)

        # Break condition
        improve = lb - lbs[n_iters - 1]
        if VERBOSE: print('Improve: {}'.format(improve))
        if (n_iters == (args.maxIter - 1)) \
                or (n_iters > 0 and 0 < improve < THRESHOLD):
            if VERBOSE and D == 2: plt.savefig('generated/plot.png')
            break

        n_iters += 1
        file_writer.add_summary(mer, n_iters)

    if VERBOSE:
        print('\n******* RESULTS *******')
        for k in range(K):
            print('Mu k{}: {}'.format(k, m_out[k, :]))
        final_time = time()
        exec_time = final_time - init_time
        print('Time: {} seconds'.format(exec_time))
        print('Iterations: {}'.format(n_iters))
        print('ELBOs: {}'.format(lbs))


if __name__ == '__main__': main()
