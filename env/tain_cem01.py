import numpy as np
import tensorflow as tf
from gym.spaces import Discrete, Box
from env.neobotixschunkGymEnv import NeobotixSchunkGymEnv

# ================================================================
# Policies
# ================================================================
class NN(object):
    def __init__(self, sess, sd, ad, action_bound):
        self.sess = sess
        self.s_dim = sd
        self.a_dim = ad
        self.action_bound = action_bound
        self.t_replace_counter = 0
        with tf.name_scope('State'):
            self.State = tf.placeholder(tf.float32, shape=[None, self.s_dim], name='s')

        with tf.variable_scope('Net'):
            # input s, output a
            self.a = self._build_net(self.State, scope='eval_net', trainable=True)

        self.e_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='Net/eval_net')

    def _build_net(self, s, scope, trainable):
        with tf.variable_scope(scope):
            init_w = tf.contrib.layers.xavier_initializer()
            init_b = tf.constant_initializer(0.001)
            net = tf.layers.dense(s, 128, activation=tf.nn.relu,
                                  kernel_initializer=init_w, bias_initializer=init_b, name='l1',
                                  trainable=trainable)
            net = tf.layers.dense(net, 64, activation=tf.nn.relu,
                                  kernel_initializer=init_w, bias_initializer=init_b, name='l2',
                                  trainable=trainable)
            actions = tf.layers.dense(net, self.a_dim, activation=tf.nn.tanh, kernel_initializer=init_w,
                                          name='a', trainable=trainable)
            scaled_a = tf.multiply(actions, self.action_bound, name='scaled_a')
        return scaled_a

    def calculate_action(self, s):
        s = [s]  # single state
        return self.sess.run(self.a, feed_dict={self.State: s})[0]

class DeterministicDiscreteActionLinearPolicy(object):

    def __init__(self, theta, ob_space, ac_space):
        """
        dim_ob: dimension of observations
        n_actions: number of actions
        theta: flat vector of parameters
        """
        dim_ob = ob_space.shape[0]
        n_actions = ac_space.n
        assert len(theta) == (dim_ob + 1) * n_actions
        self.W = theta[0 : dim_ob * n_actions].reshape(dim_ob, n_actions)
        self.b = theta[dim_ob * n_actions : None].reshape(1, n_actions)

    def act(self, ob):
        """
        """
        y = ob.dot(self.W) + self.b
        a = y.argmax()
        print('y', y, a)
        return a

class DeterministicContinuousActionLinearPolicy(object):

    def __init__(self, theta, ob_space, ac_space):
        """
        dim_ob: dimension of observations
        dim_ac: dimension of action vector
        theta: flat vector of parameters
        """
        self.ac_space = ac_space
        dim_ob = ob_space.shape[0]
        dim_ac = ac_space.shape[0]
        assert len(theta) == (dim_ob + 1) * dim_ac
        self.W = theta[0 : dim_ob * dim_ac].reshape(dim_ob, dim_ac)
        self.b = theta[dim_ob * dim_ac : None]

    def act(self, ob):
        #print('dot', ob ,(self.W).transpose(), self.b)
        a = np.clip(np.matmul([ob],self.W) + self.b, self.ac_space.low, self.ac_space.high)
        a=a[0]
        # print('a', a)
        return a

def do_episode(policy, env, num_steps, discount=1.0, render=False):
    disc_total_rew = 0
    ob = env.reset()
    for t in range(num_steps):
        # print('ds')
        a = policy.act(ob)
        (ob, reward, done, _info) = env.step(a)
        disc_total_rew += reward * discount**t
        if render and t%3==0:
            env.render()
        if done: break
    return disc_total_rew

env = None
def noisy_evaluation(theta, discount=0.90):
    policy = make_policy(theta)
    reward = do_episode(policy, env, num_steps, discount)
    return reward

def make_policy(theta):
    if isinstance(env.action_space, Discrete):
        return DeterministicDiscreteActionLinearPolicy(theta,
            env.observation_space, env.action_space)
    elif isinstance(env.action_space, Box):
        return DeterministicContinuousActionLinearPolicy(theta,
            env.observation_space, env.action_space)
    else:
        raise NotImplementedError

# Task settings:
env = NeobotixSchunkGymEnv(renders=True, isDiscrete=False, action_dim = 9, rewardtype='rdense', randomInitial=False)
num_steps = 1000 # maximum length of episode
# env.monitor.start('/tmp/cartpole-experiment-1')

# Alg settings:
n_iter = 20 # number of iterations of CEM
batch_size = 25 # number of samples per batch
elite_frac = 0.2 # fraction of samples used as elite set
n_elite = int(batch_size * elite_frac)
extra_std = 2.0
extra_decay_time = 10
print(env.observation_space,env.action_space)

if isinstance(env.action_space, Discrete):
    dim_theta = (env.observation_space.shape[0]+1) * env.action_space.n
elif isinstance(env.action_space, Box):
    dim_theta = (env.observation_space.shape[0]+1) * env.action_space.shape[0]
else:
    raise NotImplementedError

# Initialize mean and standard deviation
theta_mean = np.zeros(dim_theta)
theta_std = np.ones(dim_theta)
print(dim_theta,theta_mean, np.diag(np.array(theta_std**2)))
# Now, for the algorithm
for itr in range(n_iter):
    # Sample parameter vectors
    extra_cov = max(1.0 - itr / extra_decay_time, 0) * extra_std**2
    thetas = np.random.multivariate_normal(mean=theta_mean,
                                           cov=np.diag(np.array(theta_std**2) + extra_cov),
                                           size=batch_size)
    #print('theta', thetas.shape)
    rewards = np.array(map(noisy_evaluation, thetas))


    # Get elite parameters
    elite_inds = rewards.argsort()[-n_elite:]
    elite_thetas = thetas[elite_inds]
    #print('rewards', n_elite, rewards, elite_inds)

    # Update theta_mean, theta_std
    theta_mean = elite_thetas.mean(axis=0)
    theta_std = elite_thetas.std(axis=0)
    # print("iteration %i. mean f: %8.3g. max f: %8.3g"%(itr, np.mean(rewards), np.max(rewards)))
    #print('mean', theta_mean)
    do_episode(make_policy(theta_mean), env, num_steps, discount=0.90, render=True)
    print('ier', itr)

# env.monitor.close()

# gym.upload('/tmp/cartpole-experiment-1', api_key='sk_fzIs7KDMTtGbSREbrO4yfg')